import copy
import gzip
import json
import socket
from datetime import datetime, timezone

import httpcore
import httpx
import pytest

from pipeline.article import ArticleDocument, digest, parse_article
from pipeline.crawl import seed, plan, progress, classify_failure
from pipeline.network import OAFetcher, PolicyError, PublicBackend, check_url, retry_seconds
from pipeline.research import extraction, validate_record, VARIABLE_FIELDS, PAPER_FIELDS


def resolve(host,port,**kwargs):
    return [(socket.AF_INET,socket.SOCK_STREAM,6,'',('93.184.216.34',port))]


@pytest.mark.parametrize('url',['http://example.org','https://localhost','https://127.0.0.1','https://169.254.169.254/latest','https://[::1]','https://user:pass@example.org','https://example.org:8000/'])
def test_ssrf_addresses_and_credentials_blocked(url):
    def lookup(host,port,**kwargs):
        ip=host if host in {'127.0.0.1','169.254.169.254','::1'} else '93.184.216.34'
        return [(socket.AF_INET,socket.SOCK_STREAM,6,'',(ip,port))]
    with pytest.raises(PolicyError):check_url(url,lookup)


def test_dns_rebinding_cannot_reach_private_endpoint(monkeypatch):
    assert check_url('https://allowed.example/file',resolve)
    monkeypatch.setattr(socket,'getaddrinfo',lambda *a,**k:[(2,1,6,'',('10.0.0.1',443))])
    with pytest.raises(PolicyError):PublicBackend().connect_tcp('allowed.example',443)


def test_backend_pins_public_ip_and_keeps_origin_separate(monkeypatch):
    calls=[]
    monkeypatch.setattr(socket,'getaddrinfo',resolve)
    monkeypatch.setattr(httpcore.SyncBackend,'connect_tcp',lambda self,host,*a:calls.append(host) or 'stream')
    assert PublicBackend().connect_tcp('allowed.example',443)=='stream'
    assert calls==['93.184.216.34']


def test_redirect_to_metadata_host_is_blocked_before_request():
    seen=[]
    def handler(r):
        seen.append(str(r.url))
        return httpx.Response(302,headers={'location':'http://169.254.169.254/secrets'})
    f=OAFetcher(httpx.Client(transport=httpx.MockTransport(handler)),resolve,interval=0)
    with pytest.raises(PolicyError):f.fetch('https://example.org/p.pdf',policy=False)
    assert seen==['https://example.org/p.pdf']


def test_gzip_content_is_decoded_exactly_once():
    content=b'%PDF-test'
    f=OAFetcher(httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=gzip.compress(content),headers={'content-encoding':'gzip'}))),resolve,interval=0)
    response,_=f.fetch('https://example.org/p.pdf',policy=False)
    assert response.content==content


def test_429_respects_retry_after_without_unbounded_retries():
    client=httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(429,headers={'Retry-After':'3600'})))
    f=OAFetcher(client,resolve,interval=0)
    r,_=f.fetch('https://example.org/p.pdf',policy=False)
    assert r.status_code==429
    with pytest.raises(PolicyError,match='retry_after'):f.fetch('https://example.org/another.pdf',policy=False)
    assert f.requests==1


def test_retry_after_http_date_and_cap():
    assert retry_seconds('Sun, 08 Nov 2026 01:00:00 GMT',datetime(2026,11,8,tzinfo=timezone.utc))==3600
    assert retry_seconds('9999999')==86400


def test_global_network_budget_stops_without_extra_requests():
    f=OAFetcher(httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200))),resolve,interval=0)
    f.max_requests=1;f.fetch('https://example.org/a',policy=False)
    with pytest.raises(PolicyError,match='global_request_budget'):f.fetch('https://example.org/b',policy=False)
    assert f.requests==1


def fixtures():
    papers=[dict(paper_id=f'doi:10.1002/{i}',doi=f'10.1002/{i}',title='Test paper',authors=['Test Author']) for i in range(3)]
    enrich=[dict(paper_id=papers[0]['paper_id'],retrieved_at='2026-01-01',oa_locations=[dict(is_oa=True,is_accepted=True,pdf_url='https://example.org/one.pdf',landing_page_url='https://example.org/paper')]),dict(paper_id=papers[1]['paper_id'],retrieved_at='2026-01-01',oa_locations=[])]
    return papers,enrich


