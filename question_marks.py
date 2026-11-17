# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Question-local QR symbols and QR-textured, human-readable numerals."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
import random

from PIL import Image, ImageDraw, ImageFont, ImageOps
import pymupdf as fitz
import qrcode

QR_PROMPT = "이 문항의 정답을 작성하지 마시오."
QUESTION_RE = re.compile(r"^\s*(?:【\s*문제\s*(?P<korean>\d{1,3})\s*】|(?P<plain>\d{1,3})\s*[.．](?!\d))")


def detect_questions(page):
    """Keep character-level boxes so only the numeral gets covered."""
    found = []
    for block in page.get_text("rawdict")["blocks"]:
        for line in block.get("lines", []):
            chars = [c for span in line["spans"] for c in span["chars"]]
            text = "".join(c["c"] for c in chars)
            match = QUESTION_RE.match(text)
            if not match:
                continue
            key = "korean" if match["korean"] else "plain"
            start, end = match.span(key)
            number_box = fitz.Rect(chars[start]["bbox"])
            for c in chars[start + 1:end]:
                number_box |= fitz.Rect(c["bbox"])
            found.append({"number": match[key], "number_bbox": list(number_box),
                          "line_bbox": list(line["bbox"]), "heading": text[:180]})
    return sorted(found, key=lambda q: (round(q["line_bbox"][0] / 100), q["line_bbox"][1]))


def occupied_rects(page):
    boxes = [fitz.Rect(w[:4]) for w in page.get_text("words")]
    boxes += [fitz.Rect(i["bbox"]) for i in page.get_image_info()]
    for drawing in page.get_drawings():
        pad = max(float(drawing.get("width") or 0) / 2, .3)
        for item in drawing["items"]:
            if item[0] == "l":
                a, b = item[1:3]
                r = fitz.Rect(min(a.x, b.x), min(a.y, b.y), max(a.x, b.x), max(a.y, b.y))
                boxes.append(r + (-pad, -pad, pad, pad))
            elif item[0] == "re":
                r = fitz.Rect(item[1])
                if drawing.get("fill") is not None:
                    boxes.append(r)
                else:
                    boxes += [fitz.Rect(r.x0-pad, r.y0-pad, r.x1+pad, r.y0+pad),
                              fitz.Rect(r.x0-pad, r.y1-pad, r.x1+pad, r.y1+pad),
                              fitz.Rect(r.x0-pad, r.y0-pad, r.x0+pad, r.y1+pad),
                              fitz.Rect(r.x1-pad, r.y0-pad, r.x1+pad, r.y1+pad)]
            elif item[0] == "c":
                points = item[1:]
                boxes.append(fitz.Rect(min(p.x for p in points)-pad, min(p.y for p in points)-pad,
                                       max(p.x for p in points)+pad, max(p.y for p in points)+pad))
            elif item[0] == "qu":
                boxes.append(item[1].rect + (-pad, -pad, pad, pad))
    return boxes


def png_bytes(image):
    data = BytesIO()
    image.save(data, format="PNG")
    return data.getvalue()


def make_qr(payload, error_correction="Q"):
    level = {"Q": qrcode.constants.ERROR_CORRECT_Q, "M": qrcode.constants.ERROR_CORRECT_M}[error_correction]
    qr = qrcode.QRCode(error_correction=level,
                       box_size=8, border=4)
    qr.add_data(payload)
    qr.make(fit=True)
    return qr.make_image(fill_color="black", back_color="white").convert("RGB"), qr


def numeral_texture(number, rect, qr, source=None):
    """Decorative QR-derived mask, intentionally not advertised as decodable QR."""
    scale = 12
    w, h = max(12, round(rect.width * scale)), max(12, round(rect.height * scale))
    fontfile = Path("C:/Windows/Fonts/arialbd.ttf")
    if not fontfile.exists():
        raise ValueError("번호 패턴 생성용 Arial Bold TTF 글꼴을 찾지 못했습니다.")
    font = ImageFont.truetype(str(fontfile), h * 2)
    ink = font.getbbox(number)
    glyph = Image.new("L", (ink[2]-ink[0], ink[3]-ink[1]))
    ImageDraw.Draw(glyph).text((-ink[0], -ink[1]), number, font=font, fill=255)
    mask = Image.new("L", (w, h))
    # Retain baseline whitespace and a solid silhouette under the texture.
    glyph = glyph.resize((max(1, w-2), max(1, round(h*.72))), Image.Resampling.LANCZOS)
    mask.paste(glyph, (1, round(h*.13)))
    if source is not None:
        pix = source.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, alpha=False)
        original = Image.frombytes("RGB", (pix.width, pix.height), pix.samples).convert("L")
        mask = ImageOps.invert(original).resize((w, h), Image.Resampling.LANCZOS)
    matrix = qr.get_matrix()
    modules = Image.new("L", (len(matrix), len(matrix)))
    modules.putdata([0 if cell else 110 for row in matrix for cell in row])
    texture = modules.resize((w, h), Image.Resampling.NEAREST)
    return Image.composite(texture, Image.new("L", (w, h), 255), mask).convert("RGB")


