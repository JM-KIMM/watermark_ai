"""Export a self-contained, printable HTML report with embedded figures."""
import base64
import re
from pathlib import Path
import markdown
ROOT=Path(__file__).resolve().parents[1]
doc=ROOT/'docs/RESEARCH_PAPER.md'
html=markdown.markdown(doc.read_text(encoding='utf8'),extensions=['tables','fenced_code'])
def embed(match):
    p=doc.parent/match.group(1)
    return 'src="data:image/png;base64,'+base64.b64encode(p.read_bytes()).decode()+'"'
html=re.sub(r'src="(images/[^\"]+\.png)"',embed,html)
html=re.sub(r'href="((?:evaluation/)[^\"]+)"',r'href="https://github.com/JM-KIMM/watermark_ai/blob/main/docs/\1"',html)
html='''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>시험지 워터마크 — 타당성 연구</title><style>
body{font-family:"Malgun Gothic","Noto Sans KR",sans-serif;color:#171717;background:white;max-width:1100px;margin:50px auto;padding:0 28px;font-size:15px;line-height:1.85}h1{font-size:30px;line-height:1.4}h2{font-size:23px;margin-top:42px;border-bottom:1px solid #bbb;padding-bottom:8px}h3{font-size:18px;margin-top:28px}table{border-collapse:collapse;width:100%;font-size:12px;line-height:1.5;margin:20px 0}th,td{border:1px solid #bbb;padding:7px;text-align:left}th{background:#eee}img{max-width:100%;height:auto}pre{white-space:pre-wrap;word-break:break-word;background:#f3f3f3;padding:15px}a{color:#222;overflow-wrap:anywhere}p,li{overflow-wrap:anywhere}@media print{body{font-size:10pt;margin:0;max-width:none}h2,h3{break-after:avoid}img,tr{break-inside:avoid}table{font-size:8pt}@page{size:A4;margin:18mm}}
</style><body>'''+html+'</body></html>'
target=ROOT/'docs/RESEARCH_PAPER.html';target.write_text(html,encoding='utf8');print(target)
