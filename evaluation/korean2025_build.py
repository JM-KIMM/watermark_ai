# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Build the test conditions for one exam PDF and report what the generator did to it.

usage: korean2025_build.py <repo> <exam.pdf> <work dir>/inputs
"""
import json
import sys
import time
from pathlib import Path

repo, source, out = Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3])
sys.path.insert(0, str(repo))
import pymupdf as fitz  # noqa: E402
from watermark import build  # noqa: E402

out.mkdir(parents=True, exist_ok=True)
SEED = 'korean2025odd'
# Fixed QR placement and no tracking: the QR only logs visits and did not change accuracy.
COMMON = dict(intensity=2, font_mode='source', size_jitter=.25, prompts_file=repo / 'prompts_ko.json',
              question_style='qr', preview=False, decoy_seed=SEED)
CONDITIONS = {
    'border': dict(),                    # measured border only (old level2)
    'frames': dict(decoy='frames'),      # bait on the border and passage frames, unlabelled
    'frames_labelled': dict(decoy='frames', decoy_style='labelled'),  # current web default wording
    'lines': dict(decoy='lines'),        # bait between body lines (measured placement)
    'frames6': dict(decoy='frames', decoy_style='labelled', decoy_number='absent'),  # generator default: choice 6
}
summary = {}
for name, extra in CONDITIONS.items():
    target = out / f'{name}.pdf'
    for stale in (target, target.with_suffix('.manifest.json')):
        stale.unlink(missing_ok=True)
    begin = time.monotonic()
    report = build(source, target, **COMMON, **extra)
    pages = report['pages']
    summary[name] = dict(
        seconds=round(time.monotonic() - begin, 1),
        qr=sum(m['qr_status'] == 'placed' for p in pages for m in p['question_marks']),
        qr_skipped=sum(m['qr_status'] != 'placed' for p in pages for m in p['question_marks']),
        decoy_lines=sum(len(p['decoy_lines']) for p in pages),
        frames=[(p['page'], [(b['open_side'] or 'closed', b['source_questions']) for b in p['passage_boxes']])
                for p in pages if p['passage_boxes']],
        preserved=[(p['page'], e['reason'], [round(v) for v in e['bbox']]) for p in pages
                   for e in p['passage_box_audit'] if e['status'] == 'preserved'],
        unrenderable=sorted({c for p in pages for c in p['typography'].get('unrenderable', [])}),
    )
    print(name, json.dumps({k: v for k, v in summary[name].items() if k not in ('frames', 'preserved')}, ensure_ascii=False), flush=True)
(out / 'build_summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=1), encoding='utf8')
print('\nframes replaced (frames condition):')
for page, boxes in summary['frames']['frames']:
    print('  page', page, boxes)
print('\nframes left alone:')
for page, reason, bbox in summary['frames']['preserved']:
    print('  page', page, reason, bbox)
with fitz.open(out / 'frames.pdf') as doc:
    for number in (2, 5, 6, 8):
        doc[number - 1].get_pixmap(dpi=90).save(out / f'frames_page{number}.png')
