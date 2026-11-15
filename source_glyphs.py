# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 JM-KIMM and contributors.
"""Reuse visible source glyphs when subset/Type3 fonts cannot be embedded by name."""
from collections import Counter
from io import BytesIO

from PIL import Image

import pymupdf as fitz


class SourceGlyphs:
    def __init__(self, document):
        self.document = document
        self.entries = {}
        self.preferred = {}
        self.displaylists = {}
        self.cache = {}
        for index, page in enumerate(document):
            spans = [s for b in page.get_text("rawdict")["blocks"]
                     for line in b.get("lines", []) if tuple(line["dir"]) == (1., 0.)
                     for s in line["spans"]]
            counts = Counter()
            for s in spans:
                counts[s["font"]] += sum(c["c"].isalnum() for c in s["chars"])
            primary = counts.most_common(1)[0][0] if counts else None
            self.preferred[index] = primary
            for span in spans:
                if span["font"] != primary or span["size"] <= 0:
                    continue
                for char in span["chars"]:
                    c = char["c"]
                    if c.isspace() or len(c) != 1 or not c.isprintable():
                        continue
                    box = fitz.Rect(char["bbox"])
                    if box.is_empty or not page.rect.contains(box):
                        continue
                    self.entries.setdefault(c, []).append((index, tuple(box), span["size"], char["origin"]))

    def get(self, char, page_index, opacity=1):
        candidates = self.entries.get(char)
        if not candidates:
            return None
        entry = next((e for e in candidates if e[0] == page_index), candidates[0])
        index, box, size, origin = entry
        key = (index, box, opacity)
        if key not in self.cache:
            if index not in self.displaylists:
                self.displaylists[index] = self.document[index].get_displaylist()
            display = self.displaylists[index]
            pix = display.get_pixmap(matrix=fitz.Matrix(6, 6), clip=fitz.Rect(box), alpha=True)
            image = Image.open(BytesIO(pix.tobytes("png"))).convert("RGBA")
            image.putalpha(image.getchannel("A").point(lambda value: round(value*opacity)))
            # Flatten on the white border to avoid changing body transparency rendering.
            background = Image.new("RGBA", image.size, (255, 255, 255, 255))
            image = Image.alpha_composite(background, image).convert("RGB")
            data = BytesIO()
            image.save(data, format="PNG")
            r = fitz.Rect(box)
            self.cache[key] = dict(image=data.getvalue(), advance=r.width/size,
                                   left=(r.x0-origin[0])/size, top=(r.y0-origin[1])/size,
                                   width=r.width/size, height=r.height/size,
                                   source_page=index+1)
        return self.cache[key]
