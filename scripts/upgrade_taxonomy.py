"""One-time, auditable v1→v2 migration. Does not recode any paper."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT/'data'
old_path = DATA/'ontology.yaml'
old = json.loads(old_path.read_text(encoding='utf-8'))
if isinstance(old, dict):
    raise SystemExit('Taxonomy already migrated; edit through versioned review, not this script.')
history = DATA/'taxonomy_versions'; history.mkdir(exist_ok=True)
(history/'1.0.0.json').write_text(json.dumps({'version':'1.0.0','origin':'custom_research','is_official_smj_taxonomy':False,'status':'deprecated','nodes':old,'note':'原始十二類為 Atlas 初步工作分類，非 SMJ、SMS 或 AOM 官方分類。'},ensure_ascii=False,indent=2),encoding='utf-8')
V='2.0.0'
SMS='https://www.strategicmanagement.net/connect-participate/interest-groups-communities/'
AOM='https://www.aom.org/divisions-and-interest-groups/strategic-management/'
NAG='https://doi.org/10.1002/smj.615'
sources=[
 dict(id='SMS-IG-2026',organization='Strategic Management Society',title='Interest Groups & Communities',url=SMS,accessed_at='2026-11-07',source_type='official_academic_organization',evidence_locator='Interest Groups listings; exclude Research Methods and Teaching Communities',supports='SMS IG 英文名稱；非 SMJ 論文分類、非官方中文譯名或四層架構。'),
 dict(id='AOM-STR-2026',organization='Academy of Management, Strategic Management Division',title='Strategic Management (STR): Domain Statement',url=AOM,accessed_at='2026-11-07',source_type='official_academic_organization',evidence_locator='Domain Statement',supports='研究範圍涵蓋檢查；不授權或驗證 Atlas 的分類對應。'),
 dict(id='NAG-2007',authors=['Nag, R.','Hambrick, D. C.','Chen, M.-J.'],year=2007,title='What is strategic management, really? Inductive derivation of a consensus definition of the field',journal='Strategic Management Journal',volume='28',issue='9',pages='935–955',doi='10.1002/smj.615',url=NAG,accessed_at='2026-11-07',source_type='academic_publication',evidence_locator='Publisher Abstract; bibliographic record',supports='學者調查與跨領域學者明示定義相互對照的研究取徑；本文未提出本網站四層分類。未據摘要宣稱重現全文的具體編碼程序。'),
 dict(id='ATLAS-METHOD',organization='SMJ Research Atlas',title='Taxonomy Methodology v2',url='https://oliver0923-hub.github.io/smj-research-atlas/taxonomy-methodology/',accessed_at='2026-11-07',source_type='custom_research',evidence_locator='Four-level design, proposal rules and human review protocol',supports='Atlas 自訂譯名、層級、研究主題、構念詞彙、理論維度與演算法規則。')]
domains=[
 ('SMS-BEH','行為策略','Behavioral Strategy'),('SMS-COMP','競爭策略','Competitive Strategy'),
 ('SMS-COOP','合作策略','Cooperative Strategies'),('SMS-CORP','公司策略','Corporate Strategy'),
 ('SMS-ENT','創業與策略','Entrepreneurship and Strategy'),('SMS-GLOBAL','全球策略','Global Strategy'),
 ('SMS-KI','知識與創新','Knowledge and Innovation'),('SMS-STAKE','利害關係人策略','Stakeholder Strategy'),
 ('SMS-HC','策略人力資本','Strategic Human Capital'),('SMS-LG','策略領導與治理','Strategic Leadership & Governance'),
 ('SMS-PRACTICE','策略實踐','Strategy Practice'),('SMS-PROCESS','策略程序','Strategy Process')]
nodes=[]
for ident,zh,en in domains:
    nodes.append(dict(id=ident,level='domain',label_zh=zh,label_en=en,official_label_en=en,parent_ids=[],origin='official_academic_organization',source_ids=['SMS-IG-2026'],method='SMS IG label transcription; placement as Atlas Level 1 is an editorial adaptation',translation_origin='custom_research',hierarchy_origin='custom_research',version=V,review_status='needs_review',reviewer=None,reviewed_at=None,synonyms=[],description='SMS Interest Group 名稱參照；中文譯名與 Level 1 編排為 Atlas 編製。非 SMJ 官方 taxonomy。'))
topics=[
 ('TOP-BEH','認知、學習與注意力','Cognition, learning and attention',['SMS-BEH','SMS-PROCESS'],['managerial attention','organizational learning','performance feedback','cognition','aspiration']),
 ('TOP-COMP','競爭互動與產業動態','Competitive interaction and industry dynamics',['SMS-COMP'],['competitive dynamics','rivalry','industry dynamics']),
 ('TOP-MMC','多市場接觸','Multimarket contact',['SMS-COMP','SMS-COOP'],['multimarket contact','multimarket rivalry','mutual forbearance']),
 ('TOP-ALL','聯盟與組織間網絡','Alliances and interorganizational networks',['SMS-COOP'],['alliance','alliances','interorganizational networks']),
 ('TOP-BOUND','企業邊界與垂直整合','Firm boundaries and vertical integration',['SMS-CORP','SMS-COMP'],['vertical integration','firm boundaries','outsourcing']),
 ('TOP-MNA','併購、撤資與多角化','M&A, divestitures and diversification',['SMS-CORP'],['acquisition','acquisitions','mergers','divestiture','divestitures','diversification']),
 ('TOP-RESOURCE','資源配置與能力','Resource allocation and capabilities',['SMS-CORP','SMS-KI','SMS-COMP'],['resource allocation','capabilities','resource redeployment','resource slack']),
 ('TOP-ENT','創業與新事業','Entrepreneurship and new ventures',['SMS-ENT'],['entrepreneurship','entrepreneurial','new ventures']),
 ('TOP-GLOBAL','跨國策略與地緣政治','International strategy and geopolitics',['SMS-GLOBAL'],['multinational','internationalization','geopolitics','cross border']),
 ('TOP-INNOV','知識搜尋、創新與更新','Knowledge search, innovation and renewal',['SMS-KI'],['innovation','knowledge search','patents','strategic renewal']),
 ('TOP-NONMARKET','非市場策略與政策','Nonmarket strategy and policy',['SMS-STAKE','SMS-GLOBAL','SMS-CORP'],['nonmarket','political strategy','government policy','regulation']),
 ('TOP-STAKE','利害關係人與社會結果','Stakeholders and social outcomes',['SMS-STAKE'],['stakeholder','stakeholders','corporate social','sustainability']),
 ('TOP-HC','人才流動與人力資本','Mobility and human capital',['SMS-HC'],['human capital','employee mobility','inventor','inventors','turnover']),
 ('TOP-LEAD','高階主管與策略領導','Executives and strategic leadership',['SMS-LG'],['ceo','top management','upper echelons','executive']),
 ('TOP-GOV','公司治理','Corporate governance',['SMS-LG','SMS-CORP'],['corporate governance','boards','board of directors']),
 ('TOP-PRACTICE','策略實踐與工具','Strategy practice and tools',['SMS-PRACTICE'],['strategy as practice','strategy tools','strategizing']),
 ('TOP-PROCESS','策略形成、執行與變革','Formulation, implementation and change',['SMS-PROCESS','SMS-PRACTICE'],['strategy formulation','strategy implementation','strategic planning','strategic change']),
 ('TOP-DIGITAL','平台、生態系與商業模式','Platforms, ecosystems and business models',['SMS-COMP','SMS-COOP','SMS-KI'],['platform','platforms','ecosystem','ecosystems','business model','business models']),
 ('TOP-INPUT','關鍵投入與資源依賴','Critical inputs and resource dependencies',['SMS-CORP','SMS-COOP'],['supplier','suppliers','resource dependence','supply chain']),
 ('TOP-OUTCOME','企業績效與異質性','Firm performance and heterogeneity',['SMS-COMP','SMS-CORP'],['firm performance','performance heterogeneity','competitive heterogeneity'])]
def custom(ident,level,zh,en,parents,phrases=()):
    return dict(id=ident,level=level,label_zh=zh,label_en=en,parent_ids=parents,origin='custom_research',source_ids=['ATLAS-METHOD','AOM-STR-2026'],method='Atlas editorial working vocabulary and nonexclusive scope mapping; not an official organization subdivision',version=V,review_status='needs_review',reviewer=None,reviewed_at=None,synonyms=[],match_phrases=list(phrases),description='自訂工作詞彙與編排，待研究者審核；不表示任何論文已採用此構念或衡量。')
for ident,zh,en,parents,phrases in topics:nodes.append(custom(ident,'research_topic',zh,en,parents,phrases))
constructs=[('CON-ATTENTION','管理者注意力','Managerial attention',['TOP-BEH']),('CON-SLACK','資源寬裕','Resource slack',['TOP-RESOURCE']),('CON-DEPENDENCE','依賴不對稱','Dependence asymmetry',['TOP-INPUT']),('CON-OVERLAP','市場重疊程度','Market overlap',['TOP-MMC']),('CON-ACQEXP','併購經驗','Acquisition experience',['TOP-MNA']),('CON-PERFORMANCE','企業績效','Firm performance',['TOP-OUTCOME'])]
for ident,zh,en,parents in constructs:nodes.append(custom(ident,'construct',zh,en,parents))
theories=[('TH-BTF','企業行為理論','Behavioral Theory of the Firm',['behavioral theory of the firm']),('TH-ABV','注意力基礎觀點','Attention-Based View',['attention based view']),('TH-RDT','資源依賴理論','Resource Dependence Theory',['resource dependence theory']),('TH-RBV','資源基礎觀點','Resource-Based View',['resource based view']),('TH-TCE','交易成本經濟學','Transaction Cost Economics',['transaction cost economics','transaction cost theory']),('TH-AGENCY','代理理論','Agency Theory',['agency theory'])]
for ident,zh,en,phrases in theories:
    node=custom(ident,'theory',zh,en,[],phrases);node['source_ids']=['ATLAS-METHOD'];node['method']='Independent Atlas theory tagging vocabulary; not SMS IGs or a hierarchy level';nodes.append(node)
matrix=[
 ('decision_processes',['TOP-BEH','TOP-PROCESS','TOP-PRACTICE']),('firm_boundaries',['TOP-BOUND']),('governance',['TOP-GOV']),('corporate_strategy',['TOP-MNA','TOP-RESOURCE']),('economics_and_industry_dynamics',['TOP-COMP']),('nonmarket_and_policy',['TOP-NONMARKET']),('innovation_and_renewal',['TOP-INNOV']),('alliances_networks_ma',['TOP-ALL','TOP-MNA']),('business_models',['TOP-DIGITAL']),('competitive_cooperative_interactions',['TOP-COMP','TOP-ALL','TOP-MMC']),('resources_capabilities_critical_inputs',['TOP-RESOURCE','TOP-INPUT']),('leadership_upper_echelons',['TOP-LEAD']),('performance_and_heterogeneity',['TOP-OUTCOME'])]
tax=dict(version=V,is_official_smj_taxonomy=False,title_zh='Atlas 研究分類：以 SMS Interest Groups 為 Level 1 參照',checked_at='2026-11-07',levels=['domain','research_topic','construct','operational_variable'],independent_dimensions=['theory'],sources=sources,nodes=nodes,
 scope_check=dict(source_id='AOM-STR-2026',mapping_origin='custom_research',method='Editorial coverage checklist, not AOM endorsement or exhaustiveness certification',review_status='needs_review',mappings=[dict(scope=s,topic_ids=t) for s,t in matrix],cross_cutting_facets=['level_of_analysis','geography','industry','method','outcome','government_policy'],note='組織為常見分析層次；個人、團隊、生態系、市場、地理與產業等層次保留獨立 facets，不強行當成 Domain。'),
 migration=dict(from_version='1.0.0',automatic_paper_reclassification=False,legacy_origin='custom_research',instruction='保留 legacy_domain_codes。舊代碼不能視為 SMS 代碼；逐篇人工審核後才新增 v2 assignments。'),
 methodology=dict(approach='deductive organizational anchors + inductive lexical proposals + human adjudication',inspiration_source_id='NAG-2007',claim='Atlas 自訂方法，未宣稱重現 Nag et al. 的原研究或取得 SMS/AOM/SMJ 認可。'))
old_path.write_text(json.dumps(tax,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(history/'2.0.0.json').write_text(json.dumps(tax,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
(DATA/'classifications.jsonl').touch(exist_ok=True)
print('Archived v1; wrote v2 working taxonomy; no paper reclassification or human approval performed.')
