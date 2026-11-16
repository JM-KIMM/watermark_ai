import unittest

from evaluation.audit_strict_evaluation import metrics,paired


def row(q,c,correct,cluster=None,status='ok',accepted=None):
    return dict(exam='exam',section='all',question=str(q),condition=c,correct=correct,
                cluster=cluster or str(q),status=status,accepted=accepted or [1],weight=1,answer=1)


class StrictAuditTests(unittest.TestCase):
    def test_duplicate_cluster_mean_differs_from_exposure_mean(self):
        rows=[]
        for q,cluster,a,b in [(1,'shared',0,1),(2,'shared',0,1),(3,'unique',1,0)]:
            rows += [row(q,'a',a,cluster),row(q,'b',b,cluster)]
        result=paired(rows,'a','b',100)
        self.assertAlmostEqual(result['delta_percentage_points'],100/3)
        self.assertEqual(result['cluster_mean_delta_percentage_points'],0)
        self.assertEqual((result['wrong_to_correct'],result['correct_to_wrong']),(2,1))

    def test_missing_response_is_unknown_not_a_known_wrong_answer(self):
        rows=[]
        for q in range(4):rows += [row(q,'a',0),row(q,'b',0,status='format_error' if q==0 else 'ok')]
        result=paired(rows,'a','b',100)
        self.assertEqual(result['pairs'],3)
        self.assertEqual(result['all_scheduled_delta_bounds_percentage_points'],[0,25])

    def test_all_correct_question_changes_chance_reference(self):
        result=metrics([row(1,'a',1,accepted=[1,2,3,4,5]),row(2,'a',0)])
        self.assertEqual(result['uniform_random_expected_percent'],60)
        self.assertEqual(result['constant_choice_correct']['1'],2)
        self.assertEqual(result['all_scheduled_accuracy_bounds_percent'],[50,50])