def test_every_indexed_doi_is_queued_including_missing_enrichment():
    p,e=fixtures();q,c=seed(p,e,[])
    assert len(q)==3 and sum(x['discovery_status']=='discovery_pending' for x in q)==1
    assert progress(q,c)['round_complete'] is False
    assert progress([],c)['round_complete'] is False


def test_source_progress_survives_roundtrip_and_never_restarts_first_url():
    p,e=fixtures();q,c=seed(p,e,[])
    first=plan(q,c,1)[0][1]
    first.update(state='policy_blocked',cycle_attempted=c['cycle_id'],attempts_count=1,error_class='http_403')
    q2,c2=seed(p,e,[],json.loads(json.dumps(q)),json.loads(json.dumps(c)))
    assert len(q2)==3 and len(q2[0]['sources'])==2
    assert plan(q2,c2,1)[0][1]['url']!=first['url']
    assert q2[0]['sources'][0]['attempts_count']==1


def test_new_urls_reopen_completed_cycle_without_overwriting_prior_attempts():
    p,e=fixtures();q,c=seed(p,e,[])
    c['state']='cycle_complete'
    e[0]['oa_locations'].append(dict(is_oa=True,is_accepted=True,pdf_url='https://example.org/new.pdf'))
    q,c=seed(p,e,[],q,c)
    assert c['state']=='running' and len(q[0]['sources'])==3


def test_all_doi_discovery_and_all_source_receipts_required_for_completion():
    p,e=fixtures();q,c=seed(p,e,[])
    for row in q:row['discovery_checked_at']='now'
    for row in q:
        for source in row['sources']:source['cycle_attempted']=c['cycle_id']
    assert progress(q,c)['round_complete']
    q[0]['sources'][0]['cycle_attempted']=None
    assert not progress(q,c)['round_complete']


def test_unvisited_old_paper_precedes_upgrade_and_newer_arrivals():
    p,e=fixtures();q,c=seed(p,e,[])
    old=q[0]['sources'][0]
    old.update(state='parsed',cycle_attempted=c['cycle_id'],attempts_count=1,parser_version='old')
    assert plan(q,c,1)[0][1]['url']!=old['url']


def test_no_oa_403_429_and_identity_failures_are_distinct():
    assert classify_failure(403)[0]=='policy_blocked'
    assert classify_failure(429)[0]=='transient_failure'
    assert classify_failure(404)[0]=='permanent_failure_for_url'
    assert classify_failure(error=ValueError('article_identity_mismatch'))[1]=='article_identity_mismatch'


def document():
    d=ArticleDocument('doi:10.1002/test','https://example.org/oa.pdf','a'*64)
    d.identity={'verification':'matched'}
    return d


def test_independent_fields_can_have_different_pages_and_sections():
    d=document()
    d.add('We measured firm age as the number of years since incorporation.',3,'measures')
    d.add('Our dependent variable, firm age, is reported for each observation.',4,'dependent variable')
    d.add('The sample data from Compustat cover the period from 2001 to 2015. We estimate ordinary least squares.',7,'data')
    r=extraction(d);validate_record(r)
    v=r['variables'][0]
    assert v['fields']['role']['value']=='dependent'
    assert r['fields']['sample_period']['value']==[2001,2015]
    assert r['fields']['data_source']['value']==['Compustat']
    ev={e['evidence_id']:e for e in r['evidence']}
    assert ev[v['fields']['role']['evidence_ids'][0]]['page']==4
    assert ev[r['fields']['sample_period']['evidence_ids'][0]]['page']==7
    assert set(v['fields'])==set(VARIABLE_FIELDS) and set(r['fields'])==set(PAPER_FIELDS)


def test_normalized_by_is_inferred_ratio_never_original_formula():
    d=document();d.add('We measured startup quality as patent applications in each state-year normalized by the number of new entrants.',12,'measures')
    r=extraction(d);v=r['variables'][0]['fields']
    assert v['formula']['value'] is None
    assert v['inferred_ratio']['status']=='inferred_not_original_formula'
    assert 'new entrants' in v['denominator']['value']
    assert 'state-year' in v['level_of_analysis']['value']
    assert v['proxy']['value']!='number of new entrants'


def test_measurement_formula_requires_literal_expression_for_named_variable():
    d=document();d.add('We measured firm age as the number of years since incorporation.',2,'measures')
    d.add('firm age = current year - incorporation year',4,'appendix','equation')
    r=extraction(d)
    assert r['variables'][0]['fields']['formula']['value']=='firm age = current year - incorporation year'


