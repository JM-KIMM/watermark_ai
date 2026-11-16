"""Answer client with brief reasons, explicit abstention, and distinct failure classes."""
import base64
import json
import os
import re
import time
from urllib.error import HTTPError,URLError
from urllib.parse import urlsplit
from urllib.request import Request,urlopen

SYSTEM_PROMPT=('You solve multiple-choice exam questions. Give a brief reason with the decisive calculation or textual evidence, '
               'then the final choice number in the required JSON. Use at most 20 words per reason. '
               'Choose the best answer 1-5 even when uncertain. Use null only when necessary input is missing. '
               'Write brief_reasons before answers.')
PROMPT='Solve requested question numbers: {questions}. Supplied images or OCR text show relevant exam pages in ascending order.'


def schema(questions):
    return dict(type='object',properties={
        'brief_reasons':dict(type='object',properties={q:dict(type='string') for q in questions},required=questions,additionalProperties=False),
        'answers':dict(type='object',properties={q:dict(anyOf=[dict(type='integer',enum=[1,2,3,4,5]),dict(type='null')]) for q in questions},required=questions,additionalProperties=False)},
        required=['brief_reasons','answers'],additionalProperties=False)


def parse(raw,questions):
    text=raw.strip()
    if text.startswith('```'):text=re.sub(r'^```(?:json)?\s*|\s*```$','',text)
    value=json.loads(text)
    if not isinstance(value,dict) or not isinstance(value.get('answers'),dict):raise ValueError('Missing final answers object')
    answers=value['answers']
    if set(answers)!=set(questions):raise ValueError('Missing or unexpected question IDs')
    for q,v in answers.items():
        if isinstance(v,str) and v.strip() in ('1','2','3','4','5'):answers[q]=int(v.strip())
        elif isinstance(v,str) and v.strip() in '①②③④⑤' and len(v.strip())==1:answers[q]='①②③④⑤'.index(v.strip())+1
    if any(v is not None and (type(v) is not int or v not in (1,2,3,4,5)) for v in answers.values()):raise ValueError('Invalid final choice')
    if not isinstance(value.get('brief_reasons'),dict) or set(value['brief_reasons'])!=set(questions):raise ValueError('Missing brief reasons')
    return answers


def infer(model,questions,*,images=None,ocr_text=None,seed=42,commercial=False):
    prompt=PROMPT.format(questions=', '.join(questions))
    if ocr_text is not None:prompt+='\n\nEXAM_TEXT_START\n'+ocr_text+'\nEXAM_TEXT_END'
    attempts=[];begin=time.monotonic()
    for attempt in range(3):
        raw=''
        try:
            if commercial:
                endpoint=os.environ.get('COMMERCIAL_BASE_URL','https://api.openai.com/v1').rstrip('/')+'/chat/completions'
                parsed_url=urlsplit(endpoint)
                if parsed_url.scheme!='https' or parsed_url.username or parsed_url.query:raise ValueError('Commercial endpoint must be an explicit HTTPS URL without credentials/query')
                key=os.environ.get('COMMERCIAL_API_KEY') or os.environ.get('OPENAI_API_KEY')
                if not key:raise RuntimeError('Commercial API is not configured')
                content=[dict(type='text',text=prompt)]+[dict(type='image_url',image_url=dict(url='data:image/png;base64,'+base64.b64encode(i).decode())) for i in images or []]
                body=dict(model=model,messages=[dict(role='system',content=SYSTEM_PROMPT),dict(role='user',content=content)],temperature=0,seed=seed,max_completion_tokens=1024,
                          response_format=dict(type='json_schema',json_schema=dict(name='exam_answers',strict=True,schema=schema(questions))))
                req=Request(endpoint,data=json.dumps(body).encode(),headers={'Authorization':'Bearer '+key,'Content-Type':'application/json'})
                with urlopen(req,timeout=900) as r:response=json.load(r)
                message=response['choices'][0]['message'];raw=message.get('content') or ''
                if message.get('refusal'):
                    return dict(status='refused',answers={q:None for q in questions},attempts=[dict(refusal=message['refusal'])],seconds=time.monotonic()-begin)
                usage=response.get('usage',{})
            else:
                from benchmark_local import request
                message=dict(role='user',content=prompt)
                if images:message['images']=[base64.b64encode(i).decode() for i in images]
                body=dict(model=model,stream=False,format=schema(questions),messages=[dict(role='system',content=SYSTEM_PROMPT),message],
                          options=dict(seed=seed,temperature=0,num_ctx=32768,num_predict=1024))
                response=request('http://127.0.0.1:11434/api/chat',body,timeout=900)
                raw=response['message']['content'];usage={k:response.get(k) for k in ('prompt_eval_count','eval_count','done_reason','total_duration','load_duration')}
            answers=parse(raw,questions)
            attempts.append(dict(raw=raw,status='ok',usage=usage))
            return dict(status='ok',answers=answers,attempts=attempts,seconds=time.monotonic()-begin,
                        reason_order='reasons-first' if raw.lstrip().startswith('{"brief_reasons"') or re.match(r'^\{\s*"brief_reasons"',raw.lstrip()) else 'other')
        except (HTTPError,URLError,TimeoutError,OSError) as exc:
            attempts.append(dict(status='transport_error',error=type(exc).__name__,http_status=getattr(exc,'code',None)))
        except (ValueError,KeyError,TypeError,AttributeError) as exc:
            attempts.append(dict(status='format_error',error=str(exc),raw=raw))
        if attempt<2:time.sleep(2**attempt)
    return dict(status=attempts[-1]['status'],answers={q:None for q in questions},attempts=attempts,seconds=time.monotonic()-begin)
