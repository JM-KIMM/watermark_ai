import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import pymupdf as fitz
from PIL import Image,ImageChops
from watermark import build
from webapp import build_options
from question_layout import reserve_question_rows


class QuestionEndTests(unittest.TestCase):
    def test_question_end_moves_after_choices_on_next_page(self):
        from watermark_payloads import extract_source
        from watermark import font_path
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'continued.pdf';doc=fitz.open()
            p=doc.new_page();p.insert_text((50,100),'1. The choices continue on the next page.')
            p=doc.new_page();p.insert_font(fontname='ko',fontfile=str(font_path(None)))
            for i in range(5):p.insert_text((50,80+i*30),f'{chr(0x2460+i)} choice {i+1}',fontname='ko')
            p.insert_text((50,350),'2. Next question.')
            for i in range(5):p.insert_text((50,410+i*30),f'{chr(0x2460+i)} next {i+1}',fontname='ko')
            items=extract_source(doc);self.assertTrue(items[0][0]['complete'])
            self.assertEqual(items[0][0]['choices'][0]['source_page'],2)
            doc.save(source);doc.close()
            r=build(source,root/'out.pdf',preview=False,**build_options({},root))
            self.assertEqual(r['pages'][0]['question_marks'],[])
            marks=r['pages'][1]['question_marks']
            self.assertEqual([m['number'] for m in marks],['1','2'])
            self.assertEqual(marks[0]['origin_page'],1)
            self.assertTrue(marks[0]['continuation'])
    def test_every_question_has_row_and_content_keeps_scale(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'source.pdf'
            doc=fitz.open();p=doc.new_page(width=600,height=800)
            for x,n in [(30,1),(330,3)]:
                for y,q in [(100,n),(350,n+1)]:
                    p.insert_text((x,y),f'{q}. Choose the answer.')
                    p.insert_text((x,y+30),'The problem ends with these options.')
                    p.draw_circle((x+90,y+65),15)
            p.insert_text((290,780),'1')
            doc.save(source);doc.close()
            report=build(source,root/'result.pdf',preview=False,**build_options({},root))
            marks=report['pages'][0]['question_marks'];layout=report['pages'][0]['question_layout']
            self.assertEqual(len(marks),4)
            self.assertTrue(all(m['qr_status']=='placed' and m['label_status']=='placed' for m in marks))
            self.assertTrue(all(m['qr_anchor']=='question-end' for m in marks))
            self.assertEqual(layout['added_height'],116)
            b=report['border_pt']
            slots=[s for c in layout['columns'] for s in c['slots']]
            for m,s in zip(marks,slots):
                self.assertGreater(m['qr_source_bbox'][1],m['question_end_y'])
                self.assertTrue(fitz.Rect(s['slot_bbox']).contains(fitz.Rect(m['label_source_bbox'])))
            with fitz.open(source) as a,fitz.open(root/'result.pdf') as z:
                for col in layout['columns']:
                    start=0;shift=0
                    for slot in col['slots']+ [{'cut':layout['footer']}]:
                        clip=fitz.Rect(col['x0']+1,start+1,col['x1']-1,slot['cut']-1)
                        if clip.height>1:
                            before=a[0].get_pixmap(clip=clip,alpha=False)
                            after=z[0].get_pixmap(clip=clip+(b,b+shift,b,b+shift),alpha=False)
                            diff=ImageChops.difference(Image.frombytes('RGB',(before.width,before.height),before.samples),
                                Image.frombytes('RGB',(after.width,after.height),after.samples))
                            self.assertIsNone(diff.getbbox())
                        start=slot['cut'];shift+=layout['gap']

    def test_shared_passage_stays_after_preceding_question_qr(self):
        doc=fitz.open();p=doc.new_page()
        p.insert_text((50,100),'1. First problem.')
        p.insert_text((50,130),'Last option for question one.')
        p.insert_text((50,200),'[2~3] Read the following passage.')
        p.insert_text((50,240),'This passage belongs to the next questions.')
        p.insert_text((50,300),'2. Next problem.')
        result,plans=reserve_question_rows(doc,40)
        slots=plans[0]['columns'][0]['slots']
        self.assertLess(slots[0]['cut'],190)
        result.close();doc.close()

    def test_rich_passage_with_diagram_replaces_only_outer_border(self):
        from passage_boxes import passage_frames
        doc=fitz.open();p=doc.new_page()
        p.draw_rect(fitz.Rect(40,100,450,400),color=(.5,.5,.5),fill=(1,1,1))
        p.insert_text((55,140),'This is a complete passage with many words explaining a diagram below.')
        p.insert_text((55,165),'Its surrounding frame can change while all of the content stays intact.')
        p.draw_circle((200,280),40)
        audit=[];frames=passage_frames(p,audit)
        self.assertEqual(len(frames),1)
        self.assertEqual(audit[0]['status'],'replaced')
        doc.close()

    def test_two_columns_when_questions_only_on_left(self):
        from question_layout import plan_page
        doc=fitz.open();p=doc.new_page(width=600,height=800)
        p.draw_line((300,80),(300,750))
        p.insert_text((40,100),'1. Question on the left.')
        p.insert_text((40,140),'Last option ends here.')
        p.draw_rect(fitz.Rect(330,100,560,500))
        plan=plan_page(p,40)
        self.assertEqual(len(plan['columns']),2)
        self.assertLess(plan['columns'][0]['slots'][0]['cut'],150)
        doc.close()

    def test_numbered_facts_and_date_are_not_question_headings(self):
        from question_layout import plan_page
        doc=fitz.open();p=doc.new_page(width=600,height=800)
        p.insert_text((48,100),'51. An actual exam question.')
        p.insert_text((80,140),'1. A numbered fact inside the question.')
        p.insert_text((414,170),'6. 30.')
        p.insert_text((48,300),'52. The next exam question.')
        plan=plan_page(p,40)
        self.assertEqual(len(plan['columns']),1)
        self.assertEqual([s['question']['number'] for s in plan['columns'][0]['slots']],['51','52'])
        doc.close()

    def test_links_follow_moved_questions_and_destinations(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'links.pdf';doc=fitz.open()
            for _ in range(2):
                p=doc.new_page()
                p.insert_text((50,100),'1. The first complete question.')
                p.insert_text((50,350),'2. The second complete question.')
            doc[0].insert_link(dict(kind=fitz.LINK_URI,**{'from':fitz.Rect(50,330,150,355)},uri='https://example.com'))
            doc[0].insert_link(dict(kind=fitz.LINK_GOTO,**{'from':fitz.Rect(160,330,260,355)},page=1,to=fitz.Point(50,350)))
            doc.save(source);doc.close()
            report=build(source,root/'result.pdf',preview=False,**build_options({},root))
            b=report['border_pt'];gap=report['pages'][0]['question_layout']['gap']
            with fitz.open(root/'result.pdf') as result:
                links=result[0].get_links()
                uri=next(l for l in links if l['kind']==fitz.LINK_URI)
                internal=next(l for l in links if l['kind']==fitz.LINK_GOTO)
                self.assertAlmostEqual(uri['from'].y0,330+gap+b,places=2)
                self.assertAlmostEqual(internal['to'].y,350+gap+b,places=2)
