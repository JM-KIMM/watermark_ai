# SPDX-License-Identifier: GPL-3.0-only
"""Reserve a QR row at each question's end without shrinking exam content."""
import re
import pymupdf as fitz
from question_marks import detect_questions

GROUP = re.compile(r'^\s*[\[［【]\s*(\d+)\s*[~～∼–-]\s*\d+')
FOOTER = re.compile(r'^(?:\d{1,3}(?:\s*/\s*\d{1,3})?|20\d{2}.*|.*저작권.*|.*copyright.*)$', re.I)


def plan_page(page, qr_size):
    questions = detect_questions(page)
    w,h = page.rect.width,page.rect.height
    lines = [(fitz.Rect(line['bbox']), ''.join(s['text'] for s in line['spans']))
             for b in page.get_text('dict')['blocks'] for line in b.get('lines',[])]
    footer = min([r.y0-3 for r,t in lines if r.y0>h*.91 and FOOTER.match(t.strip())] or [h])
    # A question heading close to the bottom is content, even if its numeral is isolated.
    footer = max(footer, max((q['number_bbox'][3]+4 for q in questions),default=0))
    divider=any(abs(d['rect'].x0-w/2)<5 and d['rect'].width<3 and d['rect'].height>h*.65
                for d in page.get_drawings())
    columns = [(0,w/2),(w/2,w)] if divider or any(w*.5<=q['number_bbox'][0]<w*.66 for q in questions) else [(0,w)]
    # Indented numbered facts and dates (e.g. "6. 30.") are not exam headings.
    anchored=[]
    for x0,x1 in columns:
        group=[q for q in questions if x0<=q['number_bbox'][0]<x1]
        margin=min((q['number_bbox'][0] for q in group),default=x0)
        anchored.extend(q for q in group if q['number_bbox'][0]<=margin+14)
    questions=anchored
    words = [fitz.Rect(v[:4]) for v in page.get_text('words')]
    images = [fitz.Rect(i['bbox']) for i in page.get_image_info()]
    drawings = [fitz.Rect(d['rect']) for d in page.get_drawings()]
    plans = []
    gap = qr_size+18
    for x0,x1 in columns:
        qs = sorted([q for q in questions if x0<=q['number_bbox'][0]<x1],key=lambda q:q['number_bbox'][1])
        slots = []
        body_right = max([r.x1 for r in words if x0<=r.x0 and r.x1<=x1+.5
                          and qs and qs[0]['number_bbox'][1]<=r.y0<footer] or [x1-16])
        for i,q in enumerate(qs):
            top=q['number_bbox'][1]
            boundary=qs[i+1]['number_bbox'][1]-2 if i+1<len(qs) else footer
            groups=[r.y0-2 for r,t in lines if x0<=r.x0<x1 and top+4<r.y0<boundary
                    and (m:=GROUP.match(t)) and int(m[1])>int(q['number'])]
            boundary=min([boundary]+groups)
            content=[r for r in words+images+drawings if r.x0>=x0-.5 and r.x1<=x1+.5
                     and r.y0>=top-.5 and r.y1<=boundary+.25 and r.height<h*.8]
            bottom=max([r.y1 for r in content] or [q['number_bbox'][3]])
            cut=min(boundary,bottom+3)
            if cut<q['number_bbox'][3]:
                raise ValueError(f"문제 {q['number']} 끝에 안전한 QR 공간을 만들 수 없습니다.")
            # Do not split a word, image or bounded diagram at the insertion cut.
            crossing=[r for r in words+images if r.x0<x1 and r.x1>x0 and r.y0<cut<r.y1]
            if crossing:
                raise ValueError(f"문제 {q['number']} 끝 위치가 본문과 겹칩니다. PDF 구조를 확인하세요.")
            y=cut+len(slots)*gap+4
            x=max(x0+4,min(body_right-qr_size,x1-qr_size-4))
            slots.append(dict(question=q,cut=cut,qr_bbox=[x,y,x+qr_size,y+qr_size],
                              slot_bbox=[x0,cut+len(slots)*gap,x1,cut+(len(slots)+1)*gap]))
        plans.append(dict(x0=x0,x1=x1,slots=slots))
    return dict(original_size=[w,h],footer=footer,gap=gap,columns=plans,
                added_height=max((len(c['slots']) for c in plans),default=0)*gap)


