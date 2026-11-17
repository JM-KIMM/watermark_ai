"""Independent score/input audit against raw successful responses."""
import hashlib
import json
import re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/external_validity'

def load(p):return json.loads(Path(p).read_text(encoding='utf8'))
def unique_pairs(pairs):
    out={}
    for k,v in pairs:
        if k in out:raise ValueError('duplicate JSON key')
        out[k]=v
    return out

def main():
    report=load(ROOT/'docs/evaluation/external_validity.json')
    seal=load(OUT/'seal.json');checked=0
    for name,digest in seal['files'].items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,name
        checked+=1
    config=load(OUT/'run_config.json')
    assert hashlib.sha256((ROOT/'evaluation/external_validity.py').read_bytes()).hexdigest()==config['script_sha256']
    assert hashlib.sha256((ROOT/'docs/EXTERNAL_VALIDITY_PROTOCOL.md').read_bytes()).hexdigest()==report['amendment']['protocol_sha256']
    totals={};raw_hashes={};regraded=0
    for row in report['questions']:
        p=OUT/'responses_v2'/row['route']/row['condition']/(row['batch']+'.json');d=load(p)
        raw_hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
        successful=[a for a in d['attempts'] if 'message' in a]
        if d['status']=='ok':
            content=successful[-1]['message']['content'].strip()
            answer=json.loads(re.sub(r'^```(?:json)?\s*|\s*```$','',content),object_pairs_hook=unique_pairs)['answers'][row['question']]
            assert answer==row['answer']
            assert (answer==row['key'])==row['correct'];regraded+=1
            key=row['route'],row['condition'];totals[key]=totals.get(key,0)+int(answer==row['key'])
    for g in report['groups']:
        if g['exam']=='all':assert totals[g['route'],g['condition']]==g['correct']
    result=dict(input_files_verified=checked,raw_batches=len(raw_hashes),questions_regraded=regraded,
                score_matches=True,duplicate_key_check=True,code_and_amended_protocol_match=True,raw_response_hashes=raw_hashes)
    (ROOT/'docs/evaluation/external_independent_audit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print({k:v for k,v in result.items() if k!='raw_response_hashes'})
if __name__=='__main__':main()
