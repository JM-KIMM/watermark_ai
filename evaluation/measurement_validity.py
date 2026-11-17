"""Fixed synthetic prompt/option-order diagnostic; not an attack search."""
import base64
import io
import json
import random
import re
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont
from external_validity import request,write,sha,TESS
import subprocess
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/measurement_validity'

def make(i,shift):
    rng=random.Random(20261117+i);a,b=rng.randint(12,80),rng.randint(12,80)
    choices=[a+b+d for d in [-7,-3,2,5,9]];choices[i%5]=a+b
    choices=choices[shift:]+choices[:shift];key=choices.index(a+b)+1
    im=Image.new('RGB',(900,650),'white');draw=ImageDraw.Draw(im);font=ImageFont.truetype('C:/Windows/Fonts/malgun.ttf',28)
    draw.text((95,180),f'{i+1}번. {a} + {b}의 값은?',font=font,fill='black')
    for k,value in enumerate(choices,1):draw.text((100,230+55*k),f'{k}. {value}',font=font,fill='black')
    return im,key,a+b,choices

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/'plan.json',dict(ids=list(range(20)),rotated_ids=list(range(10)),shifts=list(range(5)),seed=20261117,script_sha256=sha(__file__),
        note='20 baseline tasks plus shifts 1-4 for first ten IDs, fixed before new response inspection. No watermark; tests measurement validity, not deterrence.'))
    for route,model in [('ocr','qwen2.5:7b'),('vision','qwen2.5vl:7b')]:
        for i in range(20):
            for shift in (range(5) if i<10 else [0]):
                path=OUT/'raw'/f'{route}-{i:02d}-{shift}.json'
                if path.exists():continue
                im,key,value,choices=make(i,shift)
                imagepath=OUT/f'{i:02d}-{shift}.png';im.save(imagepath)
                user=dict(role='user',content='Solve the displayed multiple-choice question. Return JSON with brief calculation in reason and the selected option number (1 to 5) in answer. Example format: {"reason":"...", "answer":1}. Do not put the computed sum in answer.')
                if route=='ocr':
                    text=subprocess.check_output([TESS,str(imagepath),'stdout','-l','kor+eng','--psm','6'],stderr=subprocess.DEVNULL).decode('utf8')
                    user['content']+='\n'+text
                else:
                    text=None;buf=io.BytesIO();im.save(buf,format='PNG');user['images']=[base64.b64encode(buf.getvalue()).decode()]
                response=request('api/chat',dict(model=model,stream=False,messages=[dict(role='system',content='You solve multiple-choice questions. Distinguish option numbers from their values.'),user],options=dict(temperature=0,seed=20261117,num_ctx=8192,num_predict=160)))
                answer=None;status='ok'
                try:
                    raw=response['message']['content'];parsed=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip()))
                    answer=parsed['answer']
                    if type(answer) is str and answer.strip().isdigit():answer=int(answer.strip())
                    if type(answer) is not int:raise ValueError('answer type')
                except Exception:status='format_error'
                write(path,dict(route=route,i=i,shift=shift,key=key,computed_value=value,choices=choices,answer=answer,status=status,ocr=text,response=response))
                print(route,i,shift,status,answer,key,flush=True)
        request('api/generate',dict(model=model,keep_alive=0))
    write(OUT/'COMPLETE.json',dict(responses=len(list((OUT/'raw').glob('*.json')))))
if __name__=='__main__':main()
