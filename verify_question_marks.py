"""Measure actual rasterized QR decode rates. Requires opencv-python (verification only)."""
from pathlib import Path
import json

import cv2
import numpy as np
import pymupdf as fitz

from question_marks import detect_questions, occupied_rects


def main():
    root = Path(__file__).resolve().parent
    detector = cv2.QRCodeDetector()
    metrics = {"ai_answer_accuracy": None, "qr_decode": {}, "files": []}
    detected = placed = patterned = skipped = 0
    for path in sorted((root / "outputs").glob("*.manifest.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        for key in ("source", "output"):
            if not Path(meta[key]).exists():
                base = root if key == "source" else root / "outputs"
                meta[key] = str(base / Path(meta[key]).name)
        if meta.get("question_style", "none") == "none":
            continue
        per_file = dict(file=Path(meta["output"]).name, detected=0, placed=0, skipped=0, decode={})
        with fitz.open(meta["output"]) as output, fitz.open(meta["source"]) as source:
            for i, record in enumerate(meta["pages"]):
                assert len(detect_questions(source[i])) == len(record["question_marks"])
                occupied = occupied_rects(source[i])
                for mark in record["question_marks"]:
                    detected += 1
                    per_file["detected"] += 1
                    if mark["number_status"] == "qr-texture-not-decodable":
                        patterned += 1
                    if mark["qr_status"] == "skipped-no-whitespace":
                        skipped += 1
                        per_file["skipped"] += 1
                    if mark["qr_status"] != "placed":
                        continue
                    placed += 1
                    per_file["placed"] += 1
                    original_rect = fitz.Rect(mark["qr_source_bbox"])
                    assert source[i].rect.contains(original_rect)
                    assert not any(original_rect.intersects(r) for r in occupied)
                    rect = fitz.Rect(mark["qr_bbox"])
                    for dpi in (150, 300):
                        pix = output[i].get_pixmap(dpi=dpi, clip=rect, alpha=False)
                        array = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                        value, _, _ = detector.detectAndDecode(array)
                        key = f"{dpi}dpi_question_crop"
                        tally = metrics["qr_decode"].setdefault(key, {"correct": 0, "total": 0})
                        tally["total"] += 1
                        tally["correct"] += value == mark["qr_payload"]
                        result = per_file["decode"].setdefault(str(dpi), {"correct": 0, "total": 0})
                        result["total"] += 1
                        result["correct"] += value == mark["qr_payload"]
        metrics["files"].append(per_file)
    assert placed > 0
    # A small multi-column / multi-digit detection fixture.
    d = fitz.open()
    p = d.new_page()
    for xy, text in [((50, 80), "1. First"), ((320, 80), "10. Second"),
                     ((50, 140), "2.50 is a decimal")]:
        p.insert_text(xy, text)
    assert [q["number"] for q in detect_questions(p)] == ["1", "10"]
    d.close()
    metrics.update(detected=detected, placed=placed, patterned=patterned, skipped=skipped)
    destination = root / "outputs" / "qr_metrics.json"
    destination.write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metrics, ensure_ascii=False, indent=2))
    assert metrics["qr_decode"]["300dpi_question_crop"]["correct"] == placed, "300 DPI decode failed; inspect metrics."


if __name__ == "__main__":
    main()
