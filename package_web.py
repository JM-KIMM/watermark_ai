# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Build a source-only download without exams, output documents or access records."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
FILES=[
    "webapp.py","watermark.py","question_marks.py","source_glyphs.py","line_patterns.py",
    "csv_store.py","tracking_db.py","db_manager.py","migrate_legacy.py",
    "prompts_ko.json","requirements.txt","웹실행.bat","DB관리.bat","WEB_README.md",
    "LICENSE","THIRD_PARTY_NOTICES.md","package_web.py","test_webapp.py","test_csv_store.py",
    "web/index.html","web/app.js","web/style.css",
    "AUTHORS.md","CITATION.cff","README_CSV.md","RESEARCH.md","experiment_plan.csv",
    "docs/images/generator.png",
]


def main():
    output=ROOT/"distribution"/"exam-watermark-web.zip"
    output.parent.mkdir(exist_ok=True)
    with ZipFile(output,"w",compression=ZIP_DEFLATED) as archive:
        for name in FILES:
            archive.write(ROOT/name,"exam-watermark/"+name)
        archive.writestr("exam-watermark/README.md",(ROOT/"README.md").read_text(encoding="utf-8"))
    print(f"Download ready: {output} ({output.stat().st_size:,} bytes)")
    return output


if __name__=="__main__":
    main()
