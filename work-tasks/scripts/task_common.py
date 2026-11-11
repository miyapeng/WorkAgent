"""Stage 4 shares Stage 1–3 I/O, model cache and parsing utilities."""
from pathlib import Path
import json
import sys
import re
from jsonschema import Draft202012Validator
from referencing import Registry, Resource

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO / 'workspaces/scripts'))
from common import DataError, require, sha256, json_bytes, save, read_jsonl


def read(path):
    return json.loads(Path(path).read_text())


def digest(value):
    return sha256(json_bytes(value))


def schema(name, value):
    registry=Registry().with_resources((v['$id'],Resource.from_contents(v)) for v in
        (read(p) for p in (ROOT/'config').glob('*.schema.json')))
    errors = sorted(Draft202012Validator(read(ROOT/'config'/f'{name}.schema.json'),registry=registry).iter_errors(value),
                    key=lambda e: str(list(e.path)))
    require(not errors, 'schema:'+name+(':'+str(list(errors[0].path)) if errors else ''))


def relative(value, prefix=None):
    require(isinstance(value, str) and value and '\\' not in value and ':' not in value
            and not any(ord(c)<32 for c in value), 'unsafe_path')
    p = Path(value)
    require(not p.is_absolute() and all(x not in ('', '.', '..') for x in value.split('/')), 'unsafe_path')
    if prefix: require(p.parts[0] == prefix and len(p.parts)>1, 'path_outside_'+prefix)
    return p


def confined(root, value):
    root=Path(root); p=root/relative(value)
    require(not root.is_symlink() and not any(x.is_symlink() for x in [p,*p.parents] if x!=root.parent), 'symlink_forbidden')
    require(p.resolve().is_relative_to(root.resolve()), 'path_escape')
    return p


def unique(rows, key):
    values=[r[key] for r in rows]
    require(len(values)==len(set(values)), 'duplicate_'+key)
    return {r[key]:r for r in rows}


HIDDEN=re.compile(r'(?:evaluation|construction)/|(?:rubric|verifier_spec|evidence_graph|oracle|audit_report)\.json', re.I)


def visible_text(value):
    text=json.dumps(value, ensure_ascii=False)
    require(not HIDDEN.search(text) and not re.search(r'\be_[a-f0-9]{24}\b',text), 'hidden_metadata_reference')