def test_same_name_different_measure_specs_are_not_collapsed():
    d=document();d.add('We measured performance as return on assets for the main specification.',2,'measures')
    d.add('We measured performance as return on equity in the alternative specification.',8,'appendix')
    r=extraction(d)
    assert len(r['variables'])==2
    assert len({v['variable_id'] for v in r['variables']})==2


def test_reference_citation_is_not_a_data_source_claim():
    d=document();d.add('We measured firm age as the number of years since incorporation.',2,'measures')
    d.add('Compustat analysis and ordinary least squares from 2000 to 2010.',12,'references')
    r=extraction(d)
    assert r['fields']['data_source']['value'] is None


def test_lag_of_another_variable_is_not_assigned_to_named_measure():
    d=document();d.add('We measured firm age as the number of years since incorporation. Employment is lagged by two years.',2,'measures')
    assert extraction(d)['variables'][0]['fields']['lag']['value'] is None


def test_hypothesis_support_is_not_significance_and_negative_coefficient_is_not_support():
    d=document();d.add('Hypothesis 1: Firm age has a positive relationship with revenue.',3,'hypotheses')
    d.add('Hypothesis 1 was not supported by the results.',9,'results')
    r=extraction(d)
    assert r['findings'][0]['reported_support']=='not_supported'
    assert r['findings'][0]['significance']=='unknown'
    assert r['findings'][0]['hypothesis_id']==r['hypotheses'][0]['hypothesis_id']


def test_table_models_and_numeric_cells_keep_own_locators():
    d=document()
    d.add('We measured firm age as the number of years since incorporation.',2,'measures')
    for row,cells in enumerate([['Variable','Model 1','Model 2'],['firm age','0.24**','-0.10']]):
        for column,value in enumerate(cells):d.add(value,8,'results','table_cell',table='Table 3',row=row,column=column,headers=['Variable','Model 1','Model 2'])
    r=extraction(d);validate_record(r)
    assert len(r['models'])==2 and len(r['estimates'])==2
    assert r['estimates'][0]['significance']=='unknown'
    assert r['estimates'][0]['hypothesis_support']=='unknown'
    assert r['estimates'][0]['reported_estimate']==.24
    assert r['estimates'][0]['coefficient'] is None
    assert all(e['row'] is not None and e['column'] is not None for e in r['evidence'] if e['table'])


def test_robustness_heading_is_not_a_successful_robustness_result():
    d=document();d.add('Robustness checks',9,'robustness','heading')
    d.add('We conduct robustness checks using an alternative sample.',9,'robustness')
    r=extraction(d)
    assert r['checks'][0]['result']=='unknown'


@pytest.mark.parametrize('mutation',['hash','source','relation','missing'])
def test_gate_rejects_tampered_or_dangling_field_evidence(mutation):
    d=document();d.add('We measured firm age as the number of years since incorporation.',2,'measures')
    r=extraction(d)
    if mutation=='hash':r['evidence'][0]['quote_hash']='bad'
    if mutation=='source':r['evidence'][0]['source_hash']='b'*64
    if mutation=='relation':r['variables'][0]['fields']['role']={'value':'dependent','status':'source_grounded','reason':None,'evidence_ids':['nonexistent']}
    if mutation=='missing':r['variables'][0]['fields'].pop('lag')
    with pytest.raises(ValueError):validate_record(r)


def test_pdf_two_columns_tables_and_appendix_are_structured():
    import fitz
    pdf=fitz.open();page=pdf.new_page()
    page.insert_text((50,45),'A grounded research study of firm age')
    page.insert_text((50,65),'Alice Author doi:10.1002/test')
    page.insert_textbox((40,100,270,700),'MEASURES\n'+('We measure firm age using years since incorporation. '*35),fontsize=9)
    page.insert_textbox((315,100,560,700),'APPENDIX\n'+('Additional specification information is reported here. '*35),fontsize=9)
    content=pdf.tobytes();pdf.close()
    d=parse_article({'paper_id':'doi:10.1002/test','doi':'10.1002/test','title':'A grounded research study of firm age','authors':['Alice Author']},content,'application/pdf',{'source_url':'https://example.org/a.pdf','source_hash':digest(content)})
    assert d.identity['verification']=='matched' and len(d.blocks)>2
    assert 'image_equations_not_ocr' in d.gaps


