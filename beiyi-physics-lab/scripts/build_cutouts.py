"""Create vector A4 cut sheets for B5 pasting from a PDF and explicit crop boxes."""
import argparse
from copy import copy
import io
import json
import math
import os
from pathlib import Path

from pypdf import PdfReader, PdfWriter, Transformation
from pypdf.generic import RectangleObject
from reportlab.lib import colors
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

MM = 72 / 25.4
W, H = 210 * MM, 297 * MM
MARGIN, TOP, BOTTOM = 14 * MM, 25 * MM, 14 * MM
PAD, GAP, CAPTION = 2 * MM, 3 * MM, 17


def font_path(explicit=None):
    if explicit:
        path = Path(explicit).expanduser()
        if not path.is_file():
            raise ValueError(f"Font not found: {path}")
        return path
    windir = Path(os.environ.get("WINDIR", "C:/Windows"))
    candidates = [windir / "Fonts/simsun.ttc", windir / "Fonts/simhei.ttf",
                  Path("/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"),
                  Path("/Library/Fonts/Arial Unicode.ttf")]
    for path in candidates:
        if path.is_file():
            return path
    raise ValueError("No Chinese TrueType font found; specify --font and --bold-font.")


def register_fonts(regular=None, bold=None):
    a, b = font_path(regular), font_path(bold or regular)
    for name, path in [("CutRegular", a), ("CutBold", b)]:
        font = TTFont(name, str(path), subfontIndex=0)
        required = "物理实验图表裁剪稿实际大小单面打印原稿已缩放沿虚线适配"
        missing = [ch for ch in required if ord(ch) not in font.face.charToGlyph]
        if missing:
            raise ValueError(f"Font lacks Chinese glyphs: {path}")
        pdfmetrics.registerFont(font)


def prepare(reader, manifest, scale=.86, max_width_mm=153):
    if not math.isfinite(scale) or not 0 < scale <= 1:
        raise ValueError("Scale must be finite, greater than zero and at most 1.")
    if not math.isfinite(max_width_mm) or not 20 <= max_width_mm <= 160:
        raise ValueError("Content width must be between 20 and 160 mm.")
    raw = manifest.get("items")
    if not isinstance(raw, list) or not raw:
        raise ValueError("Manifest must have a non-empty items list.")
    seen, cards = set(), []
    for item in raw:
        key = item.get("id")
        if not isinstance(key, str) or not key.strip() or key in seen:
            raise ValueError("Each cutout needs a unique non-empty string id.")
        seen.add(key)
        page = item.get("page")
        if type(page) is not int or not 1 <= page <= len(reader.pages):
            raise ValueError(f"Invalid 1-based page number for {key}")
        src = reader.pages[page - 1]
        if src.rotation:
            raise ValueError("Normalize page rotation before measuring crop boxes.")
        if abs(float(src.mediabox.left)) > .01 or abs(float(src.mediabox.bottom)) > .01:
            raise ValueError("Normalize source MediaBox origin to (0, 0) first.")
        sw, sh = float(src.mediabox.width), float(src.mediabox.height)
        box = item.get("bbox")
        if not isinstance(box, list) or len(box) != 4:
            raise ValueError(f"bbox must contain four numbers for {key}")
        if any(type(n) not in (int, float) or not math.isfinite(n) for n in box):
            raise ValueError(f"bbox must contain finite numbers for {key}")
        left, top, right, bottom = box
        if not 0 <= left < right <= sw or not 0 <= top < bottom <= sh:
            raise ValueError(f"Crop is outside its source page: {key}")
        caption = item.get("caption", "")
        if not isinstance(caption, str):
            raise ValueError("caption must be a string")
        ratio = min(scale, max_width_mm * MM / (right - left))
        dw, dh = (right - left) * ratio, (bottom - top) * ratio
        fw, fh = dw + 2 * PAD, dh + 2 * PAD + (CAPTION if caption else 0)
        if fw > W - 2 * MARGIN or fh > H - TOP - BOTTOM:
            raise ValueError(f"Cutout cannot fit intact; revise its scale/layout: {key}")
        cards.append(dict(id=key, source_page=page, bbox=box, source_height=sh,
                          scale=ratio, content_width=dw, content_height=dh,
                          width=fw, height=fh, caption=caption))
    return cards


