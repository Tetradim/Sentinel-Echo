import os
import pathlib
import sys
import unittest
from unittest.mock import patch


BACKEND_DIR = pathlib.Path(__file__).resolve().parents[1]
PROJECT_ROOT = BACKEND_DIR.parent
sys.path.insert(0, str(BACKEND_DIR))


class DatabasePathTests(unittest.TestCase):
    def test_default_database_path_uses_project_data_store(self):
        from database_paths import default_database_path

        self.assertEqual(
            pathlib.Path(default_database_path()),
            PROJECT_ROOT / "data" / "consolidation.sqlite3",
        )

    def test_database_path_environment_override_wins(self):
        from database_paths import configured_database_path

        with patch.dict(os.environ, {"DATABASE_PATH": "custom.sqlite3"}):
            self.assertEqual(configured_database_path(), "custom.sqlite3")


if __name__ == "__main__":
    unittest.main()
