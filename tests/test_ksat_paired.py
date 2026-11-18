import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evaluation'))
from ksat_paired import eligible
from ksat_analyze import summary

class KSATTests(unittest.TestCase):
    def test_exclude_listening_and_short_answers(self):
        self.assertFalse(eligible(dict(kind='multiple_choice',subject='english',number=17)))
        self.assertTrue(eligible(dict(kind='multiple_choice',subject='english',number=18)))
        self.assertFalse(eligible(dict(kind='short_answer',subject='math',number=22)))
        self.assertTrue(eligible(dict(kind='multiple_choice',subject='math',number=23)))

    def test_official_and_benchmark_grading_stay_separate(self):
        rows=[dict(id='2026-english-english-q37',key=5,answer=4,points=3,status='ok'),
              dict(id='other',key=1,answer=None,points=2,status='ok'),
              dict(id='third',key=2,answer=6,points=2,status='ok')]
        self.assertEqual(summary(rows)['score'],0)
        self.assertEqual(summary(rows,True)['score'],3)
        self.assertEqual(summary(rows)['max_score'],7)
        self.assertEqual(summary(rows)['abstain'],1)
        self.assertEqual(summary(rows)['invalid'],1)

if __name__=='__main__':unittest.main()
