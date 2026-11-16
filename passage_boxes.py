# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Replace text passage frames, preserving their contents and interrupted titles."""
import pymupdf as fitz


def text_highlight(drawings, words):
    """Recognize a single small boxed word inside an otherwise textual passage."""
    if not drawings:
        return True
    rect = fitz.Rect(drawings[0]['rect'])
    for d in drawings[1:]:
        rect |= d['rect']+(-.01,-.01,.01,.01)
    if not (8 <= rect.height <= 22 and 10 <= rect.width <= 80):
        return False
    if not any((rect+(-1.5,-1.5,1.5,1.5)).contains(w) for w in words):
        return False
    sides = set()
    for d in drawings:
        for item in d['items']:
            if item[0] == 're':
                if max(abs(item[1][k]-rect[k]) for k in range(4)) < 1:
                    sides.update(('left','right','top','bottom'))
            elif item[0] == 'l':
                a,b = item[1:3]
                if abs(a.x-b.x)<.25 and abs(abs(a.y-b.y)-rect.height)<1:
                    if abs(a.x-rect.x0)<1: sides.add('left')
                    if abs(a.x-rect.x1)<1: sides.add('right')
                elif abs(a.y-b.y)<.25 and abs(abs(a.x-b.x)-rect.width)<1:
                    if abs(a.y-rect.y0)<1: sides.add('top')
                    if abs(a.y-rect.y1)<1: sides.add('bottom')
                else:
                    return False
            else:
                return False
    return len(sides)==4


def passage_frames(page):
    segments = []
    drawings = page.get_drawings()
    for drawing in drawings:
        color = drawing.get('color')
        if (not color or max(color) > .3 or drawing.get('fill') is not None
                or float(drawing.get('width') or .5) > 1.5):
            continue
        for item in drawing['items']:
            lines = []
            if item[0] == 'l':
                lines = [(item[1], item[2])]
            elif item[0] == 're':
                r = fitz.Rect(item[1])
                lines = [(r.tl, r.tr), (r.bl, r.br), (r.tl, r.bl), (r.tr, r.br)]
            for a, b in lines:
                if abs(a.x-b.x) > .25 and abs(a.y-b.y) > .25:
                    continue
                r = fitz.Rect(min(a.x,b.x), min(a.y,b.y), max(a.x,b.x), max(a.y,b.y))
                if max(r.width,r.height) >= 2 and not any(
                        max(abs(r[k]-s[k]) for k in range(4)) < .5 for s in segments):
                    segments.append(r)
    # Some PDF exporters split a passage's sides at every text line.
    merged = []
    for is_vertical in (False, True):
        axis, start, end = (0,1,3) if is_vertical else (1,0,2)
        group = sorted([r for r in segments if (r.width < .25) == is_vertical],
                       key=lambda r:(round(r[axis],1),r[start]))
        for r in group:
            previous = next((s for s in reversed(merged)
                             if (s.width < .25) == is_vertical
                             and abs(s[axis]-r[axis]) < .5
                             and r[start] <= s[end]+.6 and r[end] >= s[start]-.6), None)
            if previous is None:
                merged.append(fitz.Rect(r))
            else:
                previous[start] = min(previous[start],r[start])
                previous[end] = max(previous[end],r[end])
    segments = merged
    vertical = [r for r in segments if r.width < .25 and r.height >= 30]
    horizontal = [r for r in segments if r.height < .25]
    words = [fitz.Rect(w[:4]) for w in page.get_text('words')]
    images = [fitz.Rect(i['bbox']) for i in page.get_image_info()]
    found = []
    for left in vertical:
        for right in vertical:
            width = right.x0-left.x0
            if not 100 <= width <= page.rect.width*.7:
                continue
            if abs(left.y0-right.y0) > 1 or abs(left.y1-right.y1) > 1:
                continue
            box = fitz.Rect(left.x0,left.y0,right.x0,left.y1)
            edges = [left, right]
            for y in (box.y0,box.y1):
                parts = [r for r in horizontal if abs(r.y0-y) < 1
                         and r.x0 >= box.x0-1 and r.x1 <= box.x1+1]
                coverage = sum(r.width for r in parts)
                if coverage < width*.65 or coverage > width*1.05:
                    break
                edges.extend(parts)
            else:
                inner = box+(4,4,-4,-4)
                if sum(inner.contains(w) for w in words) < 3 or any(inner.intersects(i) for i in images):
                    continue
                # Tables, graphs and nested diagrams keep their original frames.
                interior_drawings = [d for d in drawings if inner.intersects(d['rect']+(-.3,-.3,.3,.3))
                       if not any(max(abs(d['rect'][k]-e[k]) for k in range(4)) < 1 for e in edges)
                       and not (len(d['items']) == 1 and d['items'][0][0] == 're'
                                and max(abs(d['rect'][k]-box[k]) for k in range(4)) < 1)]
                if not text_highlight(interior_drawings,words):
                    continue
                # A title such as <보기> interrupts the top rule. Leave enough
                # clearance at those internal endpoints for its glyph bounds.
                safe_edges = []
                for edge in edges:
                    e = fitz.Rect(edge)
                    if e.height < .25:
                        for w in words:
                            if (e+(-3.5,-3.5,3.5,3.5)).intersects(w):
                                if e.x0 > box.x0+2 and w.x0 < e.x0+4:
                                    e.x0 = max(e.x0,w.x1+4)
                                elif e.x1 < box.x1-2 and w.x1 > e.x1-4:
                                    e.x1 = min(e.x1,w.x0-4)
                    if max(e.width,e.height) < 12:
                        break
                    safe_edges.append(e)
                if len(safe_edges) != len(edges):
                    continue
                strips = [e+(-3.5,-3.5,3.5,3.5) for e in safe_edges]
                if (not all(page.rect.contains(s) for s in strips)
                        or any(s.intersects(w) for s in strips for w in words)
                        or any(s.intersects(i) for s in strips for i in images)):
                    continue
                if not any(box.intersects(f['box']) for f in found):
                    found.append(dict(box=box,edges=safe_edges))
    return found


def apply_passage_boxes(source, target, *, band, payload, fontfile):
    from watermark import fill_line
    font = fitz.Font(fontfile=str(fontfile))
    target.insert_font(fontname='passagewm', fontfile=str(fontfile))
    records = []
    for frame in passage_frames(source):
        regions = []
        for edge in frame['edges']:
            dst = edge+(band,band,band,band)
            strip = dst+(-3.5,-3.5,3.5,3.5)
            target.draw_rect(strip,color=None,fill=(1,1,1))
            vertical = dst.height > dst.width
            length = max(dst.width,dst.height)-2
            unit = payload+' | '
            text = fill_line(unit,font,5,length)
            if not text:
                continue
            point = (dst.x0+1.7,dst.y1-1) if vertical else (dst.x0+1,dst.y0+1.7)
            target.insert_text(point,text,fontname='passagewm',fontsize=5,
                               color=(0,0,0),rotate=90 if vertical else 0)
            regions.append(list(strip))
        records.append(dict(source_bbox=list(frame['box']),output_regions=regions,
                            style='black-watermark-text-frame',payload=payload))
    return records
