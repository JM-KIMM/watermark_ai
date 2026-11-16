"""Independently regrade raw model replies and verify the exact captured inputs."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import argparse
import hashlib
import json
from corpus_evaluation import sections


def audit(out):
    inventory=json.loads((out/'inventory.json').read_text(encoding='utf8'))
    protocol=json.loads((out/'protocol.json').read_text(encoding='utf8'))
    summary=json.loads((out/'scores.json').read_text(encoding='utf8'))
    if not summary['complete']:raise ValueError('Cannot audit unfinished scores')
    totals={c:0 for c in protocol['conditions']};failures={c:0 for c in totals}
    weighted={c:0 for c in totals};maximum=0
    cache_hashes={};total=0;responses=0
    root=Path(__file__).resolve().parent.parent
    for exam in inventory:
        if exam['status']!='included':continue
        official_sections=sections(root/exam['source'])
        official={name:{q:v[0] for q,v in key.items()} for name,_,_,key in official_sections}
        weights={name:{q:v[1] for q,v in key.items()} for name,_,_,key in official_sections}
        for section in exam['sections']:
            if official[section['id']]!=section['answers']:raise ValueError('Key changed since preparation')
            if weights[section['id']]!=section['weights']:raise ValueError('Question weights changed')
            total+=len(section['answers'])
            maximum+=sum(weights[section['id']].values())
            for page,batch in section['pages'].items():
                for c in totals:
                    r=json.loads((out/'responses'/exam['id']/section['id']/f'{c}-{page}.json').read_text(encoding='utf8'))
                    if r['identity']!=protocol['identity'] or set(r['answers'])!=set(batch['questions']):raise ValueError('Mismatched response')
                    if len(r['capture_paths'])!=len(batch['context']):raise ValueError('Missing context capture')
                    for path,digest in zip(r['capture_paths'],r['image_sha256']):
                        if path not in cache_hashes:cache_hashes[path]=hashlib.sha256((out/path).read_bytes()).hexdigest()
                        if cache_hashes[path]!=digest:raise ValueError('Captured image changed')
                    if not r['error']:
                        raw=json.loads(r['attempts'][-1]['raw'])
                        if {q:int(v) for q,v in raw.items()}!=r['answers']:raise ValueError('Parsed choices do not match raw reply')
                    for q,answer in r['answers'].items():
                        expected=official[section['id']][q]
                        accepted=expected if isinstance(expected,list) else [expected]
                        if answer is None:
                            if not r['error']:raise ValueError('Null choice without inference error')
                            failures[c]+=1
                        else:
                            if type(answer) is not int or not 1<=answer<=5:raise ValueError('Invalid choice')
                            totals[c]+=int(answer in accepted)
                            weighted[c]+=int(answer in accepted)*weights[section['id']][q]
                    responses+=1
    for c in totals:
        if totals[c]!=summary['scores'][c]['correct'] or failures[c]!=summary['scores'][c]['inference_failures']:
            raise ValueError('Independent grading disagrees with published score')
        if weighted[c]!=summary['scores'][c]['points'] or maximum!=summary['scores'][c]['max_points']:
            raise ValueError('Independent weighted grading disagrees')
    result=dict(passed=True,total_exposures=total,responses=responses,unique_png_captures=len(cache_hashes),
                independently_regraded_correct=totals,inference_failures=failures,
                independently_regraded_points=weighted,max_points=maximum,
                checks=['official-key mapping unchanged','raw reply to parsed choices','image SHA256 matches actual PNG',
                        'all context pages present','null failures distinct from answered choices','independent score arithmetic'])
    (out/'audit.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(result,ensure_ascii=False,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('output',type=Path);args=p.parse_args();audit(args.output.resolve())
