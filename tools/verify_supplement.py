"""Verify the v1.1.0 archived results; never import or execute research models."""
import csv
import hashlib
import json
import math
import statistics
from pathlib import Path
from verify_release import verify_files, digest


def inspect(root):
    supplement = json.loads((root / 'reproducibility/supplement_v1.1.0.json').read_text(encoding='utf-8'))
    errors = verify_files(root, supplement['files'])
    frozen_path = root / 'reproducibility/frozen_files.json'
    assert digest(frozen_path) == supplement['previous_frozen_manifest_sha256']
    frozen = json.loads(frozen_path.read_text(encoding='utf-8'))
    errors += verify_files(root, frozen['files'])
    assert not errors, errors
    for family, names in supplement['excluded'].items():
        for name in names:
            assert not (root / 'ai_prototype/artifacts' / family / name).exists(), f'Excluded file present: {family}/{name}'

    survival = root / 'ai_prototype/artifacts/v23_survival_time_correction_20260929'
    runs = json.loads((survival / 'runs.json').read_text(encoding='utf-8'))
    summary = json.loads((survival / 'summary.json').read_text(encoding='utf-8'))
    assert len(runs) == len(summary) == 360
    assert {r['seed'] for r in runs} == {110, 220, 330, 440, 550}
    assert len({(r['seed'], r['scope'], r['k'], r['step_minutes']) for r in runs}) == 360
    for row in summary:
        selected = [r['metrics'][row['metric']] for r in runs if (r['scope'], r['k'], r['step_minutes']) == (row['scope'], row['k'], row['step_minutes'])]
        assert len(selected) == 5
        assert math.isclose(statistics.mean(selected), row['value']['mean'], abs_tol=1e-12)
    validation = json.loads((survival / 'validation.json').read_text(encoding='utf-8'))
    assert validation['runs'] == 360
    assert all(value != 'FAIL' for value in validation.values())

    history = root / 'ai_prototype/artifacts/rq1_longitudinal_v2_phase1_corrected'
    results = json.loads((history / 'results.json').read_text(encoding='utf-8'))
    assert results['seeds'] == [110, 220, 330, 440, 550]
    assert results['history_lengths'] == [0, 5, 10, 20, 30, 50, 75, 100]
    with (history / 'summary.csv').open(encoding='utf-8-sig', newline='') as stream:
        rows = list(csv.DictReader(stream))
    assert len(rows) == 200
    for row in rows:
        entry = results['summary'][row['target']][row['k']][row['mode']]
        assert math.isclose(float(row['mae_mean']), entry['mae']['mean'], abs_tol=1e-12)
        assert math.isclose(float(row['ci_low']), entry['mae']['ci95'][0], abs_tol=1e-12)
        assert math.isclose(float(row['ci_high']), entry['mae']['ci95'][1], abs_tol=1e-12)
        values = [results['seed_results'][str(seed)][row['target']][row['k']]['models'][row['mode']]['mae'] for seed in results['seeds']]
        assert math.isclose(statistics.mean(values), entry['mae']['mean'], abs_tol=1e-12)
    for field, filename in [('generator_sha256', 'simulator_rq1_longitudinal_v2.py'), ('parameter_sha256', 'RQ1_LONGITUDINAL_V2_FINAL_PARAMETERS.json'), ('validation_amendment_sha256', 'RQ1_LONGITUDINAL_V2_VALIDATION_AMENDMENT_01.md')]:
        assert results[field] == digest(root / 'ai_prototype' / filename)
    # Reject individual observation schemas in files approved as aggregate results.
    forbidden = {'subject_id', 'participant_id', 'person_id', 'session_id', 'source_row', 'timestamp', 'subject', 'session'}
    def aggregate_only(value):
        if isinstance(value, dict):
            assert not forbidden.intersection(value), 'Individual data key in aggregate output'
            for item in value.values():
                aggregate_only(item)
        elif isinstance(value, list):
            for item in value:
                aggregate_only(item)
    for folder in [survival, history]:
        for path in folder.glob('*.json'):
            aggregate_only(json.loads(path.read_text(encoding='utf-8')))
    return {'frozen_v1_files': len(frozen['files']), 'supplement_files': len(supplement['files']), 'survival_runs': len(runs), 'history_summary_rows': len(rows), 'status': 'PASS'}


if __name__ == '__main__':
    print(json.dumps(inspect(Path(__file__).resolve().parents[1]), indent=2))
    print('Archive integrity and stored aggregate consistency only; no experiment rerun.')
