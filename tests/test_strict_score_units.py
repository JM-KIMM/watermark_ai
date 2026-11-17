import json
from pathlib import Path
import unittest

from evaluation.strict_score_units import score_units


class ScoreUnitTests(unittest.TestCase):
    def test_all_correct_subject_maxima_and_no_elective_double_count(self):
        inventory=json.loads((Path(__file__).resolve().parent.parent/'docs/evaluation/capture_inventory.json').read_text(encoding='utf8'))
        rows=[dict(exam=e['id'],section=s['id'],question=q,weight=s['weights'][q],seed=42,condition='original',status='ok',correct=1)
              for e in inventory if e['status']=='included' for s in e['sections'] for q in s['answers']]
        units=score_units(rows)
        self.assertEqual(len(units),20)
        for u in units:
            expected=100 if u['exam'] in ('exam01','exam02','exam03','exam04','exam05') else 68 if u['exam']=='exam08' else 63
            self.assertEqual(u['max_points'],expected)
            self.assertEqual(u['points'],expected)

    def test_unresolved_is_visible_and_does_not_receive_points(self):
        rows=[dict(exam='exam09',section='odd',question='24',weight=1,seed=42,condition='original',status='format_error',correct=0)]
        u=score_units(rows)[0]
        self.assertEqual((u['max_points'],u['points'],u['unresolved']),(3,0,1))
        self.assertEqual(u['possible_points_range'],[0,3])
