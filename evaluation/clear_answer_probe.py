"""Post-diagnostic replication of the synthetic factorial with full final answers."""
import base64
import io
import json
import re
import subprocess
from pathlib import Path
from mechanism_probe import make_image
from external_validity import request,write,sha,TESS,IGNORE
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/clear_answer_probe'

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    write(OUT/'plan.json',dict(n=20,conditions=['original','neutral','marked'],ignore=[False,True],
        script_sha256=sha(__file__),status='Exploratory follow-up designed after observing 20/20 explicit baseline; not an independent preregistered confirmation.'))
    for route,model in [('ocr','qwen2.5:7b'),('vision','qwen2.5vl:7b')]:
        for ignore in (False,True):
            for i in range(20):
                for cond in ('original','neutral','marked'):
                    cache=OUT/'raw'/f'{route}-{int(ignore)}-{i:02d}-{cond}.json'
                    if cache.exists():continue
                    im,key=make_image(i,cond);path=OUT/f'{i:02d}-{cond}.png';im.save(path)
                    user=dict(role='user',content='Solve the displayed multiple-choice question. Return JSON with brief calculation in reason and the selected option number (1 to 5) in answer. Example format: {"reason":"...", "answer":1}. Do not put the computed sum in answer.')
                    if route=='ocr':
                        text=subprocess.check_output([TESS,str(path),'stdout','-l','kor+eng','--psm','6'],stderr=subprocess.DEVNULL).decode('utf8');user['content']+='\n'+text
                    else:
                        text=None;buf=io.BytesIO();im.save(buf,format='PNG');user['images']=[base64.b64encode(buf.getvalue()).decode()]
                    response=request('api/chat',dict(model=model,stream=False,messages=[dict(role='system',content='You solve multiple-choice questions. Distinguish option numbers from their values.'+(IGNORE if ignore else '')),user],options=dict(temperature=0,seed=20261117,num_ctx=8192,num_predict=160)))
                    answer=None;status='ok'
                    try:
                        raw=response['message']['content'];answer=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',raw.strip()))['answer']
                        if isinstance(answer,str) and answer.strip().isdigit():answer=int(answer.strip())
                        if type(answer) is not int:raise ValueError('answer type')
                    except Exception:status='format_error'
                    write(cache,dict(route=route,ignore=ignore,i=i,condition=cond,key=key,answer=answer,status=status,ocr=text,response=response))
                    print(route,ignore,i,cond,status,answer,key,flush=True)
        request('api/generate',dict(model=model,keep_alive=0))
    write(OUT/'COMPLETE.json',dict(responses=len(list((OUT/'raw').glob('*.json')))))
if __name__=='__main__':main()
