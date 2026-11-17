import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evaluation'))
from PIL import ImageChops
from candidate_probe import item,make,FONT

class CandidateProbeTests(unittest.TestCase):
    def test_keys_and_balanced_splits(self):
        for start in (0,20):
            keys=[]
            for i in range(start,start+20):
                a,b,key,choices,target=item(i)
                self.assertEqual(choices[key-1],a+b)
                self.assertEqual(len(set(choices)),5)
                self.assertIn(target,range(1,6));keys.append(key)
            self.assertEqual([keys.count(k) for k in range(1,6)],[4]*5)
    def test_disjoint_arithmetic_inputs(self):
        a={item(i)[:2] for i in range(20)};b={item(i)[:2] for i in range(20,40)}
        self.assertFalse(a&b)
    @unittest.skipUnless(Path(FONT).exists(),'Windows font unavailable')
    def test_body_preserved(self):
        original,_,_=make(0,'original')
        for c in ('neutral','six','valid','remap'):
            marked,_,_=make(0,c)
            self.assertIsNone(ImageChops.difference(original.crop((0,220,1100,650)),marked.crop((0,220,1100,650))).getbbox())

if __name__=='__main__':unittest.main()
