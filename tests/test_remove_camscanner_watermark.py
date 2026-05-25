import importlib.util
import pathlib
import unittest


SCRIPT = (
    pathlib.Path(__file__).resolve().parents[1]
    / "skills"
    / "remove-camscanner-watermark"
    / "scripts"
    / "remove_camscanner_watermark.py"
)
SPEC = importlib.util.spec_from_file_location("remove_camscanner_watermark", SCRIPT)
remove_camscanner_watermark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(remove_camscanner_watermark)


class WatermarkBlockTests(unittest.TestCase):
    def test_finds_small_corner_image_block_but_keeps_page_image(self):
        operations = [
            ([], b"q"),
            ([1, 0, 0, 1, 511.5, 10], b"cm"),
            ([73.4, 0, 0, 25, 0, 0], b"cm"),
            (["/X1"], b"Do"),
            ([], b"Q"),
            ([], b"q"),
            ([1, 0, 0, 1, 23.4, 45], b"cm"),
            ([548, 0, 0, 797, 0, 0], b"cm"),
            (["/X2"], b"Do"),
            ([], b"Q"),
        ]
        images = {
            "/X1": {"width": 238, "height": 81},
            "/X2": {"width": 2063, "height": 3000},
        }

        blocks = remove_camscanner_watermark.find_watermark_blocks(
            operations, images, page_width=595, page_height=842
        )

        self.assertEqual([block["object"] for block in blocks], ["/X1"])

    def test_rejects_large_scan_image_even_if_named_x1(self):
        operations = [
            ([], b"q"),
            ([1, 0, 0, 1, 20, 20], b"cm"),
            ([550, 0, 0, 790, 0, 0], b"cm"),
            (["/X1"], b"Do"),
            ([], b"Q"),
        ]
        images = {"/X1": {"width": 1800, "height": 2600}}

        blocks = remove_camscanner_watermark.find_watermark_blocks(
            operations, images, page_width=595, page_height=842
        )

        self.assertEqual(blocks, [])


if __name__ == "__main__":
    unittest.main()
