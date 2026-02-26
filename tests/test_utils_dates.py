import unittest

from utils_dates import compute_previous_week_thursday_key


class UtilsDatesTest(unittest.TestCase):
    def test_previous_week_thursday_from_wednesday(self):
        self.assertEqual(compute_previous_week_thursday_key("2026-02-25"), "2026-02-19")

    def test_previous_week_thursday_from_thursday(self):
        self.assertEqual(compute_previous_week_thursday_key("2026-02-26"), "2026-02-19")


if __name__ == "__main__":
    unittest.main()
