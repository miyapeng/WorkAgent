#!/usr/bin/env python3
"""Default Stage 1: official verbatim Raw Work Seeds; historical Task-ID baseline is opt-in."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import re

from build_onet import ROOT, SCHEMA, DataError, parse_csv, insert, encode_csv, json_bytes, sha256
from filter_digital import read_annotations, classify, EXPECTED_SHA256, SOURCE_URL

LABELS = ('digital_candidate', 'physical_required', 'uncertain')
RULE_VERSION = 'conservative-task-rules-v1'
# Deliberately narrow action-object patterns. A generic verb alone is never sufficient.
DIGITAL = {
    'D_SOFTWARE': r'^(?:write|develop|debug|test|modify|maintain) (?:computer |software |application )?(?:programs|code|software|scripts)\b',
    'D_DOCUMENT': r'^(?:prepare|write|compile|edit|revise) (?:financial |statistical |technical |budget |annual |monthly )?(?:reports|budgets|spreadsheets|documents)\b',
    'D_RECORD': r'^(?:enter|update|retrieve|organize) (?:data|records|information) (?:in|into|from|using) (?:a |the )?(?:computer|database|spreadsheet|software)\b',
}
PHYSICAL = {
    'P_DRIVE': r'^(?:drive|pilot) (?:trucks|buses|vehicles|aircraft|airplanes)(?: [^,;]+)?[.]?$',
    'P_CLEAN': r'^(?:clean|wash|disinfect) (?:floors|dishes|windows|rooms|equipment)(?: [^,;]+)?[.]?$',
    'P_HANDLE': r'^(?:lift|carry|load|unload) (?:cargo|freight|materials|packages)(?: [^,;]+)?[.]?$',
}
MIXED = r'\b(?:and|or|including|such as|to|not|without|supervise|coordinate|monitor|plan)\b|[,;]'


def load_catalog(directory):
    """Reuse strict official CSV parsing and PK checking, validate normalized FKs."""
    tables = {name: parse_csv((directory / name).read_bytes(), name, fields) for name, fields in SCHEMA.items()}
    indexes = {}
    for name, records in tables.items():
        idx = {}
        fields = SCHEMA[name]
        for row in records:
            key = (row['task_id'], row['dwa_id']) if name == 'task_dwa.csv' else row[fields[0]]
            insert(idx, key, row, name)
        indexes[name] = idx
    occupations, tasks, dwas, links = [indexes[n] for n in SCHEMA]
    task_dwas = defaultdict(set)
    for t in tasks.values():
        if t['occupation_code'] not in occupations: raise DataError('Task occupation FK missing')
        if t['task_type'] not in ('Core', 'Supplemental', ''): raise DataError('Invalid Task Type')
    for t, d in links:
        if t not in tasks or d not in dwas: raise DataError('Task-DWA FK missing')
        task_dwas[t].add(d)
    return {'occupations': occupations, 'tasks': tasks, 'dwas': dwas,
            'task_dwas': task_dwas, 'hashes': {n: sha256((directory / n).read_bytes()) for n in SCHEMA}}


def rule_classify(text):
    text = text.lower().strip()
    # Mixed clauses, negation, planning or ambiguous scope go to review, not exclusion.
    if re.search(MIXED, text): return 'uncertain', 'U_COMPOUND_OR_SCOPE'
    for rule, pattern in PHYSICAL.items():
        if re.fullmatch(pattern, text): return 'physical_required', rule
    for rule, pattern in DIGITAL.items():
        if re.search(pattern, text): return 'digital_candidate', rule
    return 'uncertain', 'U_NO_SUFFICIENT_RULE'


def eligibility(catalog, mode='ai4work', annotations=None, labels_file=None):
    decisions, rules = {}, Counter()
    if mode == 'ai4work':
        if not annotations or not annotations.is_file(): raise DataError('AI4Work annotations missing; choose explicit alternative --eligibility rules or labels')
        if sha256(annotations.read_bytes()) != EXPECTED_SHA256: raise DataError('AI4Work pinned checksum mismatch')
        annotation_rows, _ = read_annotations(annotations)
        for tid, task in sorted(catalog['tasks'].items()):
            label, rule, *_ = classify(task, annotation_rows)
            decisions[tid] = {'DIGITAL': LABELS[0], 'PHYSICAL': LABELS[1], 'REVIEW': LABELS[2]}[label]
            rules[rule] += 1
        provenance = {'provider': 'ai4work', 'url': SOURCE_URL, 'sha256': EXPECTED_SHA256,
                      'interpretation': 'External research annotation, not ground truth; PHYSICAL includes some in-person interactions.'}
    elif mode == 'rules':
        for tid, task in sorted(catalog['tasks'].items()):
            decisions[tid], rule = rule_classify(task['task_text'])
            rules[rule] += 1
        provenance = {'provider': RULE_VERSION, 'digital_rules': DIGITAL, 'physical_rules': PHYSICAL, 'uncertain_scope_rule': MIXED}
    elif mode == 'labels':
        if labels_file is None: raise DataError('--labels-file required')
        provided = {}
        for row in parse_csv(labels_file.read_bytes(), 'labels', ['task_id', 'eligibility']):
            if row['task_id'] not in catalog['tasks'] or row['eligibility'] not in LABELS: raise DataError('Invalid alternative label ID or value')
            insert(provided, row['task_id'], row['eligibility'], 'alternative labels')
        decisions = {tid: provided.get(tid, 'uncertain') for tid in sorted(catalog['tasks'])}
        rules['provided'] = len(provided); rules['missing_uncertain'] = len(decisions) - len(provided)
        provenance = {'provider': 'user_supplied_labels', 'sha256': sha256(labels_file.read_bytes()),
                      'interpretation': 'No claim of AI4Work reproduction; user must ensure label version compatibility.'}
    else: raise DataError('Unknown eligibility mode')
    return decisions, {'source': provenance, 'rule_counts': dict(sorted(rules.items())),
                       'counts': {k: list(decisions.values()).count(k) for k in LABELS}}


def tie(seed, key):
    return hashlib.sha256(f'{seed}\0{key}'.encode()).hexdigest()


def task_sample(catalog, candidates, n, seed, supplemental_target=.15, source_coverage=False):
    if n < 0 or not 0 <= supplemental_target <= 1: raise DataError('Invalid N or supplemental target')
    remaining = set(candidates)
    if not remaining <= catalog['tasks'].keys(): raise DataError('Unknown candidate Task ID')
    selected, occ, groups, dw = [], Counter(), Counter(), Counter()
    sources = Counter()
    supplemental = 0
    ranks = {t: tie(seed, t) for t in remaining}
    while remaining and len(selected) < n:
        prefer_supp = supplemental < math.floor((len(selected) + 1) * supplemental_target)
        def score(tid):
            t = catalog['tasks'][tid]; o = t['occupation_code']; g = o[:2]
            ds = catalog['task_dwas'][tid]
            priority = (2 if t['task_type'] == ('Supplemental' if prefer_supp else 'Core')
                        else 1 if t['task_type'] in ('Core', 'Supplemental') else 0)
            prefix = (not groups[g], not occ[o], sum(not dw[d] for d in ds))
            if source_coverage:
                # Two tertiary coverage objectives, not a source quota: opening a new
                # source gets real coverage credit even when no official DWA exists.
                new_source = not sources[t['task_source']]
                new_dwas = prefix[2]
                return prefix[:2] + (bool(new_dwas) + new_source, new_source, new_dwas,
                                    -occ[o], -groups[g], -sources[t['task_source']], priority, ranks[tid])
            return prefix + (-occ[o], -groups[g], priority, ranks[tid])
        chosen = max(sorted(remaining), key=score)
        remaining.remove(chosen); selected.append(chosen)
        t = catalog['tasks'][chosen]; occ[t['occupation_code']] += 1; groups[t['occupation_code'][:2]] += 1
        dw.update(catalog['task_dwas'][chosen]); supplemental += t['task_type'] == 'Supplemental'
        if source_coverage: sources[t['task_source']] += 1
    return selected


def coverage(catalog, ids):
    tasks = [catalog['tasks'][t] for t in ids]
    types = Counter(t['task_type'] or 'Missing' for t in tasks)
    groups = Counter(t['occupation_code'][:2] for t in tasks)
    occ = Counter(t['occupation_code'] for t in tasks)
    ds = set().union(*(catalog['task_dwas'][t] for t in ids)) if ids else set()
    return {'task_count': len(tasks), 'major_groups': len(groups), 'occupations': len(occ), 'dwas': len(ds),
            'major_group_counts': dict(sorted(groups.items())), 'occupation_counts': dict(sorted(occ.items())),
            'task_type_counts': {k: types[k] for k in ('Core', 'Supplemental', 'Missing')},
            'task_type_ratios': {k: types[k] / len(tasks) if tasks else 0 for k in ('Core', 'Supplemental', 'Missing')}}


def common_args(parser):
    parser.add_argument('--input-dir', type=Path, default=ROOT / 'data/processed')
    parser.add_argument('--eligibility', choices=['ai4work', 'rules', 'labels'], default='ai4work')
    parser.add_argument('--annotations', type=Path, default=ROOT / 'data/annotations/ai4work_digital_task_annotation.xlsx')
    parser.add_argument('--labels-file', type=Path)
    parser.add_argument('--n', type=int, required=True)
    parser.add_argument('--seed', type=int, default=42)


def main():
    p = argparse.ArgumentParser(description=__doc__); common_args(p)
    p.add_argument('--mode', choices=['raw', 'task-id'], default='raw')
    p.add_argument('--output-dir', type=Path)
    p.add_argument('--supplemental-target', type=float, default=.15)
    p.add_argument('--raw-dir', type=Path, default=ROOT / 'data/raw')
    p.add_argument('--emerging-file', type=Path)
    p.add_argument('--download-emerging', action='store_true')
    p.add_argument('--config', type=Path, default=ROOT / 'config/seed_pipeline.llmcenter.json')
    p.add_argument('--cache-dir', type=Path, default=ROOT / 'data/raw_seed_cache')
    p.add_argument('--batch-size', type=int, default=16)
    p.add_argument('--workers', type=int, default=4)
    p.add_argument('--offline', action='store_true')
    p.add_argument('--prompt-api-key', action='store_true')
    a = p.parse_args()
    if a.output_dir is None:
        a.output_dir = ROOT / ('data/raw_work_seeds' if a.mode == 'raw' else 'archive/data/task_sampling')
    if a.mode == 'raw':
        from emerging_tasks import build_raw_seeds
        try:
            report = build_raw_seeds(a)
        except (OSError, ValueError) as exc:
            # Preserve successful historical outputs; explicit error, no placeholder data.
            print('Stage 1 failed: ' + str(exc))
            raise
        print(json.dumps({k: report[k] for k in ('counts', 'classification_counts', 'digital_coverage', 'sampled')}, ensure_ascii=False, indent=2))
        return
    if a.output_dir.resolve() == a.input_dir.resolve(): raise DataError('Output may not overwrite input directory')
    catalog = load_catalog(a.input_dir)
    decisions, audit = eligibility(catalog, a.eligibility, a.annotations, a.labels_file)
    candidates = [t for t, status in decisions.items() if status == 'digital_candidate']
    sampled = task_sample(catalog, candidates, a.n, a.seed, a.supplemental_target)
    report = {'original_tasks': len(decisions), 'classification': audit, 'available': coverage(catalog, candidates),
              'sampled': coverage(catalog, sampled), 'parameters': {'n': a.n, 'seed': a.seed, 'supplemental_target': a.supplemental_target},
              'input_sha256': catalog['hashes'], 'algorithm': 'task-lexicographic-coverage-v1',
              'shortfall': max(0, a.n - len(sampled)),
              'limitations': ['Eligibility is a candidate annotation, not verified digital executability.',
                             'Supplemental target is a tie preference, not a quota overriding coverage.']}
    a.output_dir.mkdir(parents=True, exist_ok=True)
    (a.output_dir / 'seed_candidates.csv').write_bytes(encode_csv(['task_id', 'eligibility'], sorted(decisions.items())))
    (a.output_dir / 'sampled_seeds.csv').write_bytes(encode_csv(['task_id'], [(t,) for t in sampled]))
    (a.output_dir / 'sampling_report.json').write_bytes(json_bytes(report))
    print(json.dumps({k: report[k] for k in ('original_tasks', 'sampled', 'shortfall')}, ensure_ascii=False, indent=2))


if __name__ == '__main__': main()
