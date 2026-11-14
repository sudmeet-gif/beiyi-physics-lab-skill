import hashlib
import importlib.util
import tempfile
from pathlib import Path
import unittest

from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("cutouts", ROOT / "beiyi-physics-lab/scripts/build_cutouts.py")
cut = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cut)


class CutoutTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source.pdf"
        c = canvas.Canvas(str(self.source), pagesize=(cut.W, cut.H))
        c.rect(40, 80, 510, 500)
        c.drawString(45, 570, "Synthetic table: no personal or course data")
        c.showPage()
        c.setPageSize((500, 700))
        c.rect(40, 80, 420, 520)
        c.drawString(45, 585, "Non-A4 source page")
        c.save()

    def test_vector_export_preserves_source_and_handles_page_sizes(self):
        before = hashlib.sha256(self.source.read_bytes()).digest()
        items = [dict(id="table-a", page=1, bbox=[40, 200, 550, 720]),
                 dict(id="table-b", page=2, bbox=[40, 100, 460, 620])]
        output = self.root / "cutouts.pdf"
        layout = cut.build(self.source, dict(items=items), output)
        self.assertEqual(len(layout["items"]), 2)
        self.assertEqual(layout["items"][1]["source_height"], 700)
        self.assertEqual(layout["pages"], 2)
        self.assertEqual(before, hashlib.sha256(self.source.read_bytes()).digest())
        pdf = PdfReader(output)
        self.assertTrue(all(len(p.images) == 0 for p in pdf.pages))
        self.assertTrue(all(abs(float(p.mediabox.width) - cut.W) < .01 for p in pdf.pages))

    def test_width_cap_and_unique_coverage(self):
        manifest = dict(items=[dict(id=str(i), page=1, bbox=[0, 30, 590, 230]) for i in range(6)])
        cards = cut.prepare(PdfReader(self.source), manifest, max_width_mm=100)
        layout = cut.arrange(cards)
        self.assertEqual({q["id"] for q in layout}, {str(i) for i in range(6)})
        self.assertTrue(all(q["content_width"] / cut.MM <= 100.001 for q in layout))
        self.assertTrue(all(q["scale"] <= .86 for q in layout))

    def test_invalid_selections_and_duplicate_ids_are_rejected(self):
        reader = PdfReader(self.source)
        for box in [[0, 0, 900, 300], [30, 60, 20, 90], [0, 0, float("nan"), 20]]:
            with self.subTest(box=box), self.assertRaises(ValueError):
                cut.prepare(reader, dict(items=[dict(id="a", page=1, bbox=box)]))
        with self.assertRaises(ValueError):
            cut.prepare(reader, dict(items=[dict(id="a", page=1, bbox=[0, 0, 100, 100])] * 2))
        with self.assertRaises(ValueError):
            cut.build(self.source, dict(items=[]), self.source)

    def test_rotation_requires_explicit_normalization(self):
        writer = PdfWriter()
        writer.add_page(PdfReader(self.source).pages[0]).rotate(90)
        rotated = self.root / "rotated.pdf"
        writer.write(rotated)
        with self.assertRaisesRegex(ValueError, "rotation"):
            cut.prepare(PdfReader(rotated), dict(items=[dict(id="a", page=1, bbox=[0, 0, 100, 100])]))


if __name__ == "__main__":
    unittest.main()
