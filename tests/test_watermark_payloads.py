from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
import pymupdf as fitz
from watermark import build,font_path
from watermark_payloads import extract_source,make_payload,compact,NON_SOLVING_COMMAND


def sample(path,pages=2):
    doc=fitz.open()
    for n in range(pages):
        p=doc.new_page();p.insert_font(fontname='ko',fontfile=str(font_path(None)))
        p.insert_text((50,100),f'{n+1}. 다음 보기 중 하나를 선택하시오.',fontname='ko',fontsize=11)
        p.draw_rect(fitz.Rect(50,130,500,200))
        p.insert_text((65,155),'이것은 원본 지문이며 내용은 보존되어야 합니다.',fontname='ko',fontsize=11)
        for i in range(5):p.insert_text((60,240+i*30),f'{chr(0x2460+i)} 원문 보기 {n+1}-{i+1} x² + {i+1}',fontname='ko',fontsize=11)
    doc.save(path);doc.close()


class PayloadTests(unittest.TestCase):
    def test_private_math_character_reuses_original_visible_glyph(self):
        from watermark_payloads import MissingGlyphs
        doc=fitz.open();p=doc.new_page();p.insert_text((50,100),'1')
        font=p.get_fonts()[0][0];xref=doc.get_new_xref()
        doc.update_object(xref,'<<>>')
        doc.update_stream(xref,b'/CIDInit /ProcSet findresource begin 12 dict begin begincmap /CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def /CMapName /TestUnicode def /CMapType 2 def 1 begincodespacerange <00> <FF> endcodespacerange 1 beginbfchar <31> <E034> endbfchar endcmap CMapName currentdict /CMap defineresource pop end end')
        doc.xref_set_key(font,'ToUnicode',f'{xref} 0 R')
        p=doc.reload_page(p)
        self.assertIn('\ue034',p.get_text())
        glyphs=MissingGlyphs(doc,font_path(None))
        self.assertIsNotNone(glyphs.get('\ue034',0))
        doc.close()
    def test_source_only_five_options_and_no_generated_math(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'수학.pdf';sample(source)
            with fitz.open(source) as d:
                items=extract_source(d)
                self.assertTrue(all(q['complete'] and len(q['choices'])==5 for p in items for q in p))
                for p in items:
                    for q in p:
                        for c in q['choices']:
                            text=compact(d[c['source_page']-1].get_text(clip=fitz.Rect(c['source_bbox']),sort=True))
                            self.assertIn(c['text'],text)
                payload=make_payload('current-choices',items[0])
                self.assertTrue(payload.startswith(NON_SOLVING_COMMAND))
                self.assertNotIn('두 번 검토',payload)
                for i in range(5):self.assertIn(chr(0x2460+i),payload)
            report=build(source,root/'out.pdf',intensity=2,qr_placement='question-end',payload_policy='current-choices',replace_passage_boxes=True,preview=False)
            self.assertTrue(report['math_source_only']);self.assertFalse(report['math_watermark'])
            self.assertEqual(report['summary_method'],'source-verbatim-no-summary')
            self.assertNotIn('sin²θ + cos²θ',report['pages'][0]['payload'])
            self.assertEqual(report['pages'][0]['passage_boxes'][0]['source_questions'],['1'])

    def test_right_end_labelled_assertions(self):
        doc=fitz.open();p=doc.new_page();p.insert_font(fontname='ko',fontfile=str(font_path(None)))
        p.insert_text((50,100),'1. 적절하지 않은 설명을 고르시오.',fontname='ko')
        for i in range(5):
            p.insert_text((80,160+i*35),f'∙ 원문 주장 {i+1} ........................................',fontname='ko')
            p.insert_text((480,160+i*35),chr(0x2460+i),fontname='ko')
        items=extract_source(doc)
        self.assertTrue(items[0][0]['complete'])
        self.assertEqual(items[0][0]['layout'],'right-labelled-assertions')
        for c in items[0][0]['choices']:self.assertTrue(c['text'].endswith(chr(0x245f+c['number'])))
        doc.close()
