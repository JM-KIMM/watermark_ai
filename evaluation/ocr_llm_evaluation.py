# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""OCR -> text LLM evaluation: EasyOCR + skt/A.X-4.0-Light on every local objective exam.

Stages are separate and resumable: prepare -> ocr -> llm -> summarize.
Answers are never sent to the model. Everything runs locally.
Exam PDFs and official answer tables are read from outputs/exams (not distributed).
"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repository root
import argparse
import collections
import json
import os
import re
import sys
from pathlib import Path

try:
    import pymupdf as fitz
except ImportError:  # the llm stage can run in an interpreter that only has llama-cpp-python
    fitz = None

ROOT = Path(__file__).resolve().parent.parent
EXAMS = ROOT / 'outputs/exams'
OUT = ROOT / 'outputs/ocr_llm_eval'
MODEL = 'skt/A.X-4.0-Light Q4_K_M GGUF (llama-cpp-python, full GPU offload)'
# Local quantized weights; override with the AX_GGUF environment variable.
GGUF = Path(os.environ.get('AX_GGUF', ROOT / 'models' / 'A.X-4.0-Light-Q4_K_M.gguf'))
DPI = 200
N_CTX = 16384  # the model's documented maximum
MAX_NEW_TOKENS = 1000
# level4 is the experimental decoy-text variant built by decoy_watermark.py from the original PDF.
# level5: the level2 border plus template bait between body lines (decoy_lines.py).
# level6: the same bait on the page border and passage-box frames instead.
# level7: the generator's default, level6 with every sentence labelled as not part of the paper.
CONDITIONS = ('original', 'level1', 'level2', 'level4', 'level5', 'level6', 'level7')
CIRCLED = {c: i + 1 for i, c in enumerate('①②③④⑤')}
WORD = re.compile(r'[A-Za-z가-힣0-9]+')
# Tax accountant keys as already transcribed in prepare_benchmark.py / corpus_evaluation.py.
TAX_SESSION1 = [1,4,3,5,3,4,2,1,4,5,3,3,1,[3,5],3,2,3,3,1,2,2,4,3,1,2,4,4,3,5,2,4,4,5,1,3,1,4,5,5,2,
                3,2,3,3,3,2,4,5,2,4,4,2,[1,2,3,4,5],1,1,4,2,2,5,5,1,5,1,5,1,5,2,2,4,3,5,4,1,1,4,4,5,5,5,3]


