import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch
from capture_evaluation import infer,summarize,write,CONDITIONS
from corpus_evaluation import ENG_EVEN


class CaptureEvaluationTests(unittest.TestCase):
    def test_official_even_english_44(self):
        self.assertEqual(ENG_EVEN[43],3)

    def test_model_receives_images_but_no_answer_key(self):
        calls=[]
        def fake(endpoint,payload,**kwargs):
            calls.append(payload)
            return {'message':{'content':'{"1":3}'}}
        with patch('capture_evaluation.request',fake):
            result=infer('local-vision',['PNG-BASE64'],['1'])
        self.assertEqual(result['answers'],{'1':3})
        self.assertEqual(calls[0]['messages'][0]['images'],['PNG-BASE64'])
        self.assertNotIn('accepted',json.dumps(calls))

    def test_multianswer_failure_and_pending_are_distinct(self):
        inv=[dict(id='exam',source='sample',status='included',sections=[dict(id='all',pages={'1':{}},
             answers={'1':[3,5],'2':2},weights={'1':1,'2':3})])]
        with TemporaryDirectory() as folder:
            out=Path(folder)
            for c in CONDITIONS:
                write(out/'responses'/'exam'/'all'/f'{c}-1.json',dict(answers={'1':5,'2':None}))
            report=summarize(out,inv)
            self.assertTrue(report['complete'])
            for score in report['scores'].values():
                self.assertEqual(score['correct'],1)
                self.assertEqual(score['inference_failures'],1)
                self.assertEqual(score['pending'],0)
                self.assertEqual(score['points'],1)
            (out/'responses'/'exam'/'all'/'watermarked-1.json').unlink()
            with self.assertRaises(ValueError):summarize(out,inv)
            partial=summarize(out,inv,partial=True)
            self.assertEqual(partial['scores']['watermarked']['pending'],2)
            self.assertEqual(partial['scores']['watermarked']['inference_failures'],0)
