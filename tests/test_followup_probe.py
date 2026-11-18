import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evaluation'))
from PIL import ImageChops
import followup_probe as f
import layout_pilot as l

class FollowupTests(unittest.TestCase):
    def test_arithmetic_and_balance(self):
        for start,end in ((0,10),(10,40)):
            keys=[]
            for i in range(start,end):
                a,b,op,key,choices=f.item(i)
                value={'+':a+b,'-':a-b,'*':a*b}[op]
                self.assertEqual(choices[key-1],value)
                self.assertEqual(len(set(choices)),5);keys.append(key)
            self.assertEqual([keys.count(k) for k in range(1,6)],[(end-start)//5]*5)
        self.assertFalse({f.item(i)[:3] for i in range(10)} & {f.item(i)[:3] for i in range(10,40)})

    @unittest.skipUnless(Path(f.FONT).exists(),'Windows font unavailable')
    def test_followup_body_pixels(self):
        for i in (0,10,39):
            original=f.make(i,'original').crop((0,220,1200,680))
            for c in f.TEXTS:
                self.assertIsNone(ImageChops.difference(original,f.make(i,c).crop((0,220,1200,680))).getbbox())

    @unittest.skipUnless(Path(f.FONT).exists(),'Windows font unavailable')
    def test_layout_body_and_copied_values(self):
        for i in range(10):
            a,b,key,choices=l.item(i)
            self.assertEqual(choices[key-1],a+b)
            original=l.make(i,'original').crop((70,230,650,680))
            for c in ('symbols','distributed','concentrated'):
                self.assertIsNone(ImageChops.difference(original,l.make(i,c).crop((70,230,650,680))).getbbox())

if __name__=='__main__':unittest.main()
