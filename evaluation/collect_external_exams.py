"""Download source PDFs locally; publish only URLs and hashes."""
import hashlib
import json
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'outputs/external_validity'
SOURCES={
 'eng_202506':{'paper':'https://gichulbada.kr/files/H3_2506_paper.pdf','solution':'https://gichulbada.kr/files/H3_2506_solution.pdf'},
 'eng_202409':{'paper':'https://gichulbada.kr/files/H3_2409_paper.pdf','solution':'https://gichulbada.kr/files/H3_2409_solution.pdf'},
 'eng_202309':{'paper':'https://mogozip.com/downloads/ebsi/%EA%B3%A03-N%EC%88%98/2023/09/%EA%B3%A03_9%EC%9B%94_%EB%AA%A8%ED%8F%89(%ED%8F%89%EA%B0%80%EC%9B%90)_%EC%98%81%EC%96%B4/question-f76d5540f7.pdf',
                 'solution':'https://wdown.ebsi.co.kr/W61001/01exam/20230906/go3/eng_main_hsj_9AXRN8JA.pdf'},
}
def main():
    rows=[]
    for exam,urls in SOURCES.items():
        for kind,url in urls.items():
            path=OUT/'sources'/exam/(kind+'.pdf');path.parent.mkdir(parents=True,exist_ok=True)
            if not path.exists():
                req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
                with urllib.request.urlopen(req,timeout=90) as r:data=r.read()
                if not data.startswith(b'%PDF'):raise ValueError('Not a PDF')
                path.write_bytes(data)
            rows.append(dict(exam=exam,kind=kind,url=url,sha256=hashlib.sha256(path.read_bytes()).hexdigest(),bytes=path.stat().st_size))
            print(exam,kind,path.stat().st_size,flush=True)
    (OUT/'sources.json').write_text(json.dumps(rows,indent=2),encoding='utf8')
if __name__=='__main__':main()
