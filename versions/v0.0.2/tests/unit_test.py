import sys
import unittest
from pathlib import Path

# Add src directory to Python path so we can import the package
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import versionsnap


class TestProject(unittest.TestCase):

    def test_version(self):
        self.assertEqual(versionsnap.__version__, "1.0.0")


if __name__ == "__main__":
    unittest.main()
