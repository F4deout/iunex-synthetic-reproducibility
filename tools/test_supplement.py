"""Check that supplemental archive verification rejects corruption and excluded data."""
import json
import shutil
import tempfile
import unittest
from pathlib import Path
from verify_supplement import inspect


class SupplementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        source = Path(__file__).resolve().parents[1]
        manifests = ['reproducibility/frozen_files.json', 'reproducibility/supplement_v1.1.0.json']
        paths = set(manifests)
        for name in manifests:
            paths.update(e['path'] for e in json.loads((source / name).read_text(encoding='utf-8'))['files'])
        for name in paths:
            target = self.root / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source / name, target)

    def test_valid_archive(self):
        self.assertEqual(inspect(self.root)['status'], 'PASS')

    def test_corruption_rejected(self):
        path = self.root / 'ai_prototype/artifacts/rq1_longitudinal_v2_phase1_corrected/results.json'
        path.write_bytes(path.read_bytes() + b' ')
        with self.assertRaises(AssertionError):
            inspect(self.root)

    def test_excluded_data_rejected(self):
        (self.root / 'ai_prototype/artifacts/v23_survival_time_correction_20260929/predictions.csv').write_text('fixture')
        with self.assertRaises(AssertionError):
            inspect(self.root)


if __name__ == '__main__':
    unittest.main()
