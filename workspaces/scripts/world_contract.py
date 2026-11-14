"""One explicit experimental task family, not a general occupational world generator.

Facts come from a model or test fixture; formulas/serialization are reviewed code.
Nothing from the generated scenario is executed as code.
"""
import csv
from datetime import date
from decimal import Decimal, InvalidOperation
import io
from pathlib import Path

from common import ROOT, require, sha256
from planning_common import schema, validate

VERSION = 'project_cost_schedule_v1'
TABLES = {
    'baseline.csv': ['work_package_id', 'name', 'baseline_start', 'baseline_due',
                     'baseline_budget_usd', 'baseline_effort_hours', 'planned_completed_effort_hours'],
    'actuals.csv': ['work_package_id', 'completed_effort_hours', 'actual_cost_usd', 'actual_finish'],
    'remaining_estimates.csv': ['work_package_id', 'estimated_remaining_hours', 'hourly_rate_usd',
                              'committed_remaining_nonlabor_usd', 'available_remaining_hours'],
}
METRICS = {
    'cost_variance_to_date_usd': 'actual_cost_usd - baseline_budget_usd; negative is remaining budget, not proof of savings',
    'schedule_effort_gap_hours': 'planned_completed_effort_hours - completed_effort_hours; positive is behind planned effort',
    'forecast_total_cost_usd': 'actual_cost_usd + estimated_remaining_hours * hourly_rate_usd + committed_remaining_nonlabor_usd',
    'forecast_budget_variance_usd': 'forecast_total_cost_usd - baseline_budget_usd; positive is forecast overrun',
    'resource_gap_hours': 'max(0, estimated_remaining_hours - available_remaining_hours)',
}
OUTPUT_COLUMNS = ['work_package_id', 'currency', *METRICS]
SCOPE = ('Monitor the fictional network project at the supplied snapshot. Compare planned and actual '
         'progress and costs, forecast the cost outcome under the stated assumptions, assess budget '
         'and resource allocation, and recommend justified cost-control actions. Do not execute changes.')


def validate_world(world):
    validate(world, schema(ROOT / 'config/world.schema.json'))
    snapshot = date.fromisoformat(world['snapshot_date'])
    ids = [p['work_package_id'] for p in world['work_packages']]
    require(len(ids) == len(set(ids)), 'duplicate_work_package')
    for p in world['work_packages']:
        start, due = map(date.fromisoformat, (p['baseline_start'], p['baseline_due']))
        require(start <= due and start <= snapshot, 'invalid_period')
        total = p['baseline_effort_hours']
        require(p['planned_completed_effort_hours'] <= total and p['completed_effort_hours'] <= total, 'effort_out_of_range')
        if due <= snapshot:
            require(p['planned_completed_effort_hours'] == total, 'due_package_not_fully_planned')
        complete = p['completed_effort_hours'] == total
        require(complete == (p['actual_finish'] is not None), 'completion_date_mismatch')
        if complete:
            require(start <= date.fromisoformat(p['actual_finish']) <= snapshot, 'invalid_actual_finish')
            require(not any(p[k] for k in ('estimated_remaining_hours', 'committed_remaining_nonlabor_usd', 'available_remaining_hours')), 'completed_package_has_remaining_work')
        else:
            require(p['estimated_remaining_hours'] > 0, 'missing_remaining_estimate')
    # CSV cells are data; forbid formula-active strings rather than escaping/changing facts.
    for p in world['work_packages']:
        require(not p['name'].lstrip().startswith(('=', '+', '-', '@')), 'spreadsheet_formula_string')


def csv_bytes(columns, rows):
    out = io.StringIO(newline='')
    writer = csv.DictWriter(out, fieldnames=columns, lineterminator='\n')
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode('utf-8')


