import json
from pathlib import Path
import unittest
from strict_model_client import parse,schema
from strict_evaluation import select_pilot,cluster


class StrictEvaluationTests(unittest.TestCase):
    def test_final_answers_not_numbers_in_reasons(self):
        raw=json.dumps(dict(brief_reasons={'1':'Option 1 is false; the decisive result matches option 3.'},answers={'1':3}))
        self.assertEqual(parse(raw,['1']),{'1':3})
        explicit=json.dumps(dict(brief_reasons={'1':'reason'},answers={'1':'③'}))
        self.assertEqual(parse(explicit,['1']),{'1':3})
        self.assertEqual(parse(json.dumps(dict(brief_reasons={'1':'missing input'},answers={'1':None})),['1']),{'1':None})
        with self.assertRaises(ValueError):parse(json.dumps(dict(brief_reasons={'1':'r'},answers={'1':True})),['1'])

    def test_fixed_pilot_has_no_duplicate_clusters_and_covers_all_files(self):
        inv=json.loads((Path(__file__).resolve().parent.parent/'docs/evaluation/capture_inventory.json').read_text(encoding='utf8'))
        pilot=select_pilot(inv)
        self.assertEqual(len(pilot),70);self.assertEqual(len({p['cluster'] for p in pilot}),70)
        self.assertEqual(len({p['exam'] for p in pilot}),7)
        clusters={cluster(e,s['id'],q) for e in inv if e['status']=='included' for s in e['sections'] for q in s['answers']}
        self.assertEqual(len(clusters),357)
