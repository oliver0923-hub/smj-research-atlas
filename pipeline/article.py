"""Private structured ArticleDocument. Only evidence locators are published."""
import hashlib
import re
from dataclasses import dataclass, field

PARSER_VERSION = 'article-document-4.0'


def digest(text):
    return hashlib.sha256(text.encode() if isinstance(text, str) else text).hexdigest()


def norm(text):
    return re.sub(r'\s+', ' ', text.replace('\u00ad', '')).strip()


SECTIONS = re.compile(r'^(?:\d+(?:\.\d+)*[. ]+)?(abstract|introduction|theor\w*(?: background)?|hypothes\w*(?: development)?|propositions?|methods?|methodology|research (?:design|methods?)|empirical (?:setting|analysis|strategy)(?: and data)?|data(?: and (?:sample|methods?|measures?))?|sample|measures?|measurement|variables?|dependent variables?|independent variables?|control variables?|moderators?|mediators?|results?|analysis|robustness(?: checks)?|sensitivity(?: analysis)?|discussion|conclusion\w*|limitations?|appendi[xces]+.*|supporting information|supplement\w*.*|references|bibliography)\s*[:.]?$', re.I)


@dataclass
class ArticleDocument:
    paper_id: str
    source_url: str
    source_hash: str
    blocks: list[dict] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    identity: dict = field(default_factory=dict)
    parser_version: str = PARSER_VERSION

    def add(self, text, page, section='unknown', kind='paragraph', **locator):
        text = norm(text)
        if not text:
            return
        self.blocks.append(dict(block_id='b'+str(len(self.blocks)), text=text, page=page,
                                section=section, kind=kind, block_hash=digest(text), **locator))

    def coverage(self):
        return dict(pages=len({b['page'] for b in self.blocks}), blocks=len(self.blocks),
                    sections=sorted({b['section'] for b in self.blocks}),
                    tables=sum(b['kind']=='table_cell' for b in self.blocks),
                    equations=sum(b['kind']=='equation' for b in self.blocks),
                    appendix_scanned=any('appendi' in b['section'] for b in self.blocks),
                    supplements='not_fetched_unless_in_same_document', gaps=self.gaps,
                    references_excluded=True)


def from_pages(paper, pages, receipt):
    doc = ArticleDocument(paper['paper_id'], receipt['source_url'], receipt['source_hash'])
    section = 'unknown'
    for page in pages:
        # This migration adapter cannot recover layout that was absent from v3 caches.
        for para in re.split(r'\n\s*\n|(?<=\.)\n', page['text']):
            lines = para.splitlines()
            if lines and SECTIONS.fullmatch(norm(lines[0])):
                section = norm(lines[0]).lower()
            doc.add(para, page['page'], section)
    doc.gaps = ['legacy_text_layout_not_available', 'table_geometry_not_parsed', 'image_equations_not_ocr']
    return doc


