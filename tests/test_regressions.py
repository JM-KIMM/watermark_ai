from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import pymupdf as fitz
from PIL import Image, ImageChops
from watermark import build
from benchmark_local import grade, validate_choice_key


class RegressionTests(unittest.TestCase):
    def test_rotation_and_visible_annotation_preservation(self):
        with TemporaryDirectory() as folder:
            root=Path(folder)
            for angle in (0,90,180,270):
                doc=fitz.open();p=doc.new_page()
                p.insert_text((80,150),'1. Choose the correct answer from these alternatives.')
                p.add_rect_annot(fitz.Rect(260,260,330,300)).update()
                p.insert_link({'kind':fitz.LINK_URI,'from':fitz.Rect(80,130,150,155),'uri':'https://example.com'})
                p.set_rotation(angle)
                source=root/f'source{angle}.pdf';doc.save(source);doc.close()
                output=root/f'out{angle}.pdf'
                report=build(source,output,intensity=1,preview=False)
                with fitz.open(source) as a,fitz.open(output) as b:
                    before=a[0].get_pixmap(alpha=False);after=b[0].get_pixmap(alpha=False)
                    self.assertEqual((before.width,before.height),(after.width,after.height))
                    delta=ImageChops.difference(Image.frombytes('RGB',(before.width,before.height),before.samples),Image.frombytes('RGB',(after.width,after.height),after.samples))
                    from PIL import ImageDraw
                    draw=ImageDraw.Draw(delta)
                    for mark in report['pages'][0]['question_marks']:
                        if mark['qr_status']=='placed':
                            for key in ('qr_bbox','label_bbox'):
                                if key in mark:
                                    x0,y0,x1,y1=mark[key];draw.rectangle((int(x0)-2,int(y0)-2,int(x1)+2,int(y1)+2),fill=0)
                    self.assertLessEqual(max(v[1] for v in delta.getextrema()),2, f'rotation={angle}, bbox={delta.getbbox()}')
                    self.assertEqual(b[0].get_links()[0]['uri'],'https://example.com')

    def test_grading_multianswer_and_omissions(self):
        result=grade({'1':'3','2':'5'},{'1':[3,5],'2':2,'3':1})
        self.assertEqual(result['correct'],1)
        self.assertEqual(result['total'],3)
        self.assertEqual(result['answered'],2)
        failed=grade({'1':None},{'1':1})
        self.assertEqual(failed['correct'],0)
        self.assertEqual(failed['answered'],0)

    def test_reject_descriptive_and_misaligned_keys(self):
        valid=dict(question_type='multiple_choice',pages={'1':['1','2']},answers={'1':1,'2':[3,5]})
        validate_choice_key(valid)
        with self.assertRaises(ValueError):
            validate_choice_key(dict(valid,question_type='descriptive'))
        with self.assertRaises(ValueError):
            validate_choice_key(dict(valid,pages={'1':['1','1']}))
        with self.assertRaises(ValueError):
            validate_choice_key(dict(valid,answers={'1':1,'2':'essay answer'}))


if __name__=='__main__': unittest.main()
