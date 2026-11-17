import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'evaluation'))
import unittest
from research_statistics import calibration,holm,jsd,mcnemar_exact,paired_cluster

class ResearchStatisticsTests(unittest.TestCase):
    def test_exact_discordant_binomial(self):
        self.assertEqual(mcnemar_exact(0,0),1)
        self.assertAlmostEqual(mcnemar_exact(5,0),.0625)
        self.assertEqual(mcnemar_exact(5,5),1)
    def test_holm_order_and_monotonicity(self):
        self.assertEqual(holm([.04,.01,.03]),[.06,.03,.06])
    def test_perfect_calibration_and_separation(self):
        p=[1,0,0,0,0,0,0];q=[0,1,0,0,0,0,0]
        r=calibration([p],[1]);self.assertEqual(r['brier'],0);self.assertEqual(r['ece'],0)
        self.assertEqual(jsd(p,p),0);self.assertEqual(jsd(p,q),1)
    def test_cluster_zero_effect(self):
        r=paired_cluster([0,0,0],['a','a','b'],draws=100)
        self.assertEqual(r['clusters'],2);self.assertEqual(r['ci95'],[0,0]);self.assertEqual(r['sign_flip_p'],1)

if __name__=='__main__':unittest.main()
