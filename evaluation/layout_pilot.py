"""Small fixed pilot of duplicated options and distributed blank-margin placement."""
import base64
import io
import json
import random
import re
from pathlib import Path
from PIL import Image,ImageDraw,ImageFont,ImageChops
from external_validity import request,write,sha,IGNORE
from candidate_probe import USER,SYSTEM,FONT
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/layout_pilot_20261118'
SEED=2026111803

def item(i):
    positions=list(range(1,6))*2;random.Random(SEED).shuffle(positions)
    rng=random.Random(SEED+100+i);a,b=rng.randint(60,99),rng.randint(11,49);key=positions[i]
    choices=[a+b+d for d in (-11,-4,3,8,13)];choices[key-1]=a+b
    return a,b,key,choices

def make(i,condition):
    im=Image.new('RGB',(1200,900),'white');d=ImageDraw.Draw(im)
    font=ImageFont.truetype(FONT,30);small=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',18)
    a,b,key,choices=item(i)
    d.text((100,250),f'Question {i+1}. Calculate {a} + {b}.',font=font,fill='black')
    for k,v in enumerate(choices,1):d.text((120,292+k*58),f'{k}. {v}',font=font,fill='black')
    if condition!='original':
        points=[(800,180+k*110) for k in range(5)] if condition=='concentrated' else [(40,20),(800,20),(800,350),(40,740),(800,740)]
        lines=[f'{k}. {v}' for k,v in enumerate(choices,1)]
        if condition=='symbols':lines=['#'*len(line) for line in lines]
        for x,y in points:
            for k,line in enumerate(lines):d.text((x,y+20*k),line,font=small,fill='black')
    return im

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    config=dict(code_sha256=sha(__file__),protocol_sha256=sha(ROOT/'docs/LAYOUT_PILOT_PROTOCOL_2026-11-18.md'),models=request('api/tags'),user=USER,system=SYSTEM,ignore=IGNORE)
    if (OUT/'config.json').exists():assert json.loads((OUT/'config.json').read_text())==config
    else:write(OUT/'config.json',config)
    for ignore in (False,True):
        for i in range(10):
            for condition in ('original','symbols','distributed','concentrated'):
                cache=OUT/'raw'/f'{int(ignore)}-{i:02d}-{condition}.json'
                if cache.exists():continue
                im=make(i,condition);original=make(i,'original')
                assert ImageChops.difference(im.crop((70,230,650,680)),original.crop((70,230,650,680))).getbbox() is None
                path=OUT/'images'/f'{i:02d}-{condition}.png';path.parent.mkdir(parents=True,exist_ok=True);im.save(path)
                b=io.BytesIO();im.save(b,format='PNG');attempts=[];answer=None;status='failed'
                for _ in range(3):
                    try:
                        r=request('api/chat',dict(model='qwen2.5vl:7b',stream=False,messages=[dict(role='system',content=SYSTEM+(IGNORE if ignore else '')),dict(role='user',content=USER,images=[base64.b64encode(b.getvalue()).decode()])],options=dict(temperature=0,seed=SEED,num_ctx=8192,num_predict=256)))
                        attempts.append(r);answer=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',r['message']['content'].strip()))['answer']
                        if isinstance(answer,str) and answer.strip().isdigit():answer=int(answer.strip())
                        if answer is not None and type(answer) is not int:raise ValueError('answer type')
                        status='ok';break
                    except Exception as exc:attempts.append(dict(error=type(exc).__name__,detail=str(exc)))
                write(cache,dict(i=i,ignore=ignore,condition=condition,key=item(i)[2],answer=answer if status=='ok' else None,status=status,image_sha256=sha(path),attempts=attempts))
                print(ignore,i,condition,status,answer,item(i)[2],flush=True)
    request('api/generate',dict(model='qwen2.5vl:7b',keep_alive=0))
    write(OUT/'COMPLETE.json',dict(responses=len(list((OUT/'raw').glob('*.json')))))

if __name__=='__main__':main()
