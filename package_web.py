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
    "web/index.html","web/app.js","web/style.css","web/mono.css",
    "AUTHORS.md","CITATION.cff","README_CSV.md","RESEARCH.md","experiment_plan.csv",
    "docs/images/generator.png",
    "benchmark_local.py","prepare_benchmark.py","test_regressions.py",
    "docs/LOCAL_EVALUATION.md","docs/EVALUATION_RESULTS_2026-11-16.md",
    "audit_evaluation.py","docs/GRADING_AUDIT_2026-11-16.md",
    "corpus_evaluation.py","test_corpus_evaluation.py","docs/CORPUS_EVALUATION.md",
    "verify_corpus.py",
    "export_corpus_report.py","docs/CORPUS_RESULTS_2026-11-16.md",
    "enhance_corpus.py","test_math_captions.py","docs/CORPUS_BASELINE_2026-11-16.md",
    "docs/evaluation/corpus_scores.json","docs/evaluation/corpus_questions.json",
    "docs/evaluation/corpus_inventory.json","docs/evaluation/corpus_protocol.json",
    "docs/evaluation/corpus_verification.json",
    "docs/evaluation/baseline_corpus_scores.json","docs/evaluation/baseline_corpus_questions.json",
    "docs/evaluation/baseline_corpus_inventory.json","docs/evaluation/baseline_corpus_protocol.json",
    "docs/evaluation/baseline_corpus_verification.json",
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
