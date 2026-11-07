"""Regression tests for source-aligned multi-measure extraction and parsers."""
import pytest
from pipeline.evidence import extract_variables, verify_span, OperationalVariable, EXTRACTION_VERSION
from pipeline.enrich import parse_document


@pytest.fixture
def example():
    paper={'paper_id':'fixture:multi','doi':'10.1002/fixture','title':'Example measures','authors':['Example Author']}
    receipt={'accessible':True,'source_url':'https://example.org/accepted.pdf',
             'source_hash':'a'*64,'checked_at':'2026-11-08'}
    pages=[
        {'page':2,'text':(
            'MEASURES. We measured market overlap as the number of common geographic markets '
            'served by both firms. We measured research intensity as the ratio of research '
            'expenditures to annual sales. This measure appears in the second model.')},
        {'page':3,'text':(
            'VARIABLES. Firm age was calculated as the number of years elapsed since '
            'the firm was founded. We measured market overlap as the number of common '
            'geographic markets served by both firms.')},
    ]
    return paper,receipt,pages


def test_extracts_multiple_distinct_measures_across_pages(example):
    paper,receipt,pages=example
    variables=extract_variables(paper,pages,receipt)
    names={v['variable_label_original'].lower() for v in variables}
    assert names=={'market overlap','research intensity','firm age'}
    assert len({v['variable_id'] for v in variables})==3
    assert all(v['algorithm_version']==EXTRACTION_VERSION for v in variables)
    for variable in variables:
        assert verify_span(variable,pages) is True
        assert OperationalVariable.model_validate(variable)
        assert variable['alignment_verified'] is True
        assert variable['source_hash']==receipt['source_hash']
        assert variable['human_reviewer'] is None


def test_same_name_is_deduplicated_and_ids_stable(example):
    paper,receipt,pages=example
    first=extract_variables(paper,pages,receipt)
    second=extract_variables(paper,pages,receipt)
    assert [v['variable_id'] for v in first]==[v['variable_id'] for v in second]
    assert [v['variable_label_original'].lower() for v in first].count('market overlap')==1


def test_html_main_is_accepted_if_structured_even_without_article():
    html=(
        '<html><body><main><h1>Research methods</h1><h2>Variables and measures</h2>'
        '<p>'+'We measured market overlap as a proportion of shared markets. '*120
        +'</p></main></body></html>'
    )
    pages,version=parse_document(html.encode(),'text/html')
    assert version=='beautifulsoup-v2-structured'
    assert len(pages)==1 and pages[0]['page'] is None
    assert 'market overlap' in pages[0]['text']


def test_landing_page_without_methods_is_not_fulltext():
    html='<html><body><main><h1>Article summary</h1><p>'+'Abstract only. '*800+'</p></main></body></html>'
    with pytest.raises(ValueError,match='Not an inspectable'):
        parse_document(html.encode(),'text/html')


def test_pdf_sort_and_per_page_extraction():
    import fitz
    doc=fitz.open()
    page=doc.new_page()
    page.insert_text((72,72),'MEASURES. We measured firm size as the number of employees.')
    pdf=doc.tobytes();doc.close()
    pages,version=parse_document(pdf,'application/pdf')
    assert version=='pymupdf-v2-reading-order'
    assert len(pages)==1
    assert 'number of employees' in pages[0]['text']
