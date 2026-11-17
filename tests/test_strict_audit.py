import unittest

from evaluation.audit_strict_evaluation import metrics,paired,request_groups,capture_keys


def row(q,c,correct,cluster=None,status='ok',accepted=None):
    return dict(exam='exam',section='all',question=str(q),condition=c,correct=correct,
                cluster=cluster or str(q),status=status,accepted=accepted or [1],weight=1,answer=1)


class StrictAuditTests(unittest.TestCase):
    def test_windows_seal_paths_match_portable_inference_lookup(self):
        seal={'captures':{r'captures\exam01\current_choices\page-001.png':'digest'}}
        self.assertEqual(capture_keys(seal)['captures/exam01/current_choices/page-001.png'],'digest')
        self.assertIn(r'captures\exam01\current_choices\page-001.png',seal['captures'])

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

    def test_shared_context_groups_are_transitive(self):
        inventory=[dict(id='exam',status='included',sections=[dict(id='odd',pages={
            '1':dict(questions=['1'],context=[1,2]),'2':dict(questions=['2'],context=[2,3]),
            '3':dict(questions=['3'],context=[3]),'4':dict(questions=['4'],context=[4])})])]
        groups=request_groups(inventory)
        self.assertEqual(groups['exam:english:1'],groups['exam:english:3'])
        self.assertNotEqual(groups['exam:english:1'],groups['exam:english:4'])

    def test_answered_wrong_and_no_answer_transitions_are_distinct(self):
        blank=row(1,'b',0);blank['answer']=None
        result=paired([row(1,'a',1),blank,row(2,'a',1),row(2,'b',0)],'a','b',100)
        self.assertEqual(result['correct_to_wrong'],2)
        self.assertEqual(result['correct_to_unanswered'],1)
        self.assertEqual(result['correct_to_answered_wrong'],1)

    def test_bootstrap_does_not_depend_on_file_or_row_order(self):
        rows=[]
        for q in range(30):
            rows += [row(q,'a',int(q%3==0),str(q//2)),row(q,'b',int(q%4==0),str(q//2))]
        first=paired(rows,'a','b',1000);second=paired(list(reversed(rows)),'a','b',1000)
        self.assertEqual(first['cluster_bootstrap_95'],second['cluster_bootstrap_95'])
        self.assertEqual(first['cluster_mean_bootstrap_95'],second['cluster_mean_bootstrap_95'])
