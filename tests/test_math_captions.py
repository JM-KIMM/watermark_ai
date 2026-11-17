from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import pymupdf as fitz
from watermark import build,is_math_exam
from question_marks import occupied_rects
from test_webapp import sample_pdf


class MathCaptionTests(unittest.TestCase):
    def test_math_detection_and_caption_whitespace(self):
        self.assertTrue(is_math_exam('수학영역_문제지.pdf'))
        self.assertFalse(is_math_exam('영어영역_문제지.pdf'))
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.pdf';sample_pdf(source)
            general=build(source,root/'general.pdf',intensity=2,preview=False)
            baseline=build(source,root/'baseline.pdf',intensity=2,preview=False,qr_captions=False)
            self.assertFalse(baseline['qr_captions'])
            self.assertTrue(all('label_status' not in q for p in baseline['pages'] for q in p['question_marks']))
            # A math file name no longer swaps the border for generated formulas.
            maths_source=root/'수학영역_문제지.pdf';sample_pdf(maths_source)
            maths=build(maths_source,root/'math.pdf',intensity=2,preview=False)
            self.assertNotIn('math_watermark',maths)
            self.assertEqual([p['payload'] for p in maths['pages']],[p['payload'] for p in general['pages']])
            with fitz.open(source) as doc:
                for i,record in enumerate(general['pages']):
                    placed=[m for m in record['question_marks'] if m['qr_status']=='placed']
                    self.assertTrue(placed)
                    for mark in placed:
                        self.assertEqual(mark['label_status'],'placed')
                        rect=fitz.Rect(mark['label_source_bbox'])
                        self.assertFalse(any(rect.intersects(r) for r in occupied_rects(doc[i])))
                        self.assertFalse(rect.intersects(fitz.Rect(mark['qr_source_bbox'])))


if __name__=='__main__':unittest.main()