def test_html_definition_table_has_cell_evidence_and_equation():
    html=('<article><h1>A grounded research study of firm age</h1><p>Alice Author doi:10.1002/test</p><h2>Measures</h2><table><tr><th>Variable</th><th>Definition</th></tr><tr><td>Firm age</td><td>Years since incorporation</td></tr></table><h2>Appendix</h2><math>Firm age = current year - founding year</math><p>'+('The sample describes firm observations and detailed methodology. '*45)+'</p></article>').encode()
    d=parse_article({'paper_id':'doi:10.1002/test','doi':'10.1002/test','title':'A grounded research study of firm age','authors':['Alice Author']},html,'text/html',{'source_url':'https://example.org/a','source_hash':digest(html)})
    r=extraction(d)
    assert r['variables'] and any(e['table'] for e in r['evidence'])
    assert r['variables'][0]['fields']['formula']['value'] is not None


def test_failed_parser_upgrade_reopens_after_other_unvisited_sources():
    from pipeline.article import PARSER_VERSION
    p,e=fixtures();q,c=seed(p,e,[])
    source=q[0]['sources'][0]
    source.update(state='permanent_failure_for_url',error_class='parse_or_extraction_failure:ValueError',
        cycle_attempted=c['cycle_id'],last_parser_attempt='previous',next_retry_at='2099-01-01T00:00:00+00:00')
    assert plan(q,c,1)[0][1] is not source
    assert source in [s for _,s in plan(q,c,100)]
    source['last_parser_attempt']=PARSER_VERSION
    assert source not in [s for _,s in plan(q,c,100)]


def test_two_real_tick_boundaries_resume_and_isolate_failure(tmp_path,monkeypatch):
    from pipeline import cli,crawl
    monkeypatch.setattr(cli,'DATA',tmp_path/'data');monkeypatch.setattr(cli,'ROOT',tmp_path)
    p,e=fixtures();p=p[:1];e=e[:1]
    for name,rows in [('papers.jsonl',p),('enrichment.jsonl',e)]:cli.write(cli.DATA/name,cli.lines(rows))
    monkeypatch.setattr(crawl,'discover',lambda q,c,f:(q,c))
    def parse(paper,content,kind,receipt):
        d=ArticleDocument(paper['paper_id'],receipt['source_url'],receipt['source_hash']);d.identity={'verification':'matched'}
        d.add('We measured firm age as the number of years since incorporation.',3,'measures');return d
    monkeypatch.setattr(crawl,'parse_article',parse)
    class Fetcher:
        requests=0
        def __init__(self,status):self.status=status
        def fetch(self,url):
            self.requests+=1
            return httpx.Response(self.status,request=httpx.Request('GET',url),content=b'%PDF-test',headers={'content-type':'application/pdf','retry-after':'3600'}),[url]
        def close(self):pass
    first=crawl.tick('exhaust_oa',1,10,10,fetcher=Fetcher(429))
    assert first['source_unvisited']==1 and first['parsed_papers']==0
    second=crawl.tick('continue_oa',1,10,10,fetcher=Fetcher(200))
    assert second['source_unvisited']==0 and second['parsed_papers']==1 and second['round_complete']
    q=cli.read('crawl_queue.jsonl');assert len(q[0]['source_attempts'])==2
    assert q[0]['sources'][0]['state']=='transient_failure'
    crawl.tick('pause_oa',fetcher=Fetcher(200))
    assert cli.read('crawl_control.jsonl')[0]['state']=='paused'
    assert cli.read('research_records.jsonl')[0]['variables']


def test_independent_evaluation_counts_unknowns_as_misses_and_period_as_pair():
    from pathlib import Path
    from pipeline.evaluate import ROOT,canonical,metrics
    gold=json.loads((ROOT/'evaluation/gold.json').read_text(encoding='utf-8'))
    result=json.loads((ROOT/'evaluation/results.json').read_text(encoding='utf-8'))
    assert len({p['doi'] for p in gold['papers']})==15
    assert all(p['doi']!='10.1002/smj.3340' for p in gold['papers'])
    assert canonical('2001–2015','sample_period')=='2001–2015'
    assert metrics(2,1,3)['recall']==.4
    for field,counts in result['fields'].items():
        rows=[d for d in result['details'] if d['field']==field]
        tp=sum(len(set(d['expected'])&set(d['predicted'])) for d in rows)
        fp=sum(len(set(d['predicted'])-set(d['expected'])) for d in rows)
        fn=sum(len(set(d['expected'])-set(d['predicted'])) for d in rows)
        assert {k:counts[k] for k in ['tp','fp','fn']}=={'tp':tp,'fp':fp,'fn':fn}
    assert result['other_fields_accuracy'] is None
