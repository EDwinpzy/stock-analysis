import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_broadsheet
import build_broadsheet
from bs4 import BeautifulSoup


class BroadsheetScreenshotTests(unittest.TestCase):
    def test_broadsheet_template_has_no_remote_font_dependency(self):
        self.assertNotIn("fonts.googleapis.com", build_broadsheet.DOC_TEMPLATE)

    def test_baseline_mode_restores_remote_font_links(self):
        self.assertIn("fonts.googleapis.com", build_broadsheet.REMOTE_FONT_LINKS)
        self.assertIn("Playfair+Display", build_broadsheet.REMOTE_FONT_LINKS)

    def test_broadsheet_uses_the_source_market_data_date(self):
        soup = BeautifulSoup(
            """
            <div class="np-mast-sub">
              <span>2026.11.13 周五</span>
              <span>行情数据日 <b>2026-11-12</b></span>
            </div>
            """,
            "html.parser",
        )

        self.assertEqual(
            build_broadsheet.source_data_date(soup, "2026-11-13"),
            "2026-11-12",
        )

    def test_blank_tail_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="broadsheet-blank-") as temp:
            path = Path(temp) / "blank.png"
            Image.new("RGB", (200, 200), "white").save(path)

            self.assertEqual(verify_broadsheet.tail_ink_ratio(path), 0.0)

    def test_painted_tail_is_detected(self):
        with tempfile.TemporaryDirectory(prefix="broadsheet-ink-") as temp:
            path = Path(temp) / "ink.png"
            image = Image.new("RGB", (200, 200), (248, 244, 235))
            draw = ImageDraw.Draw(image)
            draw.rectangle((20, 185, 180, 195), fill=(20, 20, 20))
            image.save(path)

            self.assertGreater(verify_broadsheet.tail_ink_ratio(path), 0.02)


if __name__ == "__main__":
    unittest.main()
