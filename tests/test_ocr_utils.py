import unittest

from ocr_utils import merge_consensus, normalize_nickname, parse_int, parse_name_scores


class OCRUtilsTest(unittest.TestCase):
    def test_parse_name_scores(self):
        text = "홍길동 1234 Kim1 7777 noise"
        rows = parse_name_scores(text)
        self.assertEqual(rows[0]["name"], "홍길동")
        self.assertEqual(rows[0]["score"], 1234)
        self.assertEqual(rows[1]["name"], "Kim1")

    def test_normalize_nickname(self):
        self.assertEqual(normalize_nickname("R0saura"), "rosaura")
        self.assertEqual(normalize_nickname("K.cc윈드"), "kcc윈드")

    def test_parse_int(self):
        self.assertEqual(parse_int("71,457"), 71457)
        self.assertEqual(parse_int("O0O"), 0)

    def test_merge_consensus_median(self):
        merged = merge_consensus(
            [
                {"member_id": 1, "score": 1000, "source_image_id": 10},
                {"member_id": 1, "score": 900, "source_image_id": 11},
                {"member_id": 2, "score": 800, "source_image_id": 12},
            ]
        )
        by_member = {row["member_id"]: row for row in merged}
        self.assertEqual(by_member[1]["score"], 950)
        self.assertEqual(by_member[1]["confirmed"], 0)
        self.assertEqual(by_member[2]["confirmed"], 1)


if __name__ == "__main__":
    unittest.main()
