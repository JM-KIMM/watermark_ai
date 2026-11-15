"""Corpus mapping checks against public answer files and local exam inventory."""
from pathlib import Path
import unittest
from corpus_evaluation import ROOT, KEYS, sections, contexts


class CorpusMappingTests(unittest.TestCase):
    def test_passage_context_and_formula_page_preservation(self):
        self.assertEqual(contexts('국어영역_문제지.pdf','odd_common',3,['5','10'],1,12),[2,3,4])
        self.assertEqual(contexts('국어영역_문제지.pdf','even_common',30,['27'],21,32),[29,30,31])
        self.assertEqual(contexts('수학영역_문제지.pdf','odd_common',5,['13','14'],1,6),[5])
        self.assertEqual(contexts('국어영역_문제지.pdf','odd_language',18,['38'],17,20),[17,18,19,20])

    @unittest.skipUnless((KEYS/'math_odd.pdf').exists(),'Downloaded official keys not installed')
    def test_every_objective_file_and_short_answer_exclusion(self):
        specs={p.name:sections(p) for p in ROOT.glob('*.pdf')}
        included={n:s for n,s in specs.items() if s}
        self.assertEqual(len(included),7)
        self.assertEqual(sum(len(section[3]) for s in included.values() for section in s),554)
        maths=next(s for n,s in included.items() if n.startswith('수학'))
        for name,start,end,key in maths:
            if name.endswith('common'):
                self.assertEqual(set(map(int,key)),set(range(1,16)))
            else:self.assertEqual(set(map(int,key)),set(range(23,29)))
        english=next(s for n,s in included.items() if n.startswith('영어'))
        for name,start,end,key in english:self.assertEqual(set(map(int,key)),set(range(18,46)))


if __name__=='__main__':unittest.main()