def arrange(cards):
    rows, row, used = [], [], 0
    available = W - 2 * MARGIN
    for card in cards:
        addition = card["width"] + (GAP if row else 0)
        if row and used + addition > available:
            rows.append(row)
            row, used = [], 0
        row.append(card)
        used += card["width"] + (GAP if len(row) > 1 else 0)
    if row:
        rows.append(row)
    placed, page, top = [], 1, TOP
    for row in rows:
        rh = max(card["height"] for card in row)
        if top + rh > H - BOTTOM:
            page += 1
            top = TOP
        x = (W - sum(c["width"] for c in row) - GAP * (len(row) - 1)) / 2
        for card in row:
            placed.append(dict(card, output_page=page, x=x, top=top))
            x += card["width"] + GAP
        top += rh + GAP
    for i, card in enumerate(placed):
        assert card["x"] >= MARGIN - .01
        assert card["top"] + card["height"] <= H - BOTTOM + .01
        for prior in placed[:i]:
            if prior["output_page"] != card["output_page"]:
                continue
            overlap_x = min(prior["x"] + prior["width"], card["x"] + card["width"]) - max(prior["x"], card["x"])
            overlap_y = min(prior["top"] + prior["height"], card["top"] + card["height"]) - max(prior["top"], card["top"])
            assert not (overlap_x > .01 and overlap_y > .01), "Cut frames overlap"
    return placed


def overlay(cards, number, count, scale):
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setFillColor(colors.HexColor("#202c35"))
    c.setFont("CutBold", 14)
    c.drawString(MARGIN, H - 29, "物理实验 · 图表打印裁剪稿")
    c.setFont("CutRegular", 9)
    c.drawString(MARGIN, H - 46, f"A4单面，实际大小/100%；已按原稿{scale:.0%}或更小比例缩放，沿虚线裁剪贴入B5纸。")
    c.setStrokeColor(colors.HexColor("#9ca4aa"))
    c.setDash(3, 3)
    c.setLineWidth(.4)
    for q in cards:
        c.rect(q["x"], H - q["top"] - q["height"], q["width"], q["height"], stroke=1, fill=0)
        if q["caption"]:
            if pdfmetrics.stringWidth(q["caption"], "CutBold", 10) > q["content_width"]:
                raise ValueError(f"Caption too wide: {q['id']}")
            c.setFont("CutBold", 10)
            c.drawString(q["x"] + PAD, H - q["top"] - PAD - 10, q["caption"])
    c.setFont("CutRegular", 8)
    c.drawString(MARGIN, 22, "每侧2 mm留边；图表已缩放，无需再次按B5缩印。")
    c.drawRightString(W - MARGIN, 22, f"{number} / {count}")
    c.save()
    buf.seek(0)
    return PdfReader(buf)


def build(source, manifest, output, scale=.86, max_width_mm=153,
          regular_font=None, bold_font=None, layout_json=None):
    source, output = Path(source), Path(output)
    if source.resolve() == output.resolve():
        raise ValueError("Output must not overwrite the source report.")
    reader = PdfReader(source)
    cards = arrange(prepare(reader, manifest, scale, max_width_mm))
    register_fonts(regular_font, bold_font)
    count = max(q["output_page"] for q in cards)
    writer = PdfWriter()
    for number in range(1, count + 1):
        out = writer.add_blank_page(W, H)
        group = [q for q in cards if q["output_page"] == number]
        for q in group:
            left, top, right, bottom = q["bbox"]
            sh, ratio = q["source_height"], q["scale"]
            src = copy(reader.pages[q["source_page"] - 1])
            src.cropbox = RectangleObject((left, sh - bottom, right, sh - top))
            src.trimbox = RectangleObject(src.cropbox)
            target_x = q["x"] + PAD
            target_y = H - q["top"] - PAD - (CAPTION if q["caption"] else 0) - q["content_height"]
            out.merge_transformed_page(src, Transformation((ratio, 0, 0, ratio,
                                         target_x - ratio * left, target_y - ratio * (sh - bottom))), expand=False)
        out.merge_page(overlay(group, number, count, scale).pages[0])
        out.compress_content_streams()
    writer.add_metadata({"/Title": "北医物理学实验 图表打印裁剪稿 - B5适配",
                         "/Subject": "A4实际大小100%打印；裁剪贴入B5实验报告纸"})
    output.parent.mkdir(parents=True, exist_ok=True)
    writer.write(output)
    assert len(PdfReader(output).pages) == count
    layout = {"pages": count, "items": cards, "max_content_width_mm": max(q["content_width"] for q in cards) / MM}
    if layout_json:
        target = Path(layout_json)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(layout, ensure_ascii=False, indent=2), encoding="utf-8")
    return layout


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--scale", type=float, default=.86)
    parser.add_argument("--max-content-width-mm", type=float, default=153)
    parser.add_argument("--font")
    parser.add_argument("--bold-font")
    parser.add_argument("--layout-json", type=Path)
    args = parser.parse_args()
    manifest = json.loads(args.manifest.read_text(encoding="utf-8-sig"))
    try:
        layout = build(args.source, manifest, args.output, args.scale,
                       args.max_content_width_mm, args.font, args.bold_font, args.layout_json)
    except ValueError as exc:
        parser.error(str(exc))
    print(f"Created {layout['pages']} A4 pages; {len(layout['items'])} complete cutouts.")


if __name__ == "__main__":
    main()
