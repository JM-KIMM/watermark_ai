"""Render short, attributable excerpts from the actual KSAT experiment PDFs."""
import json
from pathlib import Path
import pymupdf as fitz
from external_validity import sha

ROOT = Path(__file__).resolve().parents[1]
RUN = ROOT / 'outputs/ksat_paired_20261118'

def main():
    inputs = json.loads((RUN / 'inputs.json').read_text(encoding='utf8'))
    records = []
    for condition, clip in [('original', (0, 270, 420, 405)),
                            ('product', (0, 290, 440, 425))]:
        source = RUN / 'inputs/math' / (condition + '.pdf')
        capture = inputs['math'][condition]['1']
        assert sha(ROOT / capture['image']) == capture['image_sha256']
        target = ROOT / 'docs/images' / f'ksat_math_{condition}_20261118.png'
        with fitz.open(source) as doc:
            doc[0].get_pixmap(dpi=200, alpha=False, clip=fitz.Rect(clip)).save(target)
        records.append(dict(condition=condition, page=1, clip_points=clip, dpi=200,
                            source_pdf_sha256=sha(source),
                            experiment_image_sha256=capture['image_sha256'],
                            output=str(target.relative_to(ROOT)), output_sha256=sha(target)))
    manifest = dict(source='KICE 2026 CSAT mathematics, odd form, question 1 (excerpt)',
                    upstream='https://github.com/roboco-io/KSAT-AI-Benchmark',
                    description='Actual experiment PDFs rendered as short excerpts; not camera photos or generated mockups.',
                    captures=records)
    (ROOT / 'docs/evaluation/ksat_readme_captures_20261118.json').write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf8')

if __name__ == '__main__':
    main()
