# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Conservative replacement of isolated layout separators with a QR-derived texture."""
from io import BytesIO
import math

from PIL import Image
import pymupdf as fitz

from question_marks import make_qr


def isolated_rules(page):
    """Ignore rectangles, grids, joined axes, images and rules close to text."""
    lines = []
    for drawing in page.get_drawings():
        items, color = drawing["items"], drawing.get("color")
        if drawing.get("fill") is not None or not color or max(color) > .2:
            continue
        for item in items:
            if item[0] != "l":
                continue
            a, b = item[1:3]
            horizontal = abs(a.y-b.y) < .25
            vertical = abs(a.x-b.x) < .25
            if not (horizontal or vertical):
                continue
            box = fitz.Rect(min(a.x,b.x), min(a.y,b.y), max(a.x,b.x), max(a.y,b.y))
            lines.append(dict(a=a,b=b,box=box,horizontal=horizontal,
                              single=len(items)==1,width=float(drawing.get("width") or .5)))
    blockers = [fitz.Rect(w[:4])+(-2,-2,2,2) for w in page.get_text("words")]
    blockers += [fitz.Rect(i["bbox"])+(-2,-2,2,2) for i in page.get_image_info()]
    result = []
    for index, line in enumerate(lines):
        r = line["box"]
        length = max(r.width,r.height)
        area = r+(-2.1,-2.1,2.1,2.1)
        if not line["single"] or length < 80 or line["width"] > 1.5 or not page.rect.contains(area):
            continue
        if any(area.intersects(b) for b in blockers):
            continue
        connected = False
        for j, other in enumerate(lines):
            if j == index:
                continue
            o = other["box"]
            if area.intersects(o+(-2,-2,2,2)):
                connected=True;break
            if line["horizontal"] == other["horizontal"]:
                distance = abs(r.y0-o.y0) if line["horizontal"] else abs(r.x0-o.x0)
                overlap = min(r.x1,o.x1)-max(r.x0,o.x0) if line["horizontal"] else min(r.y1,o.y1)-max(r.y0,o.y0)
                if distance < 24 and overlap > length*.6:
                    connected=True;break
        if not connected:
            result.append(line)
    return result[:20]


def apply_line_patterns(source, target, *, band, payload):
    _, qr = make_qr(payload[:120])
    matrix = qr.get_matrix()
    records = []
    for index, line in enumerate(isolated_rules(source)):
        box = line["box"]
        length = max(box.width,box.height)
        horizontal = line["horizontal"]
        # This narrow texture is decorative; it is not a scannable QR symbol.
        width = max(1, math.ceil(length*8))
        image = Image.new("L", (width, 16), 255)
        pixels = image.load()
        for x in range(width):
            for y in range(16):
                if matrix[(y//2+index)%len(matrix)][(x//3)%len(matrix)]:
                    pixels[x,y] = 0
        if not horizontal:
            image = image.transpose(Image.Transpose.ROTATE_90)
        buffer = BytesIO();image.save(buffer,format="PNG")
        center_x,center_y=(box.x0+box.x1)/2+band,(box.y0+box.y1)/2+band
        dst = (fitz.Rect(box.x0+band,center_y-1,box.x1+band,center_y+1) if horizontal
               else fitz.Rect(center_x-1,box.y0+band,center_x+1,box.y1+band))
        erase = dst+(-.6,-.6,.6,.6)
        target.draw_rect(erase,color=None,fill=(1,1,1),overlay=True)
        target.insert_image(dst,stream=buffer.getvalue(),keep_proportion=False)
        records.append(dict(source_bbox=list(box),output_bbox=list(erase),style="qr-derived-texture-not-decodable"))
    return records
