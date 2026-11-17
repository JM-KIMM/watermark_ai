"""Compare table extraction against separately transcribed answer sequences."""
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/external_validity'
MANUAL={
 'eng_202309':'1122151352534424534553215433',
 'eng_202409':'4333344523555221345354113225',
 'eng_202506':'1123132425235514244345215335',
}
def main():
    inv=json.loads((OUT/'inventory.json').read_text(encoding='utf8'));checks=[]
    for e in inv:
        text=''.join(str(e['keys'][str(q)]) for q in range(18,46))
        assert text==MANUAL[e['exam']]
        checks.append(dict(exam=e['exam'],n=28,match=True,
            source='202309 EBS solution first-page table; 202409/202506 solution table corroborated with public answer listings',
            answer_sha256=e['solution_sha256']))
    (OUT/'key_audit.json').write_text(json.dumps(checks,indent=2),encoding='utf8')
    print('PASS: 84 answers agree with independent transcription; listening excluded')
if __name__=='__main__':main()
