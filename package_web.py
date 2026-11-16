# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Build a source-only download without exams, output documents or access records."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parent
FILES=[
    "webapp.py","watermark.py","question_marks.py","source_glyphs.py","line_patterns.py",
    "csv_store.py","tracking_db.py","tools/db_manager.py","tools/migrate_legacy.py",
    "prompts_ko.json","requirements.txt","웹실행.bat","tools/DB관리.bat","docs/WEB_README.md",
    "LICENSE","THIRD_PARTY_NOTICES.md","package_web.py",
    "tests/__init__.py","tests/test_webapp.py","tests/test_csv_store.py",
    "web/index.html","web/app.js","web/style.css","web/mono.css",
    "AUTHORS.md","CITATION.cff","docs/README_CSV.md","docs/RESEARCH.md","docs/experiment_plan.csv",
    "docs/images/generator.png",
    "evaluation/benchmark_local.py","evaluation/prepare_benchmark.py","tests/test_regressions.py",
    "docs/LOCAL_EVALUATION.md","docs/EVALUATION_RESULTS_2026-11-16.md",
    "evaluation/audit_evaluation.py","docs/GRADING_AUDIT_2026-11-16.md",
    "evaluation/corpus_evaluation.py","tests/test_corpus_evaluation.py","docs/CORPUS_EVALUATION.md",
    "evaluation/verify_corpus.py",
    "evaluation/export_corpus_report.py","docs/CORPUS_RESULTS_2026-11-16.md",
    "evaluation/enhance_corpus.py","tests/test_math_captions.py","docs/CORPUS_BASELINE_2026-11-16.md",
    "evaluation/ocr_llm_evaluation.py","evaluation/decoy_watermark.py",
    "docs/OCR_LLM_RESULTS_2026-11-16.md","docs/evaluation/ocr_llm_scores.json",
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
