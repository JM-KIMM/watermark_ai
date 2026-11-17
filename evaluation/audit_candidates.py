"""Independently reparse saved responses, reconstruct keys, and verify inputs."""
import hashlib
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from candidate_probe import item


def read(path):
    return json.loads(path.read_text(encoding='utf8'))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def parsed(row):
    for attempt in reversed(row['attempts']):
        if 'message' in attempt:
            return json.loads(re.sub(r'^```(?:json)?\s*|\s*```$', '', attempt['message']['content'].strip()))
    raise AssertionError('No model response')


def main():
    synthetic = ROOT / 'outputs/candidate_probe_20261118'
    real = ROOT / 'outputs/candidate_real_20261118'
    assert (synthetic / 'COMPLETE.json').exists() and (real / 'COMPLETE.json').exists()
    for folder, script, plan in [
        (synthetic, 'candidate_probe.py', 'CANDIDATE_PROTOCOL_2026-11-18.md'),
        (real, 'candidate_real_transfer.py', 'CANDIDATE_REAL_PROTOCOL_2026-11-18.md'),
    ]:
        config = read(folder / 'config.json')
        assert config['code_sha256'] == digest(ROOT / 'evaluation' / script)
        assert config['protocol_sha256'] == digest(ROOT / 'docs' / plan)
    syn = list((synthetic / 'raw').rglob('*.json'))
    assert len(syn) == 640
    for path in syn:
        row = read(path)
        assert row['status'] == 'ok'
        value = parsed(row)['answer']
        if isinstance(value, str) and value.strip().isdigit():
            value = int(value.strip())
        assert value == row['answer']
        a, b, key, choices, target = item(row['i'])
        assert choices[key - 1] == a + b
        assert key == row['key'] and target == row['target']
        assert row['image_sha256'] == digest(synthetic / 'images' / f"{row['i']:02d}-{row['condition']}.png")
    keys = {e['exam']: e['keys'] for e in read(ROOT / 'outputs/external_validity/inventory.json')}
    paths = list((real / 'responses').rglob('*.json'))
    assert len(paths) == 126
    public = read(ROOT / 'docs/evaluation/candidate_real_20261118.json')
    indexed = {(r['route'], r['condition'], r['exam'], str(r['question'])): r for r in public['rows']}
    checked = 0
    for path in paths:
        row = read(path)
        assert row['status'] == 'ok'
        answers = parsed(row)['answers']
        assert answers == row['answers']
        for q in row['questions']:
            result = indexed[row['route'], row['condition'], row['exam'], str(q)]
            assert result['key'] == keys[row['exam']][str(q)]
            assert result['answer'] == answers[str(q)]
            checked += 1
    assert checked == 504
    pixels = read(real / 'pixel_audit.json')
    assert all(p['body_max_delta'] == 0 for p in pixels)
    for p in pixels:
        for condition in ('control', 'candidate'):
            assert p[condition + '_sha256'] == digest(real / 'inputs' / p['exam'] / f"{condition}-{p['page']}.png")
    result = dict(synthetic_raw_reparsed=640, real_batches_reparsed=126,
                  real_answers_regraded=checked, real_body_pages_identical=len(pixels),
                  frozen_code_and_protocol_hashes_match=True)
    (ROOT / 'docs/evaluation/candidate_audit_20261118.json').write_text(json.dumps(result, indent=2) + '\n', encoding='utf8')
    print(json.dumps(result))


if __name__ == '__main__':
    main()
