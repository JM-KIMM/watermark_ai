"""Apply new captions/math strips to saved PDFs, then evaluate changed inputs only."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # repository root
import json
from pathlib import Path
import shutil
import pymupdf as fitz
import corpus_evaluation as ce
from watermark import border,font_path,is_math_exam,MATH_FORMULAS,QR_DIRECTIVE
from question_marks import occupied_rects,attach_qr_label
from line_patterns import apply_line_patterns


def main(prepare_only=False):
    old=ce.OUT;old_assets=ce.ASSETS
    inventory=json.loads((old/'inventory.json').read_text(encoding='utf-8'))
    ce.OUT=ce.ROOT/'outputs/corpus_evaluation_v6';ce.ASSETS=ce.ROOT/'outputs/corpus_inputs_v6'
    ce.OUT.mkdir(exist_ok=True);ce.ASSETS.mkdir(exist_ok=True)
    # Keep the completed pre-caption benchmark separately for auditability.
    docs=ce.ROOT/'docs/evaluation'
    for p in list(docs.glob('corpus_*.json')):
        target=p.with_name('baseline_'+p.name)
        if not target.exists():shutil.copy2(p,target)
    previous=ce.ROOT/'docs/CORPUS_RESULTS_2026-11-16.md'
    baseline=ce.ROOT/'docs/CORPUS_BASELINE_2026-11-16.md'
    if previous.exists() and not baseline.exists():
        baseline.write_text(previous.read_text(encoding='utf-8').replace('evaluation/corpus_','evaluation/baseline_corpus_'),encoding='utf-8')
    font=font_path(None)
    for exam in inventory:
        if exam['status']!='included':continue
        math=is_math_exam(exam['source']);dest=ce.ASSETS/exam['id'];dest.mkdir(exist_ok=True)
        with fitz.open(ce.ROOT/exam['source']) as original:
            for level in (2,3):
                target=dest/f'level{level}.pdf';manifest=target.with_suffix('.manifest.json')
                if target.exists() and manifest.exists():continue
                meta=json.loads((old_assets/exam['id']/f'level{level}.manifest.json').read_text(encoding='utf-8'))
                with fitz.open(old_assets/exam['id']/f'level{level}.pdf') as doc:
                    for i,p in enumerate(doc):
                        record=meta['pages'][i];band=meta['border_pt'];source=original[i]
                        if math:
                            w,h=p.rect.width,p.rect.height
                            for r in [fitz.Rect(0,0,w,band),fitz.Rect(0,h-band,w,h),fitz.Rect(0,band,band,h-band),fitz.Rect(w-band,band,w,h-band)]:
                                p.draw_rect(r,color=None,fill=(1,1,1),overlay=True)
                            a=QR_DIRECTIVE+' | '+MATH_FORMULAS[i%2];b=QR_DIRECTIVE+' | '+MATH_FORMULAS[(i+1)%2]
                            record['typography']=border(p,a,font,meta['font_size_pt'],meta['opacity'],band,jitter=meta['size_jitter'],seed=meta['seed']+i,paired_text=b)
                            record.update(payload=a,mode='math-formula',summary_source_page=None)
                            if level==3:record['line_patterns']=apply_line_patterns(source,p,band=band,payload=a)
                        occupied=occupied_rects(source)+[fitz.Rect(m['qr_source_bbox']) for m in record['question_marks'] if m['qr_status']=='placed']
                        for mark in record['question_marks']:
                            if mark['qr_status']=='placed':mark.update(attach_qr_label(p,fitz.Rect(mark['qr_source_bbox']),source.rect,occupied,band=band,fontfile=font))
                    doc.save(target,garbage=4,deflate=True)
                meta.update(output=str(target),math_watermark=math,qr_captions=True,font_mode='file' if math else meta['font_mode'],feature_version='math-formulas-qr-caption-v1',
                            derivation='Incremental caption/math border update of preserved benchmark PDF; source body unchanged')
                manifest.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
                print('ENHANCED',exam['id'],level,flush=True)
        with fitz.open(dest/'level2.pdf') as a,fitz.open(dest/'level3.pdf') as b:
            exam['identical_stage_pages']=[i+1 for i in range(len(a)) if a[i].get_pixmap(dpi=150).tobytes('png')==b[i].get_pixmap(dpi=150).tobytes('png')]
        for section in exam['sections']:
            directory=ce.OUT/exam['id']/section['id'];directory.mkdir(parents=True,exist_ok=True)
            for page in section['pages']:
                cached=directory/f'original-{page}.json'
                if not cached.exists():
                    record=json.loads((old/exam['id']/section['id']/cached.name).read_text(encoding='utf-8'))
                    record['reused_original_from']='corpus_evaluation_v5: identical source images, prompt and model settings'
                    cached.write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    (ce.OUT/'inventory.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2),encoding='utf-8')
    if prepare_only:return
    ce.run(inventory)
    path=ce.OUT/'protocol.json';protocol=json.loads(path.read_text(encoding='utf-8'))
    protocol.update(version=6,features='math-only formula watermark and adjacent QR caption',qr_size=36,
                    original_condition='Reused v5 original responses for identical source input/prompt/settings',
                    structured_output_policy=dict(primary='integer-enum schema',fallback='string-enum schema on attempt 3',max_attempts=3,failed_answer=None),
                    generation='Incremental public helper enhance_corpus.py; base bodies preserved')
    path.write_text(json.dumps(protocol,ensure_ascii=False,indent=2),encoding='utf-8')
    import verify_corpus
    verify_corpus.main()
    import export_corpus_report
    export_corpus_report.main()


if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--prepare-only',action='store_true')
    main(parser.parse_args().prepare_only)
