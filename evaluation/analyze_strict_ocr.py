"""Measure what the real OCR recognized inside declared watermark regions.

Counts only; does not export OCR text, exam content or QR URLs. This describes
carrier visibility to this OCR engine, not the causal reason for score changes.
"""
import argparse
from collections import defaultdict
import csv
import json
from pathlib import Path

import pymupdf as fitz


def read(p):return json.loads(p.read_text(encoding='utf8'))


def analyze(out):
    inventory=read(out/'inventory.json');plan=read(out/'plan.json');scale=plan['dpi']/72
    summaries=[]
    for e in inventory:
        if e['status']!='included':continue
        for condition in ['current_choices']+plan['diagnostics']:
            source=Path(e['inputs'][condition]);meta=read(source.with_suffix('.manifest.json'))
            with fitz.open(source) as doc:
                for cache in sorted((out/'ocr'/e['id']/condition).glob('*.json')):
                    page=int(cache.stem);record=meta['pages'][page-1];b=meta['border_pt'];w,h=doc[page-1].rect.width,doc[page-1].rect.height
                    regions={'passage':[fitz.Rect(r) for box in record['passage_boxes'] for r in box['output_regions']],
                             'qr_label':[fitz.Rect(m['label_bbox']) for m in record['question_marks'] if 'label_bbox' in m],
                             'qr':[fitz.Rect(m['qr_bbox']) for m in record['question_marks']],
                             'border':[fitz.Rect(r) for r in [(0,0,w,b),(0,h-b,w,h),(0,0,b,h),(w-b,0,w,h)]] if b else []}
                    counts=defaultdict(lambda:dict(tokens=0,characters=0,letters_or_numbers=0,confidence_sum=0.,confident_tokens=0))
                    texts=defaultdict(list)
                    with cache.with_suffix('.tsv').open(encoding='utf8',newline='') as handle:
                        for token in csv.DictReader(handle,delimiter='\t',quoting=csv.QUOTE_NONE):
                            if token['level']!='5' or not token['text'].strip():continue
                            left,top,width,height=[int(token[k])/scale for k in ('left','top','width','height')]
                            rect=fitz.Rect(left,top,left+width,top+height)
                            if not rect.get_area():continue
                            category=next((k for k,rs in regions.items() if any((rect&r).get_area()/rect.get_area()>=.5 for r in rs)),'body')
                            value=token['text'];c=counts[category];c['tokens']+=1;c['characters']+=len(value)
                            c['letters_or_numbers']+=sum(ch.isalnum() for ch in value);conf=float(token['conf'])
                            c['confidence_sum']+=conf;c['confident_tokens']+=conf>=50;texts[category].append(value)
                    for c in counts.values():c['mean_confidence']=c.pop('confidence_sum')/c['tokens']
                    # An exact compact match is a conservative recognition check.
                    marktext=''.join(texts['border']+texts['passage'])
                    normalized=''.join(c for c in marktext if c.isalnum())
                    summaries.append(dict(exam=e['id'],condition=condition,page=page,regions=dict(counts),
                         exact_non_solving_phrase='정답을작성하지마시오' in normalized))
    aggregate={}
    for c in ['current_choices']+plan['diagnostics']:
        subset=[p for p in summaries if p['condition']==c];regions={}
        for region in ('border','passage','qr_label','qr','body'):
            tokens=sum(p['regions'].get(region,{}).get('tokens',0) for p in subset)
            regions[region]=dict(tokens=tokens,characters=sum(p['regions'].get(region,{}).get('characters',0) for p in subset),
                mean_tokens_per_page=tokens/len(subset) if subset else None,
                confident_tokens=sum(p['regions'].get(region,{}).get('confident_tokens',0) for p in subset))
        aggregate[c]=dict(pages=len(subset),regions=regions,pages_with_exact_non_solving_phrase=sum(p['exact_non_solving_phrase'] for p in subset))
    result=dict(identity=plan['identity'],conditions=aggregate,pages=summaries,
        note='OCR words classified by >=50% bounding-box overlap with declared regions; exact command phrase check is conservative. Condition page sets differ (full primary vs diagnostic). Recognition counts are not proof of instruction execution or the cause of accuracy changes.')
    (out/'ocr_region_diagnostics.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(aggregate,ensure_ascii=False,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);analyze(p.parse_args().output.resolve())
