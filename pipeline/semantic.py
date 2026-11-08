"""Conservative weak supervision for SMJ title / abstract concept mentions.

These context signals are *candidate* multi-label suggestions, NEVER claims
that a paper uses a theory or operationalizes the underlying construct.

No opaque model, embeddings download, API key, or copyrighted corpus
redistribution required. Feature values only (no full abstract) persist.
"""
import re
from .taxonomy import text_key

FEATURE_VERSION="smj-context-features-v1"
# Avoid single generic words such as 'innovation', 'knowledge', 'strategy',
# 'performance', 'theory' and 'firms'. Each indicator is multiword and
# associated with an exact pre-existing taxonomy ID.
CONSTRUCT_CONTEXT={
"CON-ATTENTION":["managerial cognition","managerial focus","executive attention","attentional focus"],
"CON-SLACK":["financial slack","unabsorbed slack","absorbed slack","excess organizational resources"],
"CON-DEPENDENCE":["power asymmetry","dependence imbalance","asymmetric interdependence"],
"CON-OVERLAP":["common markets","market commonality","overlapping markets","competitive overlap"],
"CON-ACQEXP":["prior acquisitions","acquisition learning","serial acquirer","prior merger experience"],
"CON-PERFORMANCE":["financial performance","operating performance","return on assets","return on equity","abnormal stock returns","economic performance"],
"CON-ABSCAP":["knowledge absorption","absorptive capability","absorptive abilities"],
"CON-DYNCAP":["capability reconfiguration","capability renewal","capability development"],
"CON-KNOWDIST":["cognitive distance","scientific distance","knowledge relatedness","technological relatedness"],
"CON-KNOWSPILL":["technological spillovers","interfirm knowledge spillovers","knowledge diffusion"],
"CON-EXPLORATION":["explorative innovation","exploratory innovation","exploratory search"],
"CON-EXPLOITATION":["exploitative innovation","exploitative search","exploitation activities"],
"CON-PERFFDBK":["performance shortfalls","performance relative to aspirations","aspiration performance feedback"],
"CON-ASPIRGAP":["performance below aspiration","performance above aspiration","aspiration discrepancy"],
"CON-ENVUNCERT":["market uncertainty","demand uncertainty","regulatory uncertainty","policy uncertainty","environmental turbulence"],
"CON-COMPIN":["competitive pressure","competitive rivalry","intensity of competition","competitive threats"],
"CON-MMC":["cross market contact","multimarket rivalry","multi market contact"],
"CON-MUTFORB":["competitive forbearance","mutual restraint"],
"CON-NETCENTRAL":["structural holes","brokerage position","network brokerage"],
"CON-NETEMBED":["relational embeddedness","embedded ties","network ties"],
"CON-ALLIANCEEXP":["alliance learning","repeated alliances","prior alliances"],
"CON-ALLIANCEDIV":["alliance portfolio size","partner diversity","portfolio of alliances"],
"CON-ASSETSPEC":["relationship specific investments","specific asset investments","relationship specific assets"],
"CON-ACQPERF":["merger performance","post merger performance","acquirer returns","cumulative abnormal returns"],
"CON-POSTMA":["postmerger integration","merger integration","integration process"],
"CON-DIVERSIFICATION":["corporate diversification","business diversification","diversification strategy"],
"CON-MULTINAT":["internationalization degree","foreign sales ratio","international expansion"],
"CON-GEOPOLRISK":["political risk exposure","geopolitical tensions","international political risk"],
"CON-POLCONN":["government ties","political embeddedness","political access"],
"CON-CSR":["corporate social performance","socially responsible practices"],
"CON-BOARDIND":["outside directors","board monitoring","independent board members"],
"CON-CEOOVCONF":["executive overconfidence","managerial hubris","ceo hubris"],
"CON-TMTDIV":["team heterogeneity","executive team diversity","top management heterogeneity"],
"CON-EXECINCENT":["executive pay","stock based compensation","equity based incentives"],
"CON-MANHC":["managerial experience","executive skills","general managerial ability"],
"CON-LABMOB":["employee turnover","worker mobility","inventor mobility","talent mobility"],
"CON-HCDIV":["workforce diversity","employee skill diversity"],
"CON-SUPDEPEND":["supplier power","dependency on suppliers","supplier concentration"],
"CON-CUSTCONC":["customer dependency","buyer power","customer power"],
"CON-NETEFF":["indirect network effects","cross side network effects","platform network externalities"],
"CON-BMINNOV":["business model change","business model adaptation"],
"CON-ENTORIENT":["risk taking orientation","entrepreneurial posture","proactiveness and innovativeness"],
"CON-STRATCHANGE":["strategic transformation","strategic renewal","strategic adaptation"],
"CON-RDIN":["research and development spending","research and development expenditures","r and d expenditure"],
"CON-PATINTENSITY":["patent applications","patent counts","patent output","patenting activity"],
"CON-INNOVPERF":["innovation output","innovation performance","innovative performance","technological innovation performance"],
"CON-AMBIDEX":["organizational ambidexterity","structural ambidexterity","contextual ambidexterity"],
"CON-DIGTRANS":["digital transformation","digital adoption","digital technology adoption"],
"CON-CEOPOWER":["ceo power","chief executive power","managerial power"],
"CON-BOARDDIV":["board diversity","director diversity","gender diversity on boards"],
"CON-INSTDIST":["institutional distance","regulatory distance","institutional differences"],
"CON-CULTDIST":["cultural distance","cross national cultural distance"],
"CON-RESREDEP":["resource redeployment","redeployment of resources","asset redeployment"],
"CON-STRATSIM":["strategic similarity","strategic relatedness","resource similarity"],
"CON-INNOVNOV":["innovation novelty","novel inventions","technological novelty"],
"CON-FIRMRISK":["firm risk taking","corporate risk taking","organizational risk taking"],
"CON-CAPCOMB":["capability recombination","knowledge recombination","resource recombination"],
}
THEORY_CONTEXT={
# Absence of '-theory/-view' means *related lens candidate* only.
"TH-BTF":["behavioral perspective on firms","behavioral theory perspective","behavioral theory approach"],
"TH-ABV":["attention based perspective","attention based framework","abv perspective"],
"TH-RDT":["resource dependence perspective","resource dependence lens","resource dependence approach"],
"TH-RBV":["resource based perspective","resource based theory","rbv perspective","rbv framework"],
"TH-TCE":["transaction cost perspective","transaction cost lens","transaction cost framework","transaction costs approach"],
"TH-AGENCY":["agency perspective","agency framework","principal agent framework","principal agent theory"],
"TH-DYNAMIC":["dynamic capability perspective","dynamic capability framework"],
"TH-OL":["organizational learning framework","organizational learning lens"],
"TH-KBV":["knowledge based perspective","knowledge based framework"],
"TH-INSTIT":["institutional perspective","institutional logics perspective","institutional pressures framework"],
"TH-UPPER":["upper echelons perspective","upper echelon perspective"],
"TH-REALOPT":["real options reasoning","real option logic","real options perspective"],
"TH-PROSPECT":["prospect theoretic","prospect theory framework"],
"TH-NETWORK":["network perspective","social network lens","network embeddedness perspective"],
"TH-STAKE":["stakeholder perspective","stakeholder framework"],
"TH-GAME":["game theoretic framework","game theoretic approach"],
"TH-SIGNAL":["signaling perspective","signalling perspective","signaling framework"],
"TH-SEARCH":["problemistic search perspective","behavioral search perspective"],
"TH-ORGID":["organizational identity perspective","identity based theory"],
"TH-CONTINGENCY":["contingency perspective","contingency framework"],
"TH-MICRO":["microfoundations lens","microfoundational perspective"],
"TH-IO":["industrial organization perspective","industrial economics perspective"],
"TH-POP":["population ecology perspective","ecological perspective on organizations"],
"TH-LEGIT":["legitimacy perspective","organizational legitimacy lens"],
"TH-SOC-CAP":["social capital perspective","social capital framework"],
"TH-INFO-ASYM":["information asymmetry perspective","asymmetric information framework"],
"TH-RO":["resource orchestration perspective","resource orchestration framework"],
"TH-OIP":["organizational information processing perspective","information processing theory"],
"TH-BA":["behavioral agency perspective","behavioral agency framework"],
}

