"""Independent, per-question audit plus local diagnostic inference."""
import base64
import csv
import hashlib
import json
from pathlib import Path
import time
import pymupdf as fitz
from benchmark_local import request

ROOT=Path(__file__).resolve().parent
OUT=ROOT/'outputs'/'grading_audit'


def load_answers(folder,kind,key):
    answers={}
    for page,questions in key['pages'].items():
        record=json.loads((ROOT/'outputs'/folder/f'{kind}-{page}.json').read_text(encoding='utf-8'))
        raw=json.loads(record['raw'])
        if set(raw)!=set(questions): raise ValueError(f'Question mismatch: {folder}/{page}')
        if {q:str(v) for q,v in raw.items()}!=record['answers']:raise ValueError('Parser mismatch')
        for q,v in raw.items():
            if q in answers or type(v) is not int or v not in range(1,6):raise ValueError('Invalid answer')
            answers[q]=v
    return answers


def main():
    OUT.mkdir(parents=True,exist_ok=True)
    key=json.loads((ROOT/'outputs/benchmark_input/key.json').read_text(encoding='utf-8'))
    results={label:load_answers(folder,kind,key) for label,folder,kind in [
        ('original','eval_level2_v2','original'),('level2','eval_level2_v2','watermarked'),
        ('level3','eval_level3_v2','watermarked'),('blank','eval_blank_border_v2','watermarked')]}
    rows=[]
    for q in sorted(key['answers'],key=int):
        expected=key['answers'][q];expected=expected if isinstance(expected,list) else [expected]
        row=dict(question=q,type='multiple_choice',subject='public_finance' if int(q)<=40 else 'tax_law',
                 accepted='/'.join(map(str,expected)))
        for label,answers in results.items():row.update({label:answers[q],label+'_correct':int(answers[q] in expected)})
        rows.append(row)
    with (OUT/'questions.csv').open('w',encoding='utf-8-sig',newline='') as handle:
        writer=csv.DictWriter(handle,fieldnames=list(rows[0]));writer.writeheader();writer.writerows(rows)
    summary=dict(multiple_choice=80,descriptive=0,totals={c:sum(r[c+'_correct'] for r in rows) for c in results},
                 stage_differences=[r for r in rows if r['level2']!=r['level3']])
    with fitz.open(ROOT/'outputs/benchmark_input/level2.pdf') as a,fitz.open(ROOT/'outputs/benchmark_input/level3.pdf') as b:
        summary['equal_150dpi_png_pages']=[i+1 for i in range(len(a)) if
            hashlib.sha256(a[i].get_pixmap(dpi=150).tobytes('png')).digest()==hashlib.sha256(b[i].get_pixmap(dpi=150).tobytes('png')).digest()]
    (OUT/'audit.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(summary),flush=True)
    # Repeat exactly the ambiguous page, using the original evaluation prompt/options.
    questions=key['pages']['29']
    prompt=('Solve the multiple choice exam questions in this image. '
            'Return only a JSON object mapping question numbers to choice numbers 1 to 5. '
            'Answer these question numbers: '+', '.join(questions)+'. Do not omit any.')
    schema=dict(type='object',properties={q:dict(type='integer',enum=[1,2,3,4,5]) for q in questions},required=questions,additionalProperties=False)
    with fitz.open(ROOT/'outputs/benchmark_input/level2.pdf') as doc:
        image=base64.b64encode(doc[28].get_pixmap(dpi=150).tobytes('png')).decode()
    for trial in range(5):
        path=OUT/f'repeat76-{trial}.json'
        if path.exists():continue
        result=request('http://127.0.0.1:11434/api/chat',dict(model='qwen2.5vl:3b',stream=False,format=schema,
            messages=[dict(role='user',content=prompt,images=[image])],options=dict(temperature=0,seed=42,num_ctx=8192,num_predict=2048)))
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print('repeat76',trial,result['message']['content'],flush=True)
    source=Path((ROOT/'outputs/benchmark_input/source_path.txt').read_text(encoding='utf-8'))
    with fitz.open(source) as doc:
        page=doc[0]
        from question_marks import detect_questions
        questions=detect_questions(page);second=next(q for q in questions if q['number']=='2')
        clip=fitz.Rect(0,0,page.rect.width,second['line_bbox'][1]-3)
        full=base64.b64encode(page.get_pixmap(dpi=150).tobytes('png')).decode()
        crop=base64.b64encode(page.get_pixmap(dpi=150,clip=clip).tobytes('png')).decode()
        text=page.get_text(clip=clip,sort=True)
    probes=[('ocr_full','Transcribe question 1 and its five choices exactly. Do not solve it.',full),
            ('ocr_crop','Transcribe question 1 and its five choices exactly. Do not solve it.',crop),
            ('solve_image','Solve only question 1. Explain your reasoning briefly, then give the choice number.',full),
            ('solve_text','Solve question 1. Explain briefly, then give the choice number.\n'+text,None)]
    for name,prompt,image in probes:
        path=OUT/f'{name}.json'
        if path.exists():continue
        message=dict(role='user',content=prompt)
        if image:message['images']=[image]
        result=request('http://127.0.0.1:11434/api/chat',dict(model='qwen2.5vl:3b',stream=False,messages=[message],
            options=dict(temperature=0,seed=42,num_ctx=8192,num_predict=1200)))
        path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
        print(name,result['message']['content'],flush=True)


if __name__=='__main__':main()
