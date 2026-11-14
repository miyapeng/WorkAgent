"""Shared repository utilities; no source facts are generated here."""
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
REPO = ROOT.parent
sys.path.insert(0, str(REPO / 'work-seeds/scripts'))
sys.path.insert(0, str(REPO / 'work-plans/scripts'))
from build_onet import DataError, json_bytes, sha256
from seed_evidence import save, read_jsonl, write_jsonl, now, normalized
from construct_seeds import llm_call


def require(condition, message):
    if not condition:
        raise DataError(message)


def safe_relative(value):
    p = Path(value)
    require(isinstance(value, str) and value and not p.is_absolute()
            and '..' not in p.parts and '\\' not in value and ':' not in value,
            'unsafe_relative_path')
    return p


def require_workspace_artifact(profile, path=None):
    """HTML is discovery/provenance material, never an Agent-visible input."""
    require(profile.get('type')!='html' and profile.get('format') not in ('html','htm','xhtml'),
            'html_not_allowed_in_workspace')
    if path is not None:
        require(Path(path).suffix.lower() not in ('.html','.htm','.xhtml'), 'html_not_allowed_in_workspace')
