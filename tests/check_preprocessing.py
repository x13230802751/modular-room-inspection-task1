"""Regression tests for finite-row selection, closed radius and source row identity."""
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from preprocessing import MAP_FILE, row_digest, select_input


class PreprocessingTests(unittest.TestCase):
    def test_closed_ball_duplicates_and_nonfinite_rows(self):
        # Four coincident records and a fifth exactly 20 mm away qualify each other.
        xyz = np.array([[0,0,0], [np.nan,0,0], [0,0,0], [.1,0,0],
                        [0,0,0], [0,0,0], [.020,0,0], [.1201,0,0]])
        saved = xyz.copy()
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            points, record = select_input(xyz, "radius", out)
            expected = np.array([0,2,4,5,6])
            np.testing.assert_array_equal(np.flatnonzero(np.isfinite(points).all(1)), expected)
            np.testing.assert_array_equal(points[expected], saved[expected])
            np.testing.assert_array_equal(xyz, saved)
            with np.load(out / MAP_FILE, allow_pickle=False) as mapping:
                np.testing.assert_array_equal(mapping["source_rows"], expected)
            self.assertEqual(record["source_rows_sha256"], row_digest(expected))
            self.assertEqual((record["input_rows"], record["finite_rows"], record["removed_finite_rows"]), (8,7,2))
            raw, record = select_input(xyz, "raw", out)
            self.assertIs(raw, xyz)
            self.assertEqual(record["removed_finite_rows"], 0)
            with np.load(out / MAP_FILE, allow_pickle=False) as mapping:
                np.testing.assert_array_equal(mapping["source_rows"], [0,2,3,4,5,6,7])

    def test_identity_and_failed_selection(self):
        xyz = np.zeros((5,3))
        with TemporaryDirectory() as tmp:
            out = Path(tmp)
            for method in ("raw", "radius"):
                _, record = select_input(xyz, method, out)
                self.assertIsNone(record["source_rows_file"])
                self.assertFalse((out / MAP_FILE).exists())
            with self.assertRaisesRegex(ValueError, "all finite"):
                select_input(np.arange(15.).reshape(5,3), "radius", out)
            with self.assertRaisesRegex(ValueError, "at least five"):
                select_input(xyz[:4], "radius", out)
            with self.assertRaisesRegex(ValueError, "Unknown preprocessing"):
                select_input(xyz, "p2p", out)


if __name__ == "__main__":
    unittest.main()
