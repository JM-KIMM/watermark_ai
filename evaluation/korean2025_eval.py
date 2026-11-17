# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""OCR -> text LLM accuracy test on one exam, same pipeline as evaluation/ocr_llm_evaluation.py.

usage: korean2025_eval.py <repo> <work dir> <stage> [gguf]
stages: plan (needs pymupdf) -> ocr (needs easyocr) -> llm (needs llama-cpp-python) -> score
        dist (needs llama-cpp-python) -> dist_score: answer probability per question, docs/DISTRIBUTION_EXPERIMENT.md
The work dir holds exam/korean_odd.pdf, exam/korean_key.pdf and inputs/<condition>.pdf from korean2025_build.py.
The exam is the 2025 CSAT Korean paper, odd form: 34 common + 11 + 11 elective questions.
"""
import collections
import json
import os
import sys
from pathlib import Path

repo, work, stage = Path(sys.argv[1]), Path(sys.argv[2]), sys.argv[3]
sys.path.insert(0, str(repo))
sys.path.insert(0, str(repo / 'evaluation'))
import ocr_llm_evaluation as ev  # noqa: E402
import random  # noqa: E402


def bait_number(seed_key, question_key):
    """Same seed as decoy_lines.bait_number; copied so the llm interpreter does not need PyMuPDF."""
    return random.Random(f'{seed_key}|{question_key}|decoy-v1').randint(1, 5)


SEED = 'korean2025odd'
EXAM = work / 'exam' / 'korean_odd.pdf'
KEY = work / 'exam' / 'korean_key.pdf'
CONDITIONS = ('original', 'border', 'frames', 'frames_labelled', 'lines', 'frames6')
# Shared passages of the common part: (first question, last question, first page, last page).
GROUPS = [(1, 3, 1, 1), (4, 9, 2, 3), (10, 13, 4, 5), (14, 17, 5, 6), (18, 21, 6, 7), (22, 27, 8, 9), (28, 31, 10, 11), (32, 34, 11, 12)]


def pdf_of(condition):
    return EXAM if condition == 'original' else work / 'inputs' / f'{condition}.pdf'


def plan():
    import pymupdf as fitz
    from question_marks import detect_questions
    # The official key PDF is a scanned image without a text layer or table structure, so the odd-form
    # answers are transcribed from its first page (2025학년도 대학수학능력시험 국어 영역 정답표, 홀수형).
    with fitz.open(KEY) as key_doc:
        if key_doc[0].get_text().strip():
            print('NOTE: the key PDF has a text layer; check the transcription against it', flush=True)
    def keyed(first, digits):
        return {str(first + i): [int(d)] for i, d in enumerate(digits)}
    sections = [('common', 1, 12, keyed(1, '3454532123153122324144522114354352')),
                ('speech', 13, 16, keyed(35, '24345431152')), ('language', 17, 20, keyed(35, '54312435213'))]
    batches = []
    with fitz.open(EXAM) as doc:
        for section, start, end, key in sections:
            seen = set()
            for p in range(start, end + 1):
                qs = sorted({q['number'] for q in detect_questions(doc[p - 1]) if q['number'] in key} - seen, key=int)
                if not qs:
                    continue
                seen.update(qs)
                if section == 'common':
                    context = sorted({page for q in qs for lo, hi, a, b in GROUPS if lo <= int(q) <= hi for page in range(a, b + 1)})
                else:
                    context = list(range(start, end + 1))
                batches.append(dict(id=f'{section}-{p}', section=section, page=p, questions=qs, context=context,
                                    answers={q: key[q] for q in qs}))
            if seen != set(key):
                raise ValueError(f'Incomplete mapping {section}: {sorted(set(key) - seen, key=int)}')
        pages = sorted({p for b in batches for p in b['context']})
        folder = work / 'ocr' / 'textlayer'; folder.mkdir(parents=True, exist_ok=True)
        for p in pages:
            (folder / f'{p}.json').write_text(json.dumps(dict(page=p, text=doc[p - 1].get_text()), ensure_ascii=False), encoding='utf8')
    (work / 'plan.json').write_text(json.dumps(dict(batches=batches, pages=pages), ensure_ascii=False, indent=1), encoding='utf8')
    print('PLAN questions', sum(len(b['questions']) for b in batches), 'batches', len(batches), 'pages', len(pages), flush=True)


def load():
    return json.loads((work / 'plan.json').read_text(encoding='utf8'))


def ocr():
    import easyocr
    import numpy as np
    import pymupdf as fitz
    reader = easyocr.Reader(['ko', 'en'], gpu=True)
    for condition in CONDITIONS:
        with fitz.open(pdf_of(condition)) as doc:
            for page in load()['pages']:
                cache = work / 'ocr' / condition / f'{page}.json'
                if cache.exists():
                    continue
                cache.parent.mkdir(parents=True, exist_ok=True)
                pix = doc[page - 1].get_pixmap(dpi=ev.DPI, colorspace=fitz.csRGB, alpha=False)
                image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                boxes = [([[float(a), float(b)] for a, b in box], text, float(conf)) for box, text, conf in reader.readtext(image)]
                cache.write_text(json.dumps(dict(page=page, width=pix.width, text=ev.reading_order(boxes, pix.width, 2), boxes=boxes), ensure_ascii=False), encoding='utf8')
                print('OCR', condition, page, len(boxes), flush=True)


def text_of(condition, page):
    return json.loads((work / 'ocr' / condition / f'{page}.json').read_text(encoding='utf8'))['text']


def llm():
    for site in map(Path, sys.path):
        for folder in (site / 'nvidia').glob('*/bin') if (site / 'nvidia').is_dir() else ():
            os.add_dll_directory(str(folder)); os.environ['PATH'] = str(folder) + os.pathsep + os.environ['PATH']
    import llama_cpp
    if not llama_cpp.llama_supports_gpu_offload():
        raise RuntimeError('This llama-cpp-python build has no GPU offload')
    model = llama_cpp.Llama(model_path=sys.argv[4], n_gpu_layers=-1, n_ctx=ev.N_CTX, seed=42, verbose=False)
    for condition in ('textlayer',) + CONDITIONS:
        for batch in load()['batches']:
            cache = work / 'llm' / condition / f"{batch['id']}.json"
            if cache.exists():
                continue
            cache.parent.mkdir(parents=True, exist_ok=True)
            qs = batch['questions']
            text = '\n\n'.join(text_of(condition, p) for p in batch['context'])
            # Identical wording to evaluation/ocr_llm_evaluation.py.
            prompt = (f"아래는 시험지 {len(batch['context'])}쪽을 문자 인식(OCR)으로 읽은 텍스트입니다.\n\n----- 시험지 텍스트 시작 -----\n"
                      + text + '\n----- 시험지 텍스트 끝 -----\n\n'
                      + ', '.join(qs) + '번 문제를 풀어 주세요. 문제와 선택지를 다시 적지 말고, 문제마다 "' + qs[0]
                      + '번: 정답 N - 이유 한 문장" 형식으로 한 줄씩만 쓰세요(N은 고른 선택지 번호 1~5). 마지막 줄에는 {"' + qs[0]
                      + '": N} 과 같은 형태의 JSON 하나로 모든 문제의 정답 번호를 정리해 주세요.')
            record = dict(condition=condition, batch=batch['id'], questions=qs, context_pages=batch['context'])
            try:
                response = model.create_chat_completion([dict(role='user', content=prompt)], temperature=0, seed=42, max_tokens=ev.MAX_NEW_TOKENS)
                raw = response['choices'][0]['message']['content'] or ''
                answers, parser = ev.parse_answers(raw, qs)
                record.update(answers=answers, parser=parser, prompt_tokens=response['usage']['prompt_tokens'],
                              finish_reason=response['choices'][0]['finish_reason'], error=None, raw=raw)
            except ValueError as exc:  # prompt longer than the context window: no fabricated answer
                record.update(answers={}, parser='none', prompt_tokens=None, finish_reason=None, error='context-overflow: ' + str(exc)[:200], raw='')
            cache.write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding='utf8')
            print('LLM', condition, batch['id'], record['answers'], record['finish_reason'], record['error'] or '', flush=True)


def score():
    from math import comb
    batches = load()['batches']
    rows = collections.defaultdict(dict)
    stats = {}
    for condition in ('textlayer',) + CONDITIONS:
        s = collections.Counter()
        for batch in batches:
            record = json.loads((work / 'llm' / condition / f"{batch['id']}.json").read_text(encoding='utf8'))
            s['overflow'] += bool(record['error']); s['truncated'] += record['finish_reason'] == 'length'
            for q in batch['questions']:
                answer = record['answers'].get(q); bait = bait_number(SEED, f"{batch['page']}-{q}")
                ok = answer in batch['answers'][q]
                rows[(batch['section'], q)][condition] = dict(answer=answer, correct=ok, bait=bait, bait_correct=bait in batch['answers'][q])
                s['total'] += 1; s['answered'] += answer is not None; s['correct'] += ok; s['equals_bait'] += answer == bait
        stats[condition] = s
    print(f"{'condition':<16}{'correct':>9}{'answered':>10}{'=bait':>7}{'lost':>6}{'gained':>8}{'p':>7}  overflow/truncated batches")
    for condition, s in stats.items():
        lost = sum(r['original']['correct'] and not r[condition]['correct'] for r in rows.values())
        gained = sum(not r['original']['correct'] and r[condition]['correct'] for r in rows.values())
        n, k = lost + gained, min(lost, gained)
        p = min(1.0, 2 * sum(comb(n, i) for i in range(k + 1)) / 2 ** n) if n else 1.0
        print(f"{condition:<16}{s['correct']:>4}/{s['total']:<4}{s['answered']:>10}{s['equals_bait']:>7}{lost:>6}{gained:>8}{p:>7.2f}  {s['overflow']}/{s['truncated']}")
    wrong_bait = [k for k, r in rows.items() if not r['original']['bait_correct']]
    print(f'\nquestions whose bait number is a wrong answer: {len(wrong_bait)} of {len(rows)}')
    for condition in stats:
        print(f"  {condition:<16} correct {sum(rows[k][condition]['correct'] for k in wrong_bait)}")
    result = dict(stats={c: dict(s) for c, s in stats.items()},
                  questions=[dict(section=k[0], question=k[1], **{c: v for c, v in r.items()}) for k, r in rows.items()])
    (work / 'scores.json').write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding='utf8')



DIST_CONDITIONS = ('textlayer', 'original', 'border', 'frames', 'frames_labelled', 'frames6', 'lines')
DIGITS = '123456'


def dist():
    """Next-token distribution over the choice digits, one question per request (docs/DISTRIBUTION_EXPERIMENT.md).

    The assistant turn is started with "<q>번: 정답 " and the model's probability for every token that
    reads as a single digit is summed per digit. Nothing is sampled, so the numbers do not depend on a seed.
    """
    import numpy as np
    for site in map(Path, sys.path):
        for folder in (site / 'nvidia').glob('*/bin') if (site / 'nvidia').is_dir() else ():
            os.add_dll_directory(str(folder)); os.environ['PATH'] = str(folder) + os.pathsep + os.environ['PATH']
    import llama_cpp
    from llama_cpp.llama_chat_format import Jinja2ChatFormatter
    model = llama_cpp.Llama(model_path=sys.argv[4], n_gpu_layers=-1, n_ctx=ev.N_CTX, seed=42, verbose=False)
    bos = model.detokenize([model.token_bos()], special=True).decode('utf8', 'ignore')
    eos = model.detokenize([model.token_eos()], special=True).decode('utf8', 'ignore')
    formatter = Jinja2ChatFormatter(template=model.metadata['tokenizer.chat_template'], eos_token=eos, bos_token=bos, add_generation_prompt=True)
    digit_tokens = collections.defaultdict(list)
    for token in range(model.n_vocab()):
        piece = model.detokenize([token]).decode('utf8', 'ignore').strip()
        if len(piece) == 1 and piece in '123456789':
            digit_tokens[piece].append(token)
        elif len(piece) == 1 and piece in '①②③④⑤⑥':
            digit_tokens[str('①②③④⑤⑥'.index(piece) + 1)].append(token)
    print('digit tokens', {d: len(t) for d, t in sorted(digit_tokens.items())}, flush=True)
    for condition in DIST_CONDITIONS:
        for batch in load()['batches']:
            cache = work / 'dist' / condition / f"{batch['id']}.json"
            if cache.exists():
                continue
            cache.parent.mkdir(parents=True, exist_ok=True)
            text = '\n\n'.join(text_of(condition, p) for p in batch['context'])
            head = (f"아래는 시험지 {len(batch['context'])}쪽을 문자 인식(OCR)으로 읽은 텍스트입니다.\n\n----- 시험지 텍스트 시작 -----\n"
                    + text + '\n----- 시험지 텍스트 끝 -----\n\n')
            rows = {}
            for q in batch['questions']:
                ask = head + f'{q}번 문제를 풀어 주세요. "{q}번: 정답 N" 형식으로 고른 선택지 번호 N 하나만 쓰세요.'
                prompt = formatter(messages=[dict(role='user', content=ask)]).prompt + f'{q}번: 정답 '
                tokens = model.tokenize(prompt.encode('utf8'), add_bos=not prompt.startswith(bos), special=True)
                if len(tokens) + 4 > ev.N_CTX:
                    rows[q] = dict(error='context-overflow', prompt_tokens=len(tokens)); continue
                stream = model.generate(tokens, temp=0.0)   # reuses the shared prefix of the previous request
                first = next(stream); stream.close()
                logits = np.ctypeslib.as_array(llama_cpp.llama_get_logits_ith(model.ctx, -1), shape=(model.n_vocab(),)).astype(np.float64)
                probs = np.exp(logits - logits.max()); probs /= probs.sum()
                rows[q] = dict(error=None, prompt_tokens=len(tokens), first=model.detokenize([first]).decode('utf8', 'ignore'),
                               p={d: float(probs[t].sum()) for d, t in sorted(digit_tokens.items())},
                               top=[[model.detokenize([int(i)]).decode('utf8', 'ignore'), float(probs[i])] for i in np.argsort(-probs)[:5]])
            cache.write_text(json.dumps(dict(condition=condition, batch=batch['id'], questions=rows), ensure_ascii=False, indent=1), encoding='utf8')
            print('DIST', condition, batch['id'], {q: (max(r['p'], key=r['p'].get), round(max(r['p'].values()), 2)) if not r['error'] else r['error'] for q, r in rows.items()}, flush=True)


def dist_score():
    import math
    import random as rnd
    batches = load()['batches']
    data = collections.defaultdict(dict)   # (section, q) -> condition -> record
    for condition in DIST_CONDITIONS:
        for batch in batches:
            record = json.loads((work / 'dist' / condition / f"{batch['id']}.json").read_text(encoding='utf8'))
            for q in batch['questions']:
                r = record['questions'][q]
                if r['error']:
                    data[(batch['section'], q)][condition] = None; continue
                raw = [r['p'].get(d, 0.0) for d in DIGITS]
                mass = sum(raw)
                norm = [v / mass for v in raw]
                key = batch['answers'][q][0]; bait = bait_number(SEED, f"{batch['page']}-{q}")
                data[(batch['section'], q)][condition] = dict(
                    batch=batch['id'], key=key, bait=bait, digit_mass=mass, p=norm, p_correct=norm[key - 1], p_six=norm[5], p_bait=norm[bait - 1],
                    argmax=norm.index(max(norm)) + 1, correct=norm.index(max(norm)) + 1 == key,
                    entropy=-sum(v * math.log2(v) for v in norm if v > 0))

    def js(a, b):
        m = [(x + y) / 2 for x, y in zip(a, b)]
        def kl(u, v):
            return sum(x * math.log2(x / y) for x, y in zip(u, v) if x > 0)
        return (kl(a, m) + kl(b, m)) / 2

    def interval(values_by_cluster, iterations=10000):
        """95% interval of the mean, resampling the shared-passage requests (clusters) with replacement."""
        clusters = [values_by_cluster[k] for k in sorted(values_by_cluster)]
        rng = rnd.Random(20261117); means = []
        for _ in range(iterations):
            pick = [clusters[rng.randrange(len(clusters))] for _ in clusters]
            flat = [v for c in pick for v in c]
            means.append(sum(flat) / len(flat))
        means.sort()
        return means[int(.025 * iterations)], means[int(.975 * iterations) - 1]

    usable = [k for k, r in data.items() if all(r.get(c) for c in DIST_CONDITIONS)]
    summary = {}
    print(f'questions with a distribution in every condition: {len(usable)} of {len(data)}')
    print(f"{'condition':<16}{'acc':>7}{'P(key)':>8}{'P(6)':>7}{'P(bait)':>8}{'H bits':>7}{'JSD':>6}{'digits':>8}   dP(key) vs original [95% CI]   dP(key) vs border [95% CI]")
    for condition in DIST_CONDITIONS:
        rows = [data[k][condition] for k in usable]
        def mean(name):
            return sum(r[name] for r in rows) / len(rows)
        entry = dict(n=len(rows), accuracy=sum(r['correct'] for r in rows), p_correct=mean('p_correct'), p_six=mean('p_six'), p_bait=mean('p_bait'),
                     entropy=mean('entropy'), digit_mass=mean('digit_mass'),
                     jsd_vs_original=sum(js(data[k]['original']['p'], data[k][condition]['p']) for k in usable) / len(usable))
        for base in ('original', 'border'):
            diffs = collections.defaultdict(list)
            for k in usable:
                diffs[data[k][condition]['batch']].append(data[k][condition]['p_correct'] - data[k][base]['p_correct'])
            flat = [v for c in diffs.values() for v in c]
            entry[f'delta_p_correct_vs_{base}'] = dict(mean=sum(flat) / len(flat), ci95=interval(diffs), clusters=len(diffs))
        summary[condition] = entry
        d, b = entry['delta_p_correct_vs_original'], entry['delta_p_correct_vs_border']
        print(f"{condition:<16}{entry['accuracy']:>4}/{entry['n']:<3}{entry['p_correct']:>7.3f}{entry['p_six']:>7.3f}{entry['p_bait']:>8.3f}{entry['entropy']:>7.2f}{entry['jsd_vs_original']:>6.2f}{entry['digit_mass']:>8.3f}"
              f"   {d['mean']:+.3f} [{d['ci95'][0]:+.3f}, {d['ci95'][1]:+.3f}]   {b['mean']:+.3f} [{b['ci95'][0]:+.3f}, {b['ci95'][1]:+.3f}]")
    out = dict(protocol=dict(digits=DIGITS, conditions=DIST_CONDITIONS, bootstrap='10000 resamples of shared-passage requests, seed 20261117'), summary=summary,
               questions=[dict(section=k[0], question=k[1], **{c: data[k][c] for c in DIST_CONDITIONS}) for k in data])
    (work / 'dist_scores.json').write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf8')


{'plan': plan, 'ocr': ocr, 'llm': llm, 'score': score, 'dist': dist, 'dist_score': dist_score}[stage]()
