"""Stage only allowlisted, hash-matching local calibration files; never upload them."""
import argparse
import json
import shutil
from pathlib import Path
from verify_release import checked_path, digest


def stage(root, source, entries):
    pending = []
    for entry in entries:
        relative = entry['path']
        if not relative.startswith('ai_prototype/artifacts/simulator_v2_calibration_v1/'):
            raise ValueError('Input outside the calibration allowlist')
        src = checked_path(source, relative.removeprefix('ai_prototype/'))
        dst = checked_path(root, relative)
        if not src.is_file() or digest(src) != entry['sha256']:
            raise ValueError(f"Source missing or hash mismatch: {relative}")
        if dst.exists() and digest(dst) != entry['sha256']:
            raise ValueError(f"Refusing to overwrite different file: {relative}")
        if not dst.exists():
            pending.append((src, dst))
    for src, dst in pending:
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dst)
    return len(pending)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True, help='Original local ai_prototype directory')
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    entries = json.loads((root / 'reproducibility/local_inputs.json').read_text(encoding='utf-8'))['files']
    print(f"Staged {stage(root, args.source, entries)} hash-matching local files. Raw dataset was not copied.")


if __name__ == '__main__':
    main()