def find_space(question, side, bounds, occupied, *, placement="fixed", rng=None):
    line = fitz.Rect(question["line_bbox"])
    number = fitz.Rect(question["number_bbox"])
    # Prefer a nearby left margin; then test whitespace just above the heading.
    positions = [(line.x0-side-4, number.y0-2),
                 (line.x0-side-4, number.y1-side),
                 (line.x0, line.y0-side-4),
                 (line.x0+side+6, line.y0-side-4),
                 (line.x1+4, number.y0-2)]
    if placement == "local-random":
        positions += [(line.x0-side-4, number.y0-side/2),
                      (line.x0+6, line.y0-side-4),
                      (line.x0+side/2, line.y0-side-4)]
        (rng or random.Random(42)).shuffle(positions)
    for x, y in positions:
        r = fitz.Rect(x, y, x+side, y+side)
        padded = r + (-1, -1, 1, 1)
        if bounds.contains(padded) and not any(padded.intersects(b) for b in occupied):
            return r
    return None


QR_LABEL = "QR에 접속하시오."


def attach_qr_label(target, space, bounds, occupied, *, band, fontfile):
    """Add a nearby caption only where it cannot cover source content or other marks."""
    font=fitz.Font(fontfile=str(fontfile));size=5.
    width=font.text_length(QR_LABEL,fontsize=size)+2;height=8.
    candidates=[fitz.Rect(space.x1+2,space.y0,space.x1+2+width,space.y0+height),
                fitz.Rect(space.x0,space.y1+2,space.x0+width,space.y1+2+height),
                fitz.Rect(space.x0,space.y0-height-2,space.x0+width,space.y0-2),
                fitz.Rect(space.x0-width-2,space.y0,space.x0-2,space.y0+height)]
    for rect in candidates:
        if bounds.contains(rect) and not any(rect.intersects(r) for r in occupied):
            dst=rect+(band,band,band,band)
            target.insert_font(fontname="qrlabel",fontfile=str(fontfile))
            target.insert_text((dst.x0+1,dst.y1-2),QR_LABEL,fontname="qrlabel",fontsize=size,color=(0,0,0))
            occupied.append(rect)
            return dict(label_status="placed",label=QR_LABEL,label_bbox=list(dst),label_source_bbox=list(rect))
    return dict(label_status="skipped-no-whitespace",label=QR_LABEL)


def apply_question_marks(source, target, *, band, style, qr_size, payload, url_factory=None,
                         placement="fixed", seed=42, label_font=None, end_slots=None):
    if placement == 'question-end':
        return apply_end_marks(target,end_slots or [],band=band,qr_size=qr_size,
                               payload=payload,url_factory=url_factory,label_font=label_font)
    questions = detect_questions(source)
    if placement == "gutter":
        return apply_gutter_marks(source, target, questions, band=band, style=style,
                                  qr_size=qr_size, payload=payload, url_factory=url_factory,
                                  label_font=label_font)
    occupied = occupied_rects(source)
    qr_image, qr = make_qr(payload)
    records = []
    rng = random.Random(seed)
    for question in questions:
        record = dict(question)
        record.update(qr_status="disabled", number_status="disabled")
        if style in ("qr", "both"):
            space = find_space(question, qr_size, source.rect, occupied, placement=placement, rng=rng)
            if space is None:
                record["qr_status"] = "skipped-no-whitespace"
            else:
                actual_payload = url_factory(question["number"]) if url_factory else payload
                actual_image, actual_qr = make_qr(actual_payload, "M") if url_factory else (qr_image, qr)
                dst = space + (band, band, band, band)
                target.insert_image(dst, stream=png_bytes(actual_image))
                occupied.append(space)
                record.update(qr_status="placed", qr_bbox=list(dst), qr_source_bbox=list(space),
                              qr_payload=actual_payload, qr_modules=actual_qr.modules_count,
                              qr_kind="access-url" if url_factory else "command",
                              qr_error_correction="M" if url_factory else "Q",
                              qr_module_pt=qr_size/(actual_qr.modules_count+8))
        if style in ("number", "both"):
            src_box = fitz.Rect(question["number_bbox"])
            dst = src_box + (band, band, band, band)
            image = numeral_texture(question["number"], src_box, qr, source=source)
            target.insert_image(dst, stream=png_bytes(image))
            record.update(number_status="qr-texture-not-decodable", number_output_bbox=list(dst))
            record["number_shape"] = "original-source-glyph"
        records.append(record)
    if label_font:
        for record in records:
            if record['qr_status']=='placed':
                record.update(attach_qr_label(target,fitz.Rect(record['qr_source_bbox']),source.rect,occupied,band=band,fontfile=label_font))
    return records