def materialize(world):
    validate_world(world)
    # Deliberately independent row orders: downstream calculations must join by ID.
    packages = sorted(world['work_packages'], key=lambda p:p['work_package_id'])
    files = {}
    for j, (name, columns) in enumerate(TABLES.items()):
        order = packages[j:] + packages[:j]
        files['records/' + name] = csv_bytes(columns, [{k:p[k] for k in columns} for p in order])
    files['context/project_brief.md'] = (
        '# Fictional project monitoring case\n\n'
        'All case records and governance rules are synthetic research materials, not real business records.\n\n'
        f"Project: {world['project_name']}\nSnapshot: {world['snapshot_date']}\nCurrency: USD\n\n"
        f"{world['project_brief']}\n\nReview scope: {SCOPE}\n"
    ).encode()
    files['context/monitoring_policy.md'] = (
        '# Fictional internal monitoring policy\n\n' + world['monitoring_policy'] + '\n\n'
        'This is a simplified experimental policy, not real law or a claimed industry standard.\n'
        'All three tables belong to the project and snapshot in project_brief.md; join them by work_package_id. '
        'Blank actual_finish means not completed at the snapshot. Dates are calendar dates. '
        'planned_completed_effort_hours and completed_effort_hours measure baseline-equivalent work, '
        'not actual labor consumed. baseline_budget_usd is the approved total budget per work package. '
        'actual_cost_usd includes all incurred expenses through the snapshot, including incurred unpaid items. '
        'Remaining commitments are future nonlabor only: exclude incurred expenses and future labor. '
        'Remaining labor hours and rates are project-manager estimates, not known future outcomes. '
        'Forecasts assume these estimates and rates remain applicable; no additional taxes, overhead or currency conversions. '
        'Available remaining hours refer to the same package-specific resource pool and planning horizon as estimated remaining hours. '
        'Do not assume spare resources can transfer between packages without approval.\n\n'
        'Calculate these per-work-package metrics (USD for *_usd, hours for *_hours):\n' +
        '\n'.join(f'- {k}: {v}' for k,v in METRICS.items()) + '\n\n'
        'Discuss overdue incomplete milestones and early/late completed milestones using baseline_due, '
        'actual_finish and the snapshot. Explain forecast uncertainty, budget/resource pressures and '
        'possible controls. Recommend actions; do not treat a recommendation as already approved.\n'
    ).encode()
    return files


def task_spec(world):
    return {
        'status': 'experimental_draft', 'provenance': 'synthetic',
        'instruction': SCOPE + ' Read workspace_init/context/project_brief.md and monitoring_policy.md. '
                       'Use the three source tables. Produce the following two parts of one project-status deliverable.',
        'deliverables': [
            {'path':'outputs/assessment.csv', 'columns':OUTPUT_COLUMNS,
             'requirements':'One row per source work_package_id, currency USD. Compute every metric using the published policy. Absolute tolerance 0.01 in each stated unit.'},
            {'path':'outputs/report.md', 'requirements':'Explain schedule/milestone and budget status with source references, forecast assumptions, resource/budget allocation and justified cost-control recommendations. Distinguish observed facts, estimates and judgment; follow the fictional approval policy.'},
        ],
        'constraints': ['Preserve input files in the final state. No required tool or execution path.',
                        'The case is fictional. Do not claim real business outcomes or real regulatory compliance.'],
    }


def oracle(world):
    """Private exact numeric reference derived from primitive world facts, not model answers."""
    result = []
    for p in sorted(world['work_packages'], key=lambda p:p['work_package_id']):
        forecast = p['actual_cost_usd'] + p['estimated_remaining_hours'] * p['hourly_rate_usd'] + p['committed_remaining_nonlabor_usd']
        result.append(dict(zip(OUTPUT_COLUMNS, [p['work_package_id'], 'USD',
            p['actual_cost_usd'] - p['baseline_budget_usd'],
            p['planned_completed_effort_hours'] - p['completed_effort_hours'], forecast,
            forecast - p['baseline_budget_usd'], max(0, p['estimated_remaining_hours'] - p['available_remaining_hours'])])))
    return result


