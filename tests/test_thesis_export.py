"""Synthetic values below are test fixtures, never thesis measurements."""
import importlib.util
import tempfile
import unittest
from pathlib import Path

MODULE = Path(__file__).resolve().parents[1] / "scripts/export-thesis-results.py"
SPEC = importlib.util.spec_from_file_location("thesis_export", MODULE)
exporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(exporter)
HEADER = ",".join(exporter.COLUMNS) + "\n"


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "measurements.csv"
        self.output = Path(self.tmp.name) / "table.tex"

    def test_exports_measurements_and_escapes_latex(self):
        self.source.write_text(HEADER + "test_01,rule & baseline,0.5,0.1,2,30\n", encoding="utf-8")
        exporter.export_table(self.source, self.output)
        result = self.output.read_text(encoding="utf-8")
        self.assertIn(r"test\_01 / rule \& baseline", result)
        self.assertIn("0.500 & 0.100 & 2.00 & 30.00", result)

    def test_rejects_empty_invalid_or_duplicate_measurements_without_overwriting(self):
        invalid = [
            HEADER,
            HEADER + "test,method,nan,0.1,2,30\n",
            HEADER + "test,method,1.1,0.1,2,30\n",
            HEADER + "test,method,0.5,0.1,-2,30\n",
            HEADER + "test,method,0.5,0.1,2\n",
            HEADER + "test,method,0.5,0.1,2,30,extra\n",
            HEADER + "test,method,0.5,0.1,2,30\n" * 2,
            "wrong,columns\n1,2\n",
        ]
        self.output.write_text("previous approved table", encoding="utf-8")
        for content in invalid:
            with self.subTest(content=content):
                self.source.write_text(content, encoding="utf-8")
                with self.assertRaises(ValueError):
                    exporter.export_table(self.source, self.output)
                self.assertEqual(self.output.read_text(), "previous approved table")


if __name__ == "__main__":
    unittest.main()
