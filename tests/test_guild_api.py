import os
import unittest
from unittest.mock import patch

from guild_api import GuildAPIError, _get_base_urls, fetch_guild_id, fetch_guild_members


class GuildApiTest(unittest.TestCase):
    @patch("guild_api._get_json")
    def test_fetch_guild_id_missing_raises(self, mock_get_json):
        mock_get_json.return_value = {}
        with self.assertRaises(GuildAPIError):
            fetch_guild_id("k", "엘리시움", "설아")

    @patch("guild_api._get_json")
    def test_fetch_guild_members_reads_list(self, mock_get_json):
        mock_get_json.side_effect = [{"oguild_id": "gid"}, {"guild_member": ["A", "B"]}]
        members = fetch_guild_members("k", "엘리시움", "설아")
        self.assertEqual(members, ["A", "B"])

    def test_base_url_override(self):
        os.environ["NEXON_OPENAPI_BASE_URL"] = "https://custom.example.com/maplestory/v1/"
        try:
            urls = _get_base_urls()
            self.assertEqual(urls, ["https://custom.example.com/maplestory/v1"])
        finally:
            os.environ.pop("NEXON_OPENAPI_BASE_URL", None)


if __name__ == "__main__":
    unittest.main()
