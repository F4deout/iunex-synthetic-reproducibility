"""Verify frozen files without importing research code or running experiments."""
import argparse
import hashlib
import json
from pathlib import Path


def checked_path(root, relative):
    root = Path(root).resolve()
    path = (root / relative).resolve()
    if not path.is_relative_to(root) or Path(relative).is_absolute():
        raise ValueError(f"Unsafe path: {relative}")
    return path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify_files(root, entries):
    errors = []
    for entry in entries:
        path = checked_path(root, entry['path'])
        if not path.is_file():
            errors.append(f"MISSING: {entry['path']}")
        elif digest(path) != entry['sha256']:
            errors.append(f"HASH MISMATCH: {entry['path']}")
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-inputs', action='store_true')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    frozen = json.loads((root / 'reproducibility/frozen_files.json').read_text(encoding='utf-8'))
    errors = verify_files(root, frozen['files'])
    daily = json.loads((root / 'ai_prototype/artifacts/e4_daily_state_20261026/summary.json').read_text(encoding='utf-8'))
    for method, expected in {'full': 0.21543420771273417, 'exact_context_last': 0.34068865740740745, 'history': 0.2915481541974989}.items():
        actual = next(row['mae']['mean'] for row in daily if row['scenario'] == 'BASE' and row['method'] == method)
        if abs(actual - expected) > 1e-12:
            errors.append(f'STORED RESULT MISMATCH: daily-state {method}')
    redflag = json.loads((root / 'ai_prototype/artifacts/redflag_sensor_experiment_20261026/summary.json').read_text(encoding='utf-8'))
    for method, expected in {'HR': 0.4548432471773795, 'THREE': 0.9717608655732654}.items():
        actual = next(row['sensitivity']['mean'] for row in redflag if row['case'] == 'BASE' and row['group'] == 'ALL' and row['method'] == method)
        if abs(actual - expected) > 1e-12:
            errors.append(f'STORED RESULT MISMATCH: redflag {method}')
    python_count = json_count = 0
    for path in root.rglob('*'):
        if not path.is_file() or any(part in {'.git', '.venv', '__pycache__', 'local_inputs', 'work', 'vendor', 'data', 'simulator_v2_calibration_v1'} for part in path.relative_to(root).parts):
            continue
        if path.suffix.lower() in {'.hwp', '.hwpx', '.docx', '.pptx', '.pdf', '.m4a', '.wav', '.pem', '.key'}:
            errors.append(f'EXCLUDED FILE TYPE: {path.relative_to(root)}')
        if path.suffix == '.py':
            compile(path.read_text(encoding='utf-8-sig'), str(path), 'exec')
            python_count += 1
        elif path.suffix == '.json':
            json.loads(path.read_text(encoding='utf-8-sig'))
            json_count += 1
    sums = root / 'SHA256SUMS'
    if sums.exists():
        entries = []
        for line in sums.read_text(encoding='utf-8').splitlines():
            sha, name = line.split('  ', 1)
            entries.append({'path': name, 'sha256': sha})
        errors.extend(verify_files(root, entries))
    if errors:
        print('\n'.join(errors))
        return 1
    print(f"PASS: {len(frozen['files'])} frozen hashes; {python_count} Python syntax; {json_count} JSON files; release checksums checked when present.")
    print('No generation, training, inference or network request performed.')
    if args.check_inputs:
        inputs = json.loads((root / 'reproducibility/local_inputs.json').read_text(encoding='utf-8'))
        missing = verify_files(root, inputs['files'])
        overview = checked_path(root, inputs['pmdata_directory']) / 'participant-overview.xlsx'
        if not overview.is_file():
            missing.append('MISSING: PMData participant-overview.xlsx (raw dataset not bundled)')
        if missing:
            print('\n'.join(missing))
            return 2
        print('PASS: listed local inputs present; this does not certify every historical preservation lock.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
