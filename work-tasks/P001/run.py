"""Reset / score the prototype. Evaluation metadata stays outside the run."""
import argparse
import json
import shutil
import csv
from decimal import Decimal, InvalidOperation
from pathlib import Path
from build import ROOT, dump, rows, sha


def reset(destination):
    if destination.exists():
        raise ValueError('Refusing to overwrite an existing run; choose a new --run directory')
    shutil.copytree(ROOT / 'package/workspace_init', destination)
    (destination / 'outputs').mkdir()


def verify(run):
    package = ROOT / 'package'
    manifest = json.loads((package / 'manifest.json').read_text())
    oracle = json.loads((package / 'evaluation/oracle.json').read_text())
    checks = {'input_integrity': all((run / f).is_file() and not (run / f).is_symlink()
              and sha(run / f) == h for f, h in manifest['input_sha256'].items())}
    errors = []
    try:
        actual = rows(run / 'outputs/comparison.csv')
        checks['comparison_schema'] = bool(actual) and set(actual[0]) == {
            'supplier_id', 'total_cost_cny', 'on_time_pct', 'defect_pct', 'eligible'}
        by_id = {r['supplier_id']: r for r in actual}
        checks['supplier_coverage'] = len(actual) == 3 and set(by_id) == {'A', 'B', 'C'}
        for expected in oracle['rows']:
            sid = expected['supplier_id']
            for field in ('total_cost_cny', 'on_time_pct', 'defect_pct'):
                value = Decimal(by_id.get(sid, {}).get(field, 'NaN'))
                tolerance = Decimal('0.01') if field == 'total_cost_cny' else Decimal('0')
                checks[f'{sid}.{field}'] = value.is_finite() and abs(value - Decimal(expected[field])) <= tolerance
            checks[f'{sid}.eligible'] = by_id.get(sid, {}).get('eligible') == expected['eligible']
    except (OSError, ValueError, KeyError, TypeError, InvalidOperation, csv.Error) as exc:
        checks['comparison_readable'] = False
        errors.append(str(exc))
    try:
        decision = json.loads((run / 'outputs/decision.json').read_text())
        checks['recommendation'] = decision['recommended_supplier'] == oracle['recommended_supplier']
        checks['evidence_references'] = decision['evidence'] == {
            'quotes': 'quotes.csv', 'policy': 'purchase_policy.json', 'performance': 'supplier_performance.png'}
    except (OSError, ValueError, KeyError, TypeError) as exc:
        checks['decision_readable'] = False
        errors.append(str(exc))
    memo = run / 'outputs/recommendation.md'
    try:
        checks['memo_present'] = memo.is_file() and bool(memo.read_text(encoding='utf-8').strip())
    except (OSError, UnicodeError) as exc:
        checks['memo_present'] = False
        errors.append(str(exc))
    return {'automated_checks_passed': all(checks.values()), 'checks': checks, 'errors': errors,
            'human_review': 'pending: memo factuality, rationale and citation entailment',
            'training_admitted': False,
            'limitations': 'End-state integrity only; not an execution trace or proof of model vision.'}


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['reset', 'verify'])
    parser.add_argument('--run', required=True, type=Path)
    args = parser.parse_args()
    if args.action == 'reset':
        reset(args.run)
    else:
        report = verify(args.run)
        dump(args.run / 'grade.json', report)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        raise SystemExit(0 if report['automated_checks_passed'] else 1)
