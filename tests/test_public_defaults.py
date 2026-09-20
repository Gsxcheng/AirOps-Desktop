import tempfile
import unittest
from pathlib import Path

from airops_desktop.db import Database


class PublicDefaultsTests(unittest.TestCase):
    def test_public_seed_contains_only_generic_templates(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "data" / "test.db")
            names = {item["name"] for item in db.list_device_templates()}
            self.assertEqual(names, {"Generic SSH", "Generic Telnet", "Huawei VRP"})

            command_names = {item["name"] for item in db.list_templates()}
            self.assertEqual(
                command_names,
                {
                    "Generic CLI - Example",
                    "Huawei VRP - Read-only Inspection",
                },
            )

    def test_builtin_templates_have_no_credentials(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "data" / "test.db")
            for item in db.list_device_templates():
                self.assertFalse(item["username"])
                self.assertFalse(item["password"])
                self.assertFalse(item["enable_password"])
                self.assertFalse(item["ftp_username"])
                self.assertFalse(item["ftp_password"])


if __name__ == "__main__":
    unittest.main()