def parse_article(paper, content, content_type, receipt):
    doc = ArticleDocument(paper['paper_id'], receipt['source_url'], receipt['source_hash'])
    section = 'unknown'
    if content.startswith(b'%PDF'):
        import fitz
        with fitz.open(stream=content, filetype='pdf') as pdf:
            for number, page in enumerate(pdf, 1):
                blocks = [b for b in page.get_text('blocks') if len(b)>6 and b[6]==0]
                mid = page.rect.width/2
                narrow = [b for b in blocks if b[2]-b[0]<page.rect.width*.57]
                two = any(b[0]<mid*.7 for b in narrow) and any(b[0]>mid for b in narrow)
                if two:
                    blocks.sort(key=lambda b:(0 if b[2]-b[0]>page.rect.width*.7 and b[1]<100 else 1 if b[0]<mid else 2, b[1], b[0]))
                else:
                    blocks.sort(key=lambda b:(b[1], b[0]))
                for b in blocks:
                    text = b[4]
                    # Retain headings independently so downstream roles have explicit scope.
                    for part in re.split(r'\n\s*\n', text):
                        lines = part.splitlines()
                        if lines and SECTIONS.fullmatch(norm(lines[0])):
                            section = norm(lines[0]).lower()
                            doc.add(lines[0], number, section, 'heading', bbox=list(b[:4]))
                            part='\n'.join(lines[1:])
                        kind='equation' if re.search(r'[=∑Σ]',part) and len(norm(part))<350 else 'paragraph'
                        doc.add(part,number,section,kind,bbox=list(b[:4]))
                try:
                    tables = page.find_tables().tables
                    for ti,t in enumerate(tables):
                        matrix=t.extract()
                        for row,cells in enumerate(matrix):
                            for column,value in enumerate(cells):
                                if value:
                                    doc.add(value,number,section,'table_cell',table=f'p{number}-t{ti+1}',row=row,column=column,
                                            headers=[norm(x or '') for x in matrix[0]],bbox=list(t.bbox))
                except Exception as exc:
                    doc.gaps.append(f'table_geometry_failed_page_{number}:{type(exc).__name__}')
                if not blocks:
                    doc.gaps.append(f'page_{number}_no_extractable_text_requires_ocr')
        doc.gaps += ['image_equations_not_ocr', 'unruled_tables_may_require_layout_review']
    elif 'html' in content_type:
        from bs4 import BeautifulSoup
        soup=BeautifulSoup(content,'html.parser')
        body=soup.find('article') or soup.find('main')
        if body is None:
            raise ValueError('not_article_html')
        headings=[norm(h.get_text()).lower() for h in body.find_all(['h2','h3','h4','h5'])]
        study=any(re.search(r'\b(?:methods?|measures?|measurement|hypothes\w*|theor\w*|sample|data)\b',h) for h in headings)
        substantive=any(re.search(r'\b(?:results?|discussion|conclusions?|appendix|appendices)\b',h) for h in headings)
        if not (study and substantive):raise ValueError('not_article_html_metadata_landing')
        for node in body.find_all(['script','style','nav','header','footer','aside','form']):node.decompose()
        for node in body.find_all(['h1','h2','h3','h4','h5','p','table','math']):
            if node.find_parent('table'):continue
            if node.name.startswith('h'):
                section=norm(node.get_text()).lower();doc.add(node.get_text(),None,section,'heading')
            elif node.name=='table':
                rows=node.find_all('tr');headers=[norm(x.get_text()) for x in rows[0].find_all(['th','td'])] if rows else []
                table=node.get('id') or 'html-table-'+str(len(doc.blocks))
                for row,tr in enumerate(rows):
                    for column,cell in enumerate(tr.find_all(['td','th'])):
                        doc.add(cell.get_text(' ',strip=True),None,section,'table_cell',table=table,row=row,column=column,headers=headers)
            else:doc.add(node.get_text(' ',strip=True),None,section,'equation' if node.name=='math' else 'paragraph')
        doc.gaps=['external_supplements_not_in_html']
    else:
        raise ValueError('unsupported_document_format')
    text=' '.join(b['text'] for b in doc.blocks if b['kind']!='table_cell')
    begin=text[:18000].lower()
    words=set(re.findall(r'[a-z]{4,}',re.sub('<[^>]+>','',paper['title']).lower()))
    score=len(words & set(re.findall(r'[a-z]{4,}',begin)))/len(words) if words else 0
    authors=[a.split()[-1].lower() for a in paper.get('authors',[]) if a.split()]
    doi=paper['doi'].lower() in begin
    author=any(a in begin for a in authors)
    if not ((doi and score>=.45) or (score>=.70 and author)):
        raise ValueError('article_identity_mismatch')
    if len(text)<2500:
        raise ValueError('not_enough_article_text')
    doc.identity=dict(doi_visible=doi,title_token_overlap=round(score,3),author_visible=author,verification='matched')
    return doc
