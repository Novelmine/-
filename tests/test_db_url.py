import unittest

from db import _normalize_database_url


class DBUrlNormalizeTest(unittest.TestCase):
    def test_strip_quotes_and_spaces(self):
        raw = '  "postgresql://u:p@db.example.com:6543/postgres?sslmode=require"  '
        self.assertEqual(
            _normalize_database_url(raw),
            'postgresql://u:p@db.example.com:6543/postgres?sslmode=require',
        )

    def test_unwrap_bracketed_hostname(self):
        raw = 'postgresql://u:p@[db.hewavzpynhozjtwwgfxg.supabase.co]:5432/postgres?sslmode=require'
        self.assertEqual(
            _normalize_database_url(raw),
            'postgresql://u:p@db.hewavzpynhozjtwwgfxg.supabase.co:5432/postgres?sslmode=require',
        )


if __name__ == '__main__':
    unittest.main()