def map_point(point, plan):
    p=fitz.Point(point)
    if p.y>=plan['footer']:
        return fitz.Point(p.x,p.y+plan['added_height'])
    column=next((c for c in plan['columns'] if c['x0']<=p.x<c['x1']),plan['columns'][-1])
    return fitz.Point(p.x,p.y+sum(plan['gap'] for s in column['slots'] if s['cut']<=p.y))


def map_rect(rect, plan):
    r=fitz.Rect(rect)
    return fitz.Rect(map_point(r.tl,plan),map_point(r.br,plan))


def plan_document(doc,qr_size):
    """Move an end row to the next page when the five choices continue there."""
    from watermark_payloads import choices_for
    plans=[plan_page(p,qr_size) for p in doc]
    for i,plan in enumerate(plans):
        for col in plan['columns']:
            for slot in list(col['slots']):
                slot['question'].setdefault('origin_page',i+1)
                extracted=choices_for(doc[i],slot['question'],col,slot['cut'])
                slot['source_choices']=extracted
                if extracted['complete'] or i+1>=len(doc):continue
                # A continued question occupies the first column before its
                # first heading; it must not receive a QR before its choices.
                following=plans[i+1]['columns'][0]
                first=min((s['question']['number_bbox'][1] for s in following['slots']),default=plans[i+1]['footer'])
                prefix=dict(slot['question'],number_bbox=[following['x0'],0,following['x0']+10,10])
                continued=choices_for(doc[i+1],prefix,following,first-2)
                if not continued['complete']:continue
                bottom=max(fitz.Rect(c['source_bbox']).y1 for c in continued['choices'])
                cut=min(first-2,bottom+1)
                marker=fitz.Rect(continued['choices'][0]['source_bbox'])
                q=dict(slot['question'],original_number_bbox=slot['question']['number_bbox'],
                       number_bbox=[marker.x0,marker.y0,marker.x0+10,marker.y0+10],
                       line_bbox=list(marker),continuation=True)
                moved=dict(question=q,cut=cut,source_choices=continued,
                           continued_from=dict(page=i+1,question_bbox=[col['x0'],slot['question']['number_bbox'][1],col['x1'],slot['cut']]))
                following['slots'].append(moved);col['slots'].remove(slot)
    for plan in plans:
        for col in plan['columns']:
            col['slots'].sort(key=lambda s:s['cut'])
            previous=None
            for j,slot in enumerate(col['slots']):
                if previous is not None and slot['cut']<previous:raise ValueError('문제 끝 순서가 올바르지 않습니다.')
                previous=slot['cut']
                x=slot.get('qr_bbox',[col['x1']-qr_size-16])[0]
                y=slot['cut']+j*plan['gap']+4
                slot['qr_bbox']=[x,y,x+qr_size,y+qr_size]
                slot['slot_bbox']=[col['x0'],slot['cut']+j*plan['gap'],col['x1'],slot['cut']+(j+1)*plan['gap']]
        plan['added_height']=max((len(c['slots']) for c in plan['columns']),default=0)*plan['gap']
    return plans


def reserve_question_rows(doc, qr_size, plans=None):
    plans=plans if plans is not None else plan_document(doc,qr_size)
    out=fitz.open()
    try:
        for index,plan in enumerate(plans):
            w,h=plan['original_size'];footer=plan['footer']
            page=out.new_page(width=w,height=h+plan['added_height'])
            for column in plan['columns']:
                previous=0;shift=0
                for slot in column['slots']:
                    cut=slot['cut']
                    clip=fitz.Rect(column['x0'],previous,column['x1'],cut)
                    if clip.height>.01:
                        page.show_pdf_page(clip+(0,shift,0,shift),doc,index,clip=clip)
                    previous=cut;shift+=plan['gap']
                    slot['question']=dict(slot['question'],
                        number_bbox=list(map_rect(slot['question']['number_bbox'],plan)),
                        line_bbox=list(map_rect(slot['question']['line_bbox'],plan)))
                clip=fitz.Rect(column['x0'],previous,column['x1'],footer)
                if clip.height>.01:
                    page.show_pdf_page(clip+(0,shift,0,shift),doc,index,clip=clip)
            if footer<h:
                clip=fitz.Rect(0,footer,w,h)
                page.show_pdf_page(clip+(0,plan['added_height'],0,plan['added_height']),doc,index,clip=clip)
        return out,plans
    except Exception:
        out.close()
        raise
