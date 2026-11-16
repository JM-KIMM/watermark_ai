from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz

from watermark import build, QR_DIRECTIVE


class TypographyTests(unittest.TestCase):
    def test_seed_reproduction_source_glyphs_and_size_bounds(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/"source.pdf"
            d = fitz.open()
            for i in range(2):
                p = d.new_page()
                p.insert_text((60, 80), f"{i+1}. First question alpha beta gamma. Explain the result.", fontsize=12)
            d.save(source); d.close()
            images = []
            for name, seed in [("a", 7), ("b", 7), ("c", 8)]:
                output = root/f"{name}.pdf"
                report = build(source, output, font_mode="source", size_jitter=.25, width_jitter=.15, seed=seed, preview=False)
                for page in report["pages"]:
                    stats = page["typography"]
                    self.assertGreater(stats["matched_glyphs"], 0)
                    self.assertGreaterEqual(stats["size_min"], 4.5)
                    self.assertLessEqual(stats["size_max"], 7.5)
                    self.assertGreaterEqual(stats["width_scale_min"], .85)
                    self.assertLessEqual(stats["width_scale_max"], 1.15)
                    self.assertTrue(page["payload"].startswith(QR_DIRECTIVE))
                with fitz.open(output) as result:
                    images.append(result[0].get_pixmap().samples)
            self.assertEqual(images[0], images[1])
            self.assertNotEqual(images[0], images[2])

    def test_local_random_qr_is_reproducible_and_avoids_content(self):
        from question_marks import detect_questions, occupied_rects, find_space
        import random
        d = fitz.open(); p = d.new_page()
        for i in range(3):
            p.insert_text((80, 100+i*150), f"{i+1}. A question with enough whitespace.")
        questions = detect_questions(p)
        occupied = occupied_rects(p)
        def places(seed, mode):
            rng = random.Random(seed)
            return [find_space(q, 36, p.rect, occupied, placement=mode, rng=rng) for q in questions]
        fixed, first, again = places(42, "fixed"), places(42, "local-random"), places(42, "local-random")
        self.assertEqual(first, again)
        self.assertNotEqual(fixed, first)
        for rect in first:
            self.assertIsNotNone(rect)
            self.assertTrue(p.rect.contains(rect))
            self.assertFalse(any(rect.intersects(box) for box in occupied))
        d.close()


if __name__ == "__main__":
    unittest.main()
