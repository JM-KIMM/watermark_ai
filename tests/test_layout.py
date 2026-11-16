from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz
from PIL import Image, ImageChops

from passage_boxes import passage_frames
from watermark import build
from webapp import build_options


class LayoutTests(unittest.TestCase):
    def test_default_gutters_frames_and_body_preservation(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            source = root/'exam.pdf'
            doc = fitz.open()
            p = doc.new_page(width=600,height=800)
            for x,number in [(25,1),(325,3)]:
                for y,n in [(120,number),(500,number+1)]:
                    p.insert_text((x,y),f'{n}. Choose the correct answer.')
            p.draw_rect(fitz.Rect(25,170,275,300),width=.5)
            p.insert_text((40,200),'Preserve every word inside this passage box.')
            p.insert_text((40,225),'The passage continues on the following line.')
            # A table and a diagram must retain their original frames.
            p.draw_rect(fitz.Rect(325,170,575,300),width=.5)
            p.insert_text((340,200),'These words are inside a table.')
            p.draw_line((325,235),(575,235))
            doc.save(source); doc.close()
            options = build_options({'qr_placement':'gutter'},root)
            self.assertEqual(options['opacity'],.9)
            report = build(source,root/'out.pdf',preview=False,**options)
            self.assertEqual(len(report['pages'][0]['passage_boxes']),1)
            marks = report['pages'][0]['question_marks']
            self.assertEqual(len(marks),4)
            band = report['border_pt']
            with fitz.open(source) as a, fitz.open(root/'out.pdf') as b:
                body = fitz.Rect(band,band,band+600,band+800)
                for m in marks:
                    self.assertEqual(m['qr_status'],'placed')
                    self.assertFalse(body.intersects(fitz.Rect(m['qr_bbox'])))
                    self.assertFalse(body.intersects(fitz.Rect(m['label_bbox'])))
                    self.assertEqual(m['qr_bbox'][1]-band,m['number_bbox'][1])
                self.assertEqual(marks[0]['qr_bbox'][0],marks[1]['qr_bbox'][0])
                self.assertEqual(marks[2]['qr_bbox'][0],marks[3]['qr_bbox'][0])
                for clip in [fitz.Rect(35,185,270,240),fitz.Rect(320,165,580,305)]:
                    before = a[0].get_pixmap(clip=clip,alpha=False)
                    after = b[0].get_pixmap(clip=clip+(band,band,band,band),alpha=False)
                    diff = ImageChops.difference(Image.frombytes('RGB',(before.width,before.height),before.samples),
                                                 Image.frombytes('RGB',(after.width,after.height),after.samples))
                    self.assertIsNone(diff.getbbox())

    def test_interrupted_title_and_graph_exclusion(self):
        doc = fitz.open();p=doc.new_page()
        p.draw_line((50,150),(130,150),width=.5)
        p.draw_line((185,150),(300,150),width=.5)
        p.draw_line((50,150),(50,300),width=.5)
        p.draw_line((300,150),(300,300),width=.5)
        p.draw_line((50,300),(300,300),width=.5)
        p.insert_text((130,153),'PASSAGE')
        p.insert_text((65,190),'Preserve the passage text inside.')
        self.assertEqual(len(passage_frames(p)),1)
        p.draw_circle((180,240),20)
        self.assertEqual(passage_frames(p),[])
        doc.close()

    def test_sides_split_at_text_lines(self):
        doc=fitz.open();p=doc.new_page()
        for y in range(150,300,10):
            for x in (50,300):
                p.draw_line((x,y),(x,y+10.2),width=.5)
        p.draw_line((50,150),(300,150),width=.5)
        p.draw_line((50,300),(300,300),width=.5)
        p.insert_text((65,190),'Keep all these words inside the frame.')
        self.assertEqual(len(passage_frames(p)),1)
        p.draw_rect(fitz.Rect(63,177,93,194),width=.5)
        self.assertEqual(len(passage_frames(p)),1)
        doc.close()

    def test_gutter_collision_does_not_move_qr_into_body(self):
        from question_marks import apply_question_marks
        from watermark import font_path
        doc=fitz.open();source=doc.new_page()
        source.insert_text((20,100),'1. First question.')
        source.insert_text((20,125),'2. Next question too close to first.')
        target=doc.new_page(width=source.rect.width+112,height=source.rect.height+112)
        source=doc[0]
        marks=apply_question_marks(source,target,band=56,style='qr',qr_size=40,
                                   payload='test',placement='gutter',label_font=font_path(None))
        self.assertEqual([m['qr_status'] for m in marks],['placed','skipped-no-whitespace'])
        doc.close()