NEGATION=re.compile(r"\b(?:not|no|neither|without|unrelated to|reject(?:s|ed)?|rather than)\b")


def hits_for_text(text,taxonomy):
    """Candidate signals, with short keyword cues only and algorithmic scores.
    False positives are possible. Source is the whole article abstract hash;
    no substring evidence or quote is independently verified.
    """
    normalized=' '+text_key(text)+' '
    nodes={n['id']:n for n in taxonomy['nodes']}
    result=[]
    for dim,lex in (('construct',CONSTRUCT_CONTEXT),('theory',THEORY_CONTEXT)):
        for term_id,phrases in lex.items():
            if term_id not in nodes or nodes[term_id]['level']!=dim:continue
            for phrase in phrases:
                normalized_phrase=' '+text_key(phrase)+' '
                at=normalized.find(normalized_phrase)
                if at<0:continue
                # Avoid a directly negated/counterfactual term assertion.
                context=normalized[max(0,at-34):at]
                if NEGATION.search(context):continue
                result.append(dict(term_id=term_id,dimension=dim,trigger=phrase,
                                   source='abstract_context',heuristic_score=.62 if dim=='construct' else .54,
                                   method='multiword_contextual_phrase_v1',
                                   status='candidate_not_verified'))
                break
    return result


def title_hits(text,taxonomy):
    result=hits_for_text(text,taxonomy)
    for item in result:item['source']='title_context'
    return result