def read_table(path):
    with path.open(newline='', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        require(reader.fieldnames and len(reader.fieldnames) == len(set(reader.fieldnames)), 'invalid_csv_header')
        rows = list(reader)
    require(all(None not in r and all(v is not None for v in r.values()) for r in rows), 'invalid_csv_shape')
    return rows


def visible_reference(workspace):
    """Engineering reference only: reads exported inputs, never hidden world/oracle.

    Separate implementation from oracle so serialization/join/sign bugs are observable.
    It is not a model solver and does not write a professional narrative.
    """
    tables = []
    for filename in TABLES:
        rows = read_table(workspace / 'records' / filename)
        byid = {r['work_package_id']: r for r in rows}
        require(len(rows) == len(byid), 'duplicate_source_id')
        tables.append(byid)
    baseline, actual, remaining = tables
    require(set(baseline) == set(actual) == set(remaining), 'source_join_mismatch')
    output = []
    for key in sorted(baseline):
        b,a,r = baseline[key],actual[key],remaining[key]
        budget, spent = Decimal(b['baseline_budget_usd']), Decimal(a['actual_cost_usd'])
        forecast = sum((spent, Decimal(r['hourly_rate_usd']) * Decimal(r['estimated_remaining_hours']), Decimal(r['committed_remaining_nonlabor_usd'])))
        output.append({'work_package_id':key, 'currency':'USD',
            'cost_variance_to_date_usd':spent-budget,
            'schedule_effort_gap_hours':Decimal(b['planned_completed_effort_hours'])-Decimal(a['completed_effort_hours']),
            'forecast_total_cost_usd':forecast, 'forecast_budget_variance_usd':forecast-budget,
            'resource_gap_hours':max(Decimal(0), Decimal(r['estimated_remaining_hours'])-Decimal(r['available_remaining_hours']))})
    return output


def grade_numeric(rows, expected):
    failures = []
    ids = [r.get('work_package_id') for r in rows]
    require(len(ids) == len(set(ids)), 'duplicate_submission_id')
    require(set(ids) == {r['work_package_id'] for r in expected}, 'submission_id_mismatch')
    byid = {r['work_package_id']:r for r in rows}
    for reference in expected:
        row = byid[reference['work_package_id']]
        require(set(row) == set(OUTPUT_COLUMNS), 'submission_columns_mismatch')
        for column in METRICS:
            try:
                value = Decimal(str(row[column]))
                ok = value.is_finite() and abs(value - Decimal(str(reference[column]))) <= Decimal('0.01')
            except (InvalidOperation, ValueError):
                ok = False
            if not ok: failures.append(reference['work_package_id'] + ':' + column)
        if row['currency'] != 'USD': failures.append(reference['work_package_id'] + ':currency')
    return {'passed':not failures, 'failures':failures}


def grade_submission(directory, expected):
    """Never returns a total reward or training admission; narrative remains unevaluated."""
    output = directory / 'outputs'
    require(not output.is_symlink() and not any(p.is_symlink() for p in output.rglob('*')), 'submission_symlink')
    numeric = grade_numeric(read_table(output / 'assessment.csv'), expected)
    report_present = (output / 'report.md').is_file() and bool((output / 'report.md').read_text().strip())
    return {'numeric':numeric, 'report_present':report_present, 'semantic_score':None,
            'overall_pass':None if numeric['passed'] and report_present else False,
            'note':'Report existence is not professional quality. No independent Agent execution or semantic grading.'}


def verify_materialization(workspace, world, expected_hashes):
    require(not workspace.is_symlink() and not any(p.is_symlink() for p in workspace.rglob('*')), 'workspace_symlink')
    actual = {p.relative_to(workspace).as_posix():sha256(p.read_bytes()) for p in workspace.rglob('*') if p.is_file()}
    canonical = {name:sha256(data) for name,data in materialize(world).items()}
    require(actual == expected_hashes == canonical, 'materialization_or_hash_mismatch')
    grade = grade_numeric(visible_reference(workspace), oracle(world))
    require(grade['passed'], 'visible_inputs_disagree_with_world_oracle')
    return grade
