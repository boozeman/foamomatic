"""Regression coverage for systemd WorkingDirectory rendering."""
import runpy
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parent.parent
render = runpy.run_path(str(ROOT / "deploy/install_systemd.py"))["render"]

class SystemdTests(unittest.TestCase):
    def test_debian_working_directory_has_no_literal_quotes(self):
        template = (ROOT / "deploy/foamomatic-adapter.service").read_text()
        unit = render(template, "/home/viinatim/git/foamomatic", 1000, 1000)
        line = next(line for line in unit.splitlines() if line.startswith("WorkingDirectory="))
        self.assertEqual(line, "WorkingDirectory=/home/viinatim/git/foamomatic")
        self.assertIn("User=1000", unit)
        self.assertNotIn("@PROJECT_ROOT@", unit)

    def test_specifiers_and_unsupported_paths(self):
        self.assertEqual(render("WorkingDirectory=@PROJECT_ROOT@", "/home/test%/foam", 1, 1),
                         "WorkingDirectory=/home/test%%/foam")
        for path in ("relative/path", "/home/space name/foam", "/home/test\n/foam"):
            with self.assertRaises(ValueError):
                render("@PROJECT_ROOT@", path, 1, 1)

if __name__ == "__main__":
    unittest.main()
