import sys
import tempfile
import unittest
from pathlib import Path

from PIL import Image, ImageDraw

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))

import verify_broadsheet


class BroadsheetScreenshotTests(unittest.TestCase):
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
