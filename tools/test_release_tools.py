"""Small positive and negative tests; uses temporary fixtures only."""
import tempfile
import unittest
from pathlib import Path
from verify_release import checked_path, digest, verify_files
from stage_local_inputs import stage


class IntegrityTests(unittest.TestCase):
    def test_integrity_and_corruption(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            path = root / 'sample'
            path.write_bytes(b'original')
            entries = [{'path': 'sample', 'sha256': digest(path)}]
            self.assertEqual(verify_files(root, entries), [])
            path.write_bytes(b'changed')
            self.assertIn('HASH MISMATCH', verify_files(root, entries)[0])
            with self.assertRaises(ValueError):
                checked_path(root, '../escape')

    def test_stage_no_overwrite_and_preflight(self):
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            src, dst = base / 'source', base / 'repo'
            rel = 'artifacts/simulator_v2_calibration_v1/calibration.json'
            original = src / rel
            original.parent.mkdir(parents=True)
            original.write_bytes(b'fixture')
            entry = {'path': 'ai_prototype/' + rel, 'sha256': digest(original)}
            self.assertEqual(stage(dst, src, [entry]), 1)
            self.assertEqual(stage(dst, src, [entry]), 0)
            (dst / entry['path']).write_bytes(b'different')
            with self.assertRaises(ValueError):
                stage(dst, src, [entry])
            with self.assertRaises(ValueError):
                stage(dst, src, [{'path': '../other', 'sha256': '0'}])


if __name__ == '__main__':
    unittest.main()