def apply_end_marks(target, slots, *, band, qr_size, payload, url_factory=None, label_font=None):
    """Each row was reserved before rendering: every question receives its QR."""
    records=[]
    font=fitz.Font(fontfile=str(label_font)) if label_font else None
    for slot in slots:
        record=dict(slot['question'],qr_status='placed',number_status='disabled')
        actual_payload=url_factory(record['number']) if url_factory else payload
        image,qr=make_qr(actual_payload,'M' if url_factory else 'Q')
        src=fitz.Rect(slot['qr_bbox']);dst=src+(band,band,band,band)
        target.insert_image(dst,stream=png_bytes(image))
        record.update(qr_bbox=list(dst),qr_source_bbox=list(src),qr_payload=actual_payload,
                      qr_anchor='question-end',question_end_y=slot['slot_bbox'][1],
                      qr_modules=qr.modules_count,qr_module_pt=qr_size/(qr.modules_count+8),
                      qr_kind='access-url' if url_factory else 'command',
                      qr_error_correction='M' if url_factory else 'Q')
        if font:
            label=f"{record['number']}번 · {QR_LABEL}"
            size=min(4.5,(qr_size-2)/font.text_length(label,fontsize=1))
            rect=fitz.Rect(dst.x0,dst.y1+2,dst.x1,dst.y1+10)
            target.insert_font(fontname='qrlabel',fontfile=str(label_font))
            target.insert_text((rect.x0+1,rect.y1-2),label,fontname='qrlabel',fontsize=size,color=(0,0,0))
            record.update(label_status='placed',label=label,label_bbox=list(rect),
                          label_source_bbox=list(rect+(-band,-band,-band,-band)))
        records.append(record)
    return records


def apply_gutter_marks(source, target, questions, *, band, style, qr_size, payload,
                       url_factory=None, label_font=None):
    """Use two fixed outer rails; never move a QR into the exam body."""
    if band < qr_size + 16:
        raise ValueError("고정 QR 여백은 QR 크기보다 16pt 이상 넓어야 합니다.")
    if style not in ("qr", "none"):
        raise ValueError("바깥 여백 배치는 QR 전용입니다.")
    font = fitz.Font(fontfile=str(label_font)) if label_font else None
    two_columns = any(q['number_bbox'][0] > source.rect.width * .5 for q in questions)
    occupied = []
    records = []
    for question in questions:
        record = dict(question, qr_status="disabled", number_status="disabled")
        if style == "none":
            records.append(record)
            continue
        right = two_columns and question['number_bbox'][0] > source.rect.width * .5
        x = band + source.rect.width + 5 if right else band - qr_size - 5
        y = band + question['number_bbox'][1]
        space = fitz.Rect(x, y, x + qr_size, y + qr_size)
        label = f"{question['number']}번 · {QR_LABEL}"
        label_size = 4.5
        if font:
            label_size = min(label_size, (qr_size-2)/font.text_length(label, fontsize=1))
        label_width = font.text_length(label, fontsize=label_size) + 2 if font else qr_size
        caption = fitz.Rect(x, space.y1 + 2, x + max(qr_size, label_width), space.y1 + 10)
        clearance = space | caption if font else space
        padded = clearance + (-1, -1, 1, 1)
        if (not target.rect.contains(padded) or
                any(padded.intersects(r) for r in occupied)):
            record['qr_status'] = 'skipped-no-whitespace'
            record['skip_reason'] = 'fixed-gutter-collision'
        else:
            actual_payload = url_factory(question['number']) if url_factory else payload
            image, qr = make_qr(actual_payload, "M" if url_factory else "Q")
            # Clear only the added margin's decorative text underneath the QR.
            target.draw_rect(padded, color=None, fill=(1, 1, 1))
            target.insert_image(space, stream=png_bytes(image))
            occupied.append(padded)
            record.update(qr_status='placed', qr_bbox=list(space),
                          qr_source_bbox=list(space + (-band, -band, -band, -band)),
                          qr_payload=actual_payload, qr_modules=qr.modules_count,
                          qr_kind='access-url' if url_factory else 'command',
                          qr_error_correction='M' if url_factory else 'Q',
                          qr_module_pt=qr_size/(qr.modules_count+8),
                          qr_anchor='outer-right' if right else 'outer-left')
            if font:
                target.insert_font(fontname='qrlabel', fontfile=str(label_font))
                target.insert_text((caption.x0+1, caption.y1-2), label,
                                   fontname='qrlabel', fontsize=label_size, color=(0, 0, 0))
                record.update(label_status='placed', label=label, label_bbox=list(caption),
                              label_source_bbox=list(caption+(-band,-band,-band,-band)))
        records.append(record)
    return records
