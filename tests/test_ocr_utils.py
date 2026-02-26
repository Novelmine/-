import unittest

from ocr_utils import merge_consensus, normalize_nickname, parse_name_scores


class OCRUtilsTest(unittest.TestCase):
    def test_parse_name_scores(self):
        text = "홍길동 1234\nKim1 7777\nnoise"
        rows = parse_name_scores(text)
        self.assertEqual(rows[0]["name"], "홍길동")
        self.assertEqual(rows[0]["score"], 1234)
        self.assertEqual(rows[1]["name"], "Kim1")

    def test_parse_name_scores_ocr_noise(self):
        text = "설아: 1O,2S0\n로즈 | 8B0\n잘못된줄 abc"
        rows = parse_name_scores(text)
        self.assertEqual(rows, [{"name": "설아", "score": 10250}, {"name": "로즈", "score": 880}])

    def test_normalize_nickname(self):
        self.assertEqual(normalize_nickname("R0saura"), "rosaura")
        self.assertEqual(normalize_nickname("K.cc윈드"), "kcc윈드")

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
