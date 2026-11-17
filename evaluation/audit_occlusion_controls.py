"""Input-identity negative controls for existing occlusion measurements."""
import json
from pathlib import Path
from PIL import Image,ImageChops
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/mechanism_probe'
base=Image.open(OUT/'images/00-marked.png').convert('RGB')
records=[]
for route in ('ocr','vision'):
    for ignore in (0,1):
        original=json.loads((OUT/'raw'/f'{route}-{ignore}-00-marked.json').read_text(encoding='utf8'))
        for y in range(4):
            for x in range(4):
                name=f'occlusion-{y}-{x}'
                changed=ImageChops.difference(base,Image.open(OUT/'images'/f'{name}.png').convert('RGB')).getbbox() is not None
                r=json.loads((OUT/'raw'/f'{route}-{ignore}-{name}.json').read_text(encoding='utf8'))
                records.append(dict(route=route,ignore=bool(ignore),x=x,y=y,input_changed=changed,
                    delta_p6=r['p_six'][0]-original['p_six'][0],
                    delta_p_correct=r['p_correct'][0]-original['p_correct'][0],
                    ocr_changed=r['ocr']!=original['ocr'] if route=='ocr' else None))
neg=[r for r in records if not r['input_changed']]
result=dict(records=records,negative_controls=len(neg),
    max_identical_input_delta_p6=max(abs(r['delta_p6']) for r in neg),
    max_identical_input_delta_correct=max(abs(r['delta_p_correct']) for r in neg),
    note='Blank-region identity control, not model-weight randomization. One fixed item; masking body text creates missing-input confounding.')
(ROOT/'docs/evaluation/occlusion_controls.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print({k:v for k,v in result.items() if k!='records'})