def table_key(pdf, page):
    """Official KICE table: (number, answer, points) column triples; objective answers only."""
    with fitz.open(pdf) as doc:
        rows = doc[page].find_tables().tables[0].extract()
    width = max(len(r) for r in rows)
    result = [{} for _ in range(width // 3)]
    for row in rows:
        for col in range(0, len(row) - 2, 3):
            n, a, _ = row[col:col + 3]
            if n and n.strip().isdigit() and a in CIRCLED:
                result[col // 3][str(int(n))] = [CIRCLED[a]]
    return result


def sections(name, source):
    """(section id, first page, last page, {question: accepted answers}) for one exam file."""
    if name == 'english':  # listening 1-17 excluded; one table of four column groups per form
        result = []
        for form, offset, page in (('odd', 0, 0), ('even', 8, 1)):
            cols = table_key(EXAMS / 'kice_english_key.pdf', page)
            key = {q: v for col in cols for q, v in col.items() if int(q) >= 18}
            result.append((form, offset + 2, offset + 8, key))
        return result
    if name == 'korean':
        result = []
        for form, offset, page in (('odd', 0, 0), ('even', 20, 1)):
            cols = table_key(EXAMS / 'kice_korean_key.pdf', page)
            result += [(form + '_common', offset + 1, offset + 12, cols[0] | cols[1]),
                       (form + '_speech', offset + 13, offset + 16, cols[2]),
                       (form + '_language', offset + 17, offset + 20, cols[3])]
        return result
    if name == 'math':  # short-answer 16-22, 29-30 are not circled and are dropped by table_key
        result = []
        for form, offset, page in (('odd', 0, 0), ('even', 20, 1)):
            cols = table_key(EXAMS / 'kice_math_key.pdf', page)
            result += [(form + '_common', offset + 1, offset + 6, cols[0] | cols[1]),
                       (form + '_probability', offset + 9, offset + 11, cols[2]),
                       (form + '_calculus', offset + 13, offset + 15, cols[3]),
                       (form + '_geometry', offset + 17, offset + 19, cols[4])]
        return result
    if name.startswith('tax'):
        from corpus_evaluation import TAX_ACCOUNT, TAX_LAWS
        values = TAX_SESSION1 if name == 'tax1' else TAX_ACCOUNT + TAX_LAWS[{'tax2_civil': '민법', 'tax2_commercial': '상법', 'tax2_admin': '행정소송법'}[name]]
        with fitz.open(source) as doc:
            count = len(doc)
        return [('all', 1, count, {str(i + 1): v if isinstance(v, list) else [v] for i, v in enumerate(values)})]
    raise ValueError(name)


def exam_sources():
    found = {n: EXAMS / f'kice_{n}.pdf' for n in ('english', 'korean', 'math') if (EXAMS / f'kice_{n}.pdf').exists()}
    for folder in (EXAMS, ROOT):  # optional: tax accountant papers, if the user has them
        for pdf in folder.glob('2026*세무사*.pdf'):
            if '1교시' in pdf.name: found['tax1'] = pdf
            for word, name in (('민법', 'tax2_civil'), ('상법', 'tax2_commercial'), ('행정소송법', 'tax2_admin')):
                if word in pdf.name: found[name] = pdf
    return found


def contexts(name, section, page, questions, start, end):
    """Pages whose text the model needs; same grouping as corpus_evaluation.py."""
    if name == 'korean':
        if section.endswith('common'):
            groups = [(1, 3, 1, 1), (4, 9, 2, 3), (10, 13, 3, 4), (14, 17, 5, 6), (18, 21, 6, 7),
                      (22, 26, 8, 9), (27, 30, 9, 11), (31, 34, 11, 12)]
            return sorted({p + start - 1 for q in questions for lo, hi, a, b in groups if lo <= int(q) <= hi for p in range(a, b + 1)})
        return list(range(start, end + 1))
    return [page]


def load_plan():
    return json.loads((OUT / 'plan.json').read_text(encoding='utf-8'))


def source_pdf(exam, condition):
    return Path(exam['source']) if condition == 'original' else OUT / exam['id'] / 'inputs' / f'{condition}.pdf'


def prepare():
    from question_marks import detect_questions
    from watermark import build
    plan = []
    for name, source in exam_sources().items():
        exam = dict(id=name, source=str(source), batches=[], pages=[])
        with fitz.open(source) as doc:
            for section, start, end, key in sections(name, source):
                seen = set()
                for p in range(start, end + 1):
                    qs = sorted({q['number'] for q in detect_questions(doc[p - 1]) if q['number'] in key} - seen, key=int)
                    if qs:
                        seen.update(qs)
                        exam['batches'].append(dict(id=f'{section}-{p}', section=section, page=p, questions=qs,
                            context=contexts(name, section, p, qs, start, end), answers={q: key[q] for q in qs}))
                if seen != set(key):
                    raise ValueError(f'Incomplete mapping: {name}/{section}: {sorted(set(key) - seen, key=int)}')
            exam['pages'] = sorted({p for b in exam['batches'] for p in b['context']})
            folder = OUT / name / 'ocr' / 'textlayer'; folder.mkdir(parents=True, exist_ok=True)
            for p in exam['pages']:  # no-OCR reference input: the original PDF text layer
                (folder / f'{p}.json').write_text(json.dumps(dict(page=p, text=doc[p - 1].get_text()), ensure_ascii=False), encoding='utf-8')
        (OUT / name / 'inputs').mkdir(parents=True, exist_ok=True)
        for level in (1, 2):
            target = OUT / name / 'inputs' / f'level{level}.pdf'
            if not target.exists():
                report = build(source, target, intensity=level, font_mode='source', size_jitter=.25,
                               prompts_file=ROOT / 'prompts_ko.json')
                placed = sum(m['qr_status'] == 'placed' for p in report['pages'] for m in p['question_marks'])
                print('BUILT', name, target.name, 'QR placed', placed, flush=True)
        for level, placement, style in ((5, 'lines', 'plain'), (6, 'frames', 'plain'), (7, 'frames', 'labelled')):
            target = OUT / name / 'inputs' / f'level{level}.pdf'
            if not target.exists():
                # decoy_seed=name reproduces the bait numbers of decoy_watermark.py, so summarize() can count follows.
                report = build(source, target, intensity=2, font_mode='source', size_jitter=.25,
                               prompts_file=ROOT / 'prompts_ko.json', decoy=placement, decoy_style=style, decoy_seed=name)
                print('BUILT', name, target.name, 'decoy lines', sum(len(p['decoy_lines']) for p in report['pages']),
                      'frames', sum(len(p['passage_boxes']) for p in report['pages']), flush=True)
        plan.append(exam)
        print('PLAN', name, 'questions', sum(len(b['questions']) for b in exam['batches']), 'batches', len(exam['batches']), 'pages', len(exam['pages']), flush=True)
    (OUT / 'plan.json').write_text(json.dumps(plan, ensure_ascii=False, indent=2), encoding='utf-8')


def reading_order(boxes, width, columns=2):
    """Naive reading order, as a generic OCR pipeline would produce (CSAT papers are two-column)."""
    items = []
    for box, text, conf in boxes:
        xs = [p[0] for p in box]; ys = [p[1] for p in box]
        items.append(dict(x=min(xs), y=(min(ys) + max(ys)) / 2, h=max(ys) - min(ys), cx=(min(xs) + max(xs)) / 2, text=text))
    lines = []
    for column in ([items] if columns == 1 else [[i for i in items if i['cx'] < width / 2], [i for i in items if i['cx'] >= width / 2]]):
        column.sort(key=lambda i: i['y'])
        rows = []
        for item in column:
            if rows and abs(item['y'] - rows[-1][-1]['y']) < .6 * max(item['h'], 1):
                rows[-1].append(item)
            else:
                rows.append([item])
        lines.extend(' '.join(i['text'] for i in sorted(row, key=lambda i: i['x'])) for row in rows)
    return '\n'.join(lines)


def ocr():
    import easyocr
    import numpy as np
    reader = easyocr.Reader(['ko', 'en'], gpu=True)
    for exam in load_plan():
        for condition in CONDITIONS:
            with fitz.open(source_pdf(exam, condition)) as doc:
                for page in exam['pages']:
                    cache = OUT / exam['id'] / 'ocr' / condition / f'{page}.json'
                    if cache.exists():
                        continue
                    cache.parent.mkdir(parents=True, exist_ok=True)
                    pix = doc[page - 1].get_pixmap(dpi=DPI, colorspace=fitz.csRGB, alpha=False)
                    image = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, 3)
                    boxes = [([[float(a), float(b)] for a, b in box], text, float(conf)) for box, text, conf in reader.readtext(image)]
                    cache.write_text(json.dumps(dict(condition=condition, page=page, width=pix.width, height=pix.height,
                        text=reading_order(boxes, pix.width, 1 if exam['id'].startswith('tax') else 2), boxes=boxes), ensure_ascii=False), encoding='utf-8')
                    print('OCR', exam['id'], condition, page, len(boxes), flush=True)


def page_text(exam_id, condition, page):
    return json.loads((OUT / exam_id / 'ocr' / condition / f'{page}.json').read_text(encoding='utf-8'))['text']


def parse_answers(raw, questions):
    """Final JSON object first; otherwise the stated answer inside each question's own segment."""
    answers = {}
    for candidate in re.findall(r'\{[^{}]*\}', raw):  # the model may emit one object per line; later ones win
        try:
            parsed = json.loads(candidate)
        except ValueError:
            continue
        for q, v in parsed.items() if isinstance(parsed, dict) else ():
            v = CIRCLED.get(str(v).strip(), v)
            if str(q) in questions and str(v) in ('1', '2', '3', '4', '5'):
                answers[str(q)] = int(v)
    if answers:
        return answers, 'json'
    marks = sorted((m.start(), q) for q in questions for m in [re.search(rf'(?<!\d){q}\s*번', raw)] if m)
    answers = {}
    for i, (pos, q) in enumerate(marks):
        segment = raw[pos:marks[i + 1][0] if i + 1 < len(marks) else len(raw)]
        m = re.search(r'정답[^0-9①-⑤\n]{0,15}([1-5①-⑤])', segment)
        if m:
            answers[q] = int(CIRCLED.get(m.group(1), m.group(1)))
    return answers, 'segment' if answers else 'none'


def llm():
    # CUDA builds of llama-cpp-python need the pip-installed NVIDIA runtime DLLs on the search path.
    for site in map(Path, sys.path):
        for folder in (site / 'nvidia').glob('*/bin') if (site / 'nvidia').is_dir() else ():
            os.add_dll_directory(str(folder)); os.environ['PATH'] = str(folder) + os.pathsep + os.environ['PATH']
    import llama_cpp
    if not llama_cpp.llama_supports_gpu_offload():
        raise RuntimeError('This llama-cpp-python build has no GPU offload')
    model = llama_cpp.Llama(model_path=str(GGUF), n_gpu_layers=-1, n_ctx=N_CTX, seed=42, verbose=False)
    for exam in load_plan():
        for condition in ('textlayer',) + CONDITIONS:
            for batch in exam['batches']:
                cache = OUT / exam['id'] / 'llm' / condition / f"{batch['id']}.json"
                if cache.exists():
                    continue
                cache.parent.mkdir(parents=True, exist_ok=True)
                qs = batch['questions']
                text = '\n\n'.join(page_text(exam['id'], condition, p) for p in batch['context'])
                prompt = (f"아래는 시험지 {len(batch['context'])}쪽을 문자 인식(OCR)으로 읽은 텍스트입니다.\n\n----- 시험지 텍스트 시작 -----\n"
                          + text + '\n----- 시험지 텍스트 끝 -----\n\n'
                          + ', '.join(qs) + '번 문제를 풀어 주세요. 문제와 선택지를 다시 적지 말고, 문제마다 "' + qs[0]
                          + '번: 정답 N - 이유 한 문장" 형식으로 한 줄씩만 쓰세요(N은 고른 선택지 번호 1~5). 마지막 줄에는 {"' + qs[0]
                          + '": N} 과 같은 형태의 JSON 하나로 모든 문제의 정답 번호를 정리해 주세요.')
                # The example deliberately shows no concrete choice number: a literal "3" anchored the model's answers.
                record = dict(condition=condition, exam=exam['id'], batch=batch['id'], questions=qs, context_pages=batch['context'])
                try:
                    response = model.create_chat_completion([dict(role='user', content=prompt)], temperature=0, seed=42, max_tokens=MAX_NEW_TOKENS)
                    raw = response['choices'][0]['message']['content'] or ''
                    answers, parser = parse_answers(raw, qs)
                    record.update(answers=answers, parser=parser, prompt_tokens=response['usage']['prompt_tokens'],
                                  output_tokens=response['usage']['completion_tokens'], finish_reason=response['choices'][0]['finish_reason'],
                                  error=None, raw=raw)
                except ValueError as exc:  # prompt longer than the context window: no fabricated answer
                    record.update(answers={}, parser='none', prompt_tokens=None, output_tokens=0, finish_reason=None,
                                  error='context-overflow: ' + str(exc)[:200], raw='')
                cache.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding='utf-8')
                print('LLM', exam['id'], condition, batch['id'], record['answers'], record['finish_reason'], record['error'] or '', flush=True)


def summarize():
    report = dict(model=MODEL, ocr='EasyOCR ko+en', dpi=DPI, n_ctx=N_CTX, max_new_tokens=MAX_NEW_TOKENS, exams={}, questions=[])
    grand = {c: collections.Counter() for c in ('textlayer',) + CONDITIONS}
    for exam in load_plan():
        correct = collections.defaultdict(dict); follows = collections.defaultdict(dict); result = dict(conditions={}, ocr_quality={})
        # Levels 4 and 5 print "the answer is N" bait with a seeded random N; count how often each condition answers N.
        from decoy_lines import bait_number
        for condition in ('textlayer',) + CONDITIONS:
            stats = collections.Counter(correct=0, total=0, answered=0, batches=0, truncated_batches=0, context_overflow_batches=0, answers_equal_bait=0)
            for batch in exam['batches']:
                record = json.loads((OUT / exam['id'] / 'llm' / condition / f"{batch['id']}.json").read_text(encoding='utf-8'))
                stats['batches'] += 1
                stats['truncated_batches'] += record['finish_reason'] == 'length'; stats['context_overflow_batches'] += bool(record['error'])
                for q in batch['questions']:
                    answer = record['answers'].get(q); ok = answer in batch['answers'][q]
                    correct[condition][(batch['section'], q)] = ok
                    bait = bait_number(exam['id'], f"{batch['page']}-{q}")  # same seed as decoy_watermark.py
                    follows[condition][(batch['section'], q)] = (bait, bait in batch['answers'][q], answer == bait and bait is not None)
                    stats['total'] += 1; stats['answered'] += answer is not None; stats['correct'] += ok
                    stats['answers_equal_bait'] += answer == bait and bait is not None
            grand[condition].update(stats)
            result['conditions'][condition] = dict(stats, accuracy=round(100 * stats['correct'] / stats['total'], 2))
        for condition in CONDITIONS:
            hit = total = extra = 0
            for page in exam['pages']:
                truth = collections.Counter(WORD.findall(page_text(exam['id'], 'textlayer', page)))
                seen = collections.Counter(WORD.findall(page_text(exam['id'], condition, page)))
                hit += sum(min(n, seen[w]) for w, n in truth.items()); total += sum(truth.values()); extra += sum((seen - truth).values())
            result['ocr_quality'][condition] = dict(word_recall=round(100 * hit / total, 2), words_not_in_original=extra)
        for condition in CONDITIONS[1:]:
            lost = sum(correct['original'][k] and not correct[condition][k] for k in correct['original'])
            gained = sum(not correct['original'][k] and correct[condition][k] for k in correct['original'])
            result['conditions'][condition]['vs_original'] = dict(correct_to_wrong=lost, wrong_to_correct=gained)
            grand[condition].update(correct_to_wrong=lost, wrong_to_correct=gained)
        report['exams'][exam['id']] = result
        for (section, q) in correct['original']:
            bait, bait_correct, _ = follows['original'][(section, q)]
            report['questions'].append(dict(exam=exam['id'], section=section, question=q, **{c: int(correct[c][(section, q)]) for c in correct},
                                            bait=bait, bait_is_correct=int(bait_correct),
                                            **{c + '_equals_bait': int(follows[c][(section, q)][2]) for c in correct}))
    report['total'] = {c: dict(s, accuracy=round(100 * s['correct'] / s['total'], 2)) for c, s in grand.items()}
    (OUT / 'scores.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({k: v for k, v in report.items() if k != 'questions'}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('stage', choices=['prepare', 'ocr', 'llm', 'summarize'])
    {'prepare': prepare, 'ocr': ocr, 'llm': llm, 'summarize': summarize}[parser.parse_args().stage]()
