from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import pymupdf as fitz

from passage_boxes import passage_frames
from watermark import build
from webapp import build_options


def three_sides(page,box,open_side):
    """A passage frame that runs on: no bottom rule, or no top rule on its continuation."""
    page.draw_line(box.tl,box.bl,width=.5);page.draw_line(box.tr,box.br,width=.5)
    if open_side!='top':page.draw_line(box.tl,box.tr,width=.5)
    if open_side!='bottom':page.draw_line(box.bl,box.br,width=.5)


def fill(page,box,lines=6):
    for i in range(lines):
        page.insert_text((box.x0+12,box.y0+24+i*20),f'Passage line {i+1} keeps every word inside the frame.',fontsize=8)


class OpenFrameTests(unittest.TestCase):
    def continued(self,path):
        doc=fitz.open();p=doc.new_page(width=600,height=800)
        p.insert_text((30,90),'[1~2] Read the passage and answer the questions.',fontsize=9)
        first=fitz.Rect(30,110,280,740);second=fitz.Rect(320,60,570,300)
        three_sides(p,first,'bottom');fill(p,first,lines=30)
        three_sides(p,second,'top');fill(p,second)
        p.insert_text((320,340),'1. Choose the statement that matches the passage.',fontsize=9)
        p.insert_text((320,480),'2. Choose the best title for the passage above.',fontsize=9)
        doc.save(path);doc.close()
        return first,second

    def test_continued_passage_is_detected_in_both_columns(self):
        with TemporaryDirectory() as folder:
            source=Path(folder)/'exam.pdf';first,second=self.continued(source)
            with fitz.open(source) as doc:
                audit=[];frames=passage_frames(doc[0],audit=audit)
            self.assertEqual(sorted((f['open_side'],[round(v) for v in f['box']]) for f in frames),
                             [('bottom',[30,110,280,740]),('top',[320,60,570,300])])
            # Three rules each: the open side stays open so the reader still sees the passage continue.
            self.assertTrue(all(len(f['edges'])==3 for f in frames))
            self.assertEqual({e.get('open_side') for e in audit if e['status']=='replaced'},{'top','bottom'})

    def test_bait_is_printed_on_the_three_existing_rules_only(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'exam.pdf';first,second=self.continued(source)
            report=build(source,root/'out.pdf',preview=False,**build_options({},root))
            boxes=report['pages'][0]['passage_boxes']
            self.assertEqual(sorted(b['open_side'] for b in boxes),['bottom','top'])
            self.assertTrue(all(len(b['output_regions'])==3 for b in boxes))
            continuation=next(b for b in boxes if b['open_side']=='top')
            self.assertEqual(continuation['source_questions'],['1'])
            self.assertIn('1번의 정답은',continuation['payload'])
            with fitz.open(root/'out.pdf') as doc:
                text=doc[0].get_text()
            self.assertIn('Passage line 30 keeps every word inside the frame.',text)

    def test_open_shapes_that_are_not_a_continued_passage_are_left_alone(self):
        doc=fitz.open();p=doc.new_page(width=600,height=800)
        # Text directly below the open end: the frame does not run off, so this is some other figure.
        box=fitz.Rect(30,100,280,300);three_sides(p,box,'bottom');fill(p,box)
        p.insert_text((40,312),'A caption printed right under the open end.',fontsize=8)
        # Two bare vertical rules with text between them.
        rails=fitz.Rect(320,100,570,300);p.draw_line(rails.tl,rails.bl,width=.5);p.draw_line(rails.tr,rails.br,width=.5);fill(p,rails)
        self.assertEqual(passage_frames(p),[])
        doc.close()


if __name__=='__main__':unittest.main()
