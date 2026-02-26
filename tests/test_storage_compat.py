import unittest

from storage import Storage, StorageError


class StorageCompatTest(unittest.TestCase):
    def test_list_recent_batches_fallback_without_processed_count(self):
        st = Storage()
        st.use_rest = True

        calls = {"n": 0}

        def fake_select(table, select="*", **kwargs):
            calls["n"] += 1
            if calls["n"] == 1:
                raise StorageError("column processed_count does not exist")
            return [{"id": 1, "week_key": "2026-02-19", "uploaded_count": 3, "status": "processing", "created_at": "now"}]

        st._rest_select = fake_select
        rows = st.list_recent_batches(limit=20)
        self.assertEqual(rows[0]["processed_count"], 0)


if __name__ == "__main__":
    unittest.main()
