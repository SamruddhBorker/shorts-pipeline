import shutil
import tempfile
import unittest
from pathlib import Path

import pipeline


class SplitTests(unittest.TestCase):
    def test_sentences_become_scenes(self):
        self.assertEqual(pipeline.split_scenes("One. Two! Three?"),
                         ["One.", "Two!", "Three?"])

    def test_long_sentence_splits_at_commas(self):
        s = ("When the legion marches at dawn, every soldier carries forty kilos, "
             "and nobody complains, because the centurion is watching closely.")
        scenes = pipeline.split_scenes(s)
        self.assertGreater(len(scenes), 1)
        self.assertTrue(all(len(x.split()) <= pipeline.MAX_WORDS + 4 for x in scenes))

    def test_empty(self):
        self.assertEqual(pipeline.split_scenes("   "), [])


@unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg not installed")
class EndToEnd(unittest.TestCase):
    def test_builds_a_vertical_video(self):
        with tempfile.TemporaryDirectory() as d:
            script = Path(d) / "s.txt"
            script.write_text("Hello there. This is a tiny test.", encoding="utf-8")
            out = Path(d) / "o.mp4"
            self.assertEqual(pipeline.main([str(script), "-o", str(out)]), 0)
            self.assertTrue(out.exists())
            self.assertGreater(pipeline.duration(out), 1)


if __name__ == "__main__":
    unittest.main()
