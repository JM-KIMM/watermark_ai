"""Integration checks against the generated sample artifacts."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repository root
import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory

import pymupdf as fitz
from PIL import Image, ImageChops, ImageStat, ImageDraw

from watermark import build


def main():
    root = Path(__file__).resolve().parent.parent
    checks = 0
    for path in sorted((root / "outputs").glob("*.manifest.json")):
        meta = json.loads(path.read_text(encoding="utf-8"))
        for key in ("source", "output"):
            if not Path(meta[key]).exists():
                base = root if key == "source" else root / "outputs"
                meta[key] = str(base / Path(meta[key]).name)
        src = Path(meta["source"])
        assert hashlib.sha256(src.read_bytes()).hexdigest() == meta["source_sha256"]
        with fitz.open(src) as original, fitz.open(meta["output"]) as output:
            assert len(original) == len(output) == len(meta["pages"])
            b = meta["border_pt"]
            for i, record in enumerate(meta["pages"]):
                assert record["summary_source_page"] != i + 1
                old, new = original[i], output[i]
                region = fitz.Rect(b, b, b + old.rect.width, b + old.rect.height)
                assert new.rect.width == old.rect.width + 2 * b
                assert new.rect.height == old.rect.height + 2 * b
                # PDF form placement may introduce tiny antialias rounding changes.
                before = old.get_pixmap(alpha=False)
                after = new.get_pixmap(clip=region, alpha=False)
                assert (before.width, before.height) == (after.width, after.height)
                delta = ImageChops.difference(
                    Image.frombytes("RGB", (before.width, before.height), before.samples),
                    Image.frombytes("RGB", (after.width, after.height), after.samples))
                # Exclude only the recorded, intentional question marks.
                draw = ImageDraw.Draw(delta)
                for mark in record.get("question_marks", []):
                    for key in ("qr_bbox", "number_output_bbox", "label_bbox"):
                        if key in mark:
                            x0, y0, x1, y1 = mark[key]
                            draw.rectangle((int(x0-b)-1, int(y0-b)-1,
                                            int(x1-b)+1, int(y1-b)+1), fill=(0, 0, 0))
                assert max(high for low, high in delta.getextrema()) <= 2 and max(ImageStat.Stat(delta).mean) < .001, f"本文 rendering changed: {path.name} {i+1}"
                bands = [fitz.Rect(0, 0, new.rect.width, b),
                         fitz.Rect(0, new.rect.height-b, new.rect.width, new.rect.height),
                         fitz.Rect(0, b, b, new.rect.height-b),
                         fitz.Rect(new.rect.width-b, b, new.rect.width, new.rect.height-b)]
                if b:
                    assert all(new.get_text(clip=r).strip() for r in bands)
                checks += 1
    assert checks, "샘플 결과가 없습니다."
    with TemporaryDirectory() as temp:
        scan = Path(temp) / "scan.pdf"
        d = fitz.open()
        d.new_page(); d.new_page()
        d.save(scan); d.close()
        try:
            build(scan, Path(temp) / "out.pdf", mode="summary")
        except ValueError as exc:
            assert "요약 원문" in str(exc)
        else:
            raise AssertionError("텍스트 없는 입력이 통과했습니다.")
    print(f"PASS: {checks}개 페이지의 본문 렌더링(안티앨리어싱 오차 허용)·4변 텍스트·페이지 매핑 및 빈 입력 거부")


if __name__ == "__main__":
    main()
