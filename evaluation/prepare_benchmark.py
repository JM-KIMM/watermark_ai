"""Prepare the 2026 tax-accountant first-session A-form paired experiment."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repository root
import hashlib
import json
from pathlib import Path
import pymupdf as fitz
from question_marks import detect_questions
from watermark import build

ROOT=Path(__file__).resolve().parent.parent


def main():
    source=next(ROOT.glob('2026*1교시*.pdf'))
    output=ROOT/'outputs'/'benchmark_input';output.mkdir(parents=True,exist_ok=True)
    # Manually transcribed and visually checked against Q-Net's final key, page 1.
    rows=[
        [1,4,3,5,3],[4,2,1,4,5],[3,3,1,[3,5],3],[2,3,3,1,2],
        [2,4,3,1,2],[4,4,3,5,2],[4,4,5,1,3],[1,4,5,5,2],
        [3,2,3,3,3],[2,4,5,2,4],[4,2,[1,2,3,4,5],1,1],[4,2,2,5,5],
        [1,5,1,5,1],[5,2,2,4,3],[5,4,1,1,4],[4,5,5,5,3],
    ]
    answers={str(i+1):v for i,v in enumerate(v for row in rows for v in row)}
    with fitz.open(source) as doc:
        pages={str(i+1):sorted(set(q['number'] for q in detect_questions(p)),key=int) for i,p in enumerate(doc)}
    seen=set()
    for page, questions in pages.items():
        pages[page]=[q for q in questions if q not in seen]
        seen.update(questions)
    ids=[q for qs in pages.values() for q in qs]
    if len(ids)!=80 or set(ids)!=set(answers):raise ValueError('Expected exactly 80 unique exam questions')
    official=ROOT/'outputs'/'official_answers.pdf'
    key=dict(exam='2026 tax accountant session 1, A form',question_type='multiple_choice',
        source_url='https://www.q-net.or.kr/cst003.do?artlSeq=5272129&boardId=Q004&gId=22&gSite=L&id=cst00302&menuType=cst00310',
        official_pdf_sha256=hashlib.sha256(official.read_bytes()).hexdigest(),
        transcription='Manually checked official image, page 1; Q14 accepts 3/5, Q53 accepts all choices.',pages=pages,answers=answers)
    (output/'key.json').write_text(json.dumps(key,ensure_ascii=False,indent=2),encoding='utf-8')
    for level in (2,3):
        target=output/f'level{level}.pdf'
        if not target.exists():
            report=build(source,target,intensity=level,font_mode='source',size_jitter=.25,
                         prompts_file=ROOT/'prompts_ko.json',math_watermark=False,qr_captions=False,progress=lambda i,n:print(level,i,n,flush=True))
            print('QR',sum(m['qr_status']=='placed' for p in report['pages'] for m in p['question_marks']),flush=True)
    (output/'source_path.txt').write_text(str(source),encoding='utf-8')
    control=output/'blank_border.pdf'
    if not control.exists():
        with fitz.open(source) as doc,fitz.open() as out:
            for i,p in enumerate(doc):
                q=out.new_page(width=p.rect.width+40,height=p.rect.height+40)
                q.show_pdf_page(fitz.Rect(20,20,p.rect.width+20,p.rect.height+20),doc,i)
            out.save(control)


if __name__=='__main__':main()
