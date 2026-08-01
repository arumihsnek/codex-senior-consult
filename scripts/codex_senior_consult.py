#!/usr/bin/env python3
"""Run one bounded, single-pass senior consultation."""
from __future__ import annotations

import argparse
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import uuid
from typing import Any

VERSION = "2.1.0"
BUNDLE_SCHEMA = "codex-senior-consult/v1"
RESPONSE_SCHEMA = "codex-senior-consult-response/v2"
V3_RESPONSE_SCHEMA = "codex-senior-consult-response/v3"
LEGACY_RESPONSE_SCHEMA = "codex-senior-consult-response/v1"
RESPONSE_ARTIFACT_SCHEMA = "codex-senior-consult-response-artifact/v1"
MODES = {"integrated-review", "plan", "plan-review", "replan", "blocker-analysis", "risk-audit", "final-review", "merge-gate"}
EFFORTS = {"low", "medium", "high", "xhigh"}
MEDIUM_TRIGGERS = {"cross_cutting_architecture", "security", "credentials", "process_isolation", "contradictory_evidence", "concurrency", "duplicate_side_effects", "public_contract", "destructive_migration", "alternatives_tie", "conceptual_plan_failure", "recovery"}
TOOL_ITEM_TYPES = {"command_execution", "mcp_tool_call", "dynamic_tool_call", "collab_tool_call", "web_search", "computer_tool_call", "file_search_call", "function_call", "file_change"}
NON_TOOL_ITEM_TYPES = {"agent_message", "reasoning", "todo_list", "error"}
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"), re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"), re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}\b"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:@/]+:[^\s@/]+@"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
]
SENSITIVE_KEY = re.compile(r"(?i)(?:password|passwd|secret|api.?key|access.?token|refresh.?token|private.?key|credential|authorization|bearer|auth)")
DESCRIPTIVE_KEY = re.compile(r"(?i)(?:scope|contract|policy|description|behavior|redaction|metadata|requirement|finding|risk)")
BASE_REQUIRED = {"schema_version", "mission_id", "mode", "objective", "decision_needed", "current_plan", "progress", "relevant_contracts", "observed_facts", "invalidated_assumptions", "candidate_decision", "alternatives", "code_excerpts", "diff", "tests", "runtime_evidence", "constraints", "risks_already_identified", "questions", "requested_output", "snapshot", "escalation"}
DETERMINISTIC_FIELDS = {"schema_version", "mission_id", "mode", "requested_output", "repository"}
CALLER_FIELDS = tuple(sorted(BASE_REQUIRED - DETERMINISTIC_FIELDS - {"snapshot"}))
CALLER_POINTERS = {f"/{name}" for name in CALLER_FIELDS} | {"/snapshot/plan_fingerprint", "/snapshot/checkpoint_fingerprint"}
EXPECTED_TYPES: dict[str, tuple[type, ...]] = {
    "/objective": (str,), "/decision_needed": (str,), "/current_plan": (dict,),
    "/progress": (dict,), "/candidate_decision": (dict,), "/alternatives": (list,),
    "/constraints": (list,), "/questions": (list,), "/escalation": (dict,),
    "/relevant_contracts": (list,), "/observed_facts": (list,),
    "/invalidated_assumptions": (list,), "/code_excerpts": (list,), "/diff": (dict,),
    "/tests": (list,), "/runtime_evidence": (list,), "/risks_already_identified": (list,),
    "/snapshot/plan_fingerprint": (str,), "/snapshot/checkpoint_fingerprint": (str,),
}

class ConsultError(Exception):
    def __init__(self, code: str, details: list[str] | None = None):
        super().__init__(code); self.code = code; self.details = details or []

def utc_now() -> str: return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def canonical(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def sha256(value: Any) -> str: return hashlib.sha256(canonical(value)).hexdigest()
def safe_mission_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value or ""): raise ConsultError("INVALID_MISSION_ID", ["mission_id must be path-safe and 1-128 characters"])
    return value

def translate_legacy_argv(argv: list[str]) -> list[str]:
    if argv and argv[0] in {"build-bundle", "preflight", "consult", "status"}: return list(argv)
    return ["consult", *argv]

def _git(repository: Path, *args: str) -> bytes:
    proc = subprocess.run(["git", "-C", str(repository), *args], stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE, check=False)
    if proc.returncode: raise ConsultError("INVALID_REPOSITORY", ["repository must be a readable Git worktree"])
    return proc.stdout

def build_bundle_skeleton(mission_id: str, mode: str, repository: Path) -> dict[str, Any]:
    safe_mission_id(mission_id)
    if mode not in MODES: raise ConsultError("BUNDLE_INCOMPLETE", ["unsupported mode"])
    repository = repository.resolve()
    head = _git(repository, "rev-parse", "HEAD").decode().strip()
    status = _git(repository, "status", "--porcelain=v1", "-z")
    diff = _git(repository, "diff", "--binary", "HEAD")
    tree_fingerprint = hashlib.sha256(status + b"\0" + diff).hexdigest()
    bundle: dict[str, Any] = {key: None for key in BASE_REQUIRED}
    bundle.update({
        "schema_version": BUNDLE_SCHEMA, "mission_id": mission_id, "mode": mode,
        "requested_output": {"schema_version": V3_RESPONSE_SCHEMA},
        "repository": {"name": repository.name, "dirty": bool(status),
                       "identity_fingerprint": hashlib.sha256(str(repository).encode()).hexdigest()},
        "snapshot": {"repository_head": head, "working_tree_fingerprint": tree_fingerprint,
                     "plan_fingerprint": None, "checkpoint_fingerprint": None},
        "caller_required": sorted(CALLER_POINTERS),
    })
    return bundle

def _pointer_parts(pointer: str) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        raise ValueError("invalid RFC 6901 pointer")
    parts = []
    for raw in pointer[1:].split("/"):
        if re.search(r"~(?![01])", raw): raise ValueError("invalid RFC 6901 escape")
        parts.append(raw.replace("~1", "/").replace("~0", "~"))
    return parts

def resolve_json_pointer(value: Any, pointer: str) -> Any:
    current = value
    for part in _pointer_parts(pointer):
        if not isinstance(current, dict) or part not in current: raise KeyError(pointer)
        current = current[part]
    return current

def assign_json_pointer(value: dict[str, Any], pointer: str, child: Any) -> None:
    current: Any = value; parts = _pointer_parts(pointer)
    for part in parts[:-1]:
        if not isinstance(current, dict) or part not in current: raise KeyError(pointer)
        current = current[part]
    if not isinstance(current, dict) or parts[-1] not in current: raise KeyError(pointer)
    current[parts[-1]] = child

def _sentinel(value: Any) -> bool:
    return isinstance(value, str) and bool(re.fullmatch(r"\s*[<\[]?(?:caller[_ -]?required|todo|tbd|placeholder)[>\]]?\s*", value, re.I))

def _diagnostic(code: str, path: str, state: str, reason: str, expected: str, guidance: str) -> dict[str, Any]:
    return {"code": code, "path": path, "state": state, "reason": reason,
            "expected": {"type": expected},
            "remediation": {"guidance": guidance, "suggested_source": "mission-owned sanitized evidence"},
            "category": "bundle", "model_process_consumed": False}

def normalize_construction_bundle(source: dict[str, Any]) -> dict[str, Any]:
    bundle = json.loads(json.dumps(source)); diagnostics: list[dict[str, Any]] = []
    pointers = bundle.get("caller_required", [])
    if not isinstance(pointers, list):
        diagnostics.append(_diagnostic("CALLER_REQUIRED_INVALID", "/caller_required", "invalid", "caller_required must be an array", "array", "Use unique RFC 6901 pointers.")); pointers = []
    seen: set[str] = set(); remaining: list[str] = []
    for pointer in pointers:
        if pointer in seen:
            diagnostics.append(_diagnostic("CALLER_REQUIRED_DUPLICATE_PATH", str(pointer), "invalid", "duplicate caller-required path", "unique RFC 6901 pointer", "Remove the duplicate path.")); continue
        seen.add(pointer)
        try: value = resolve_json_pointer(bundle, pointer)
        except (KeyError, ValueError, TypeError):
            diagnostics.append(_diagnostic("CALLER_REQUIRED_UNKNOWN_PATH", str(pointer), "missing", "path is outside the supported construction schema", "supported RFC 6901 pointer", "Use a path emitted by build-bundle.")); continue
        if pointer not in CALLER_POINTERS:
            diagnostics.append(_diagnostic("CALLER_REQUIRED_NON_NULL", pointer, "invalid", "deterministic fields must not be caller-fillable", "path absent from caller_required", "Remove this deterministic field path.")); continue
        expected = EXPECTED_TYPES[pointer]
        if value is None:
            diagnostics.append(_diagnostic("CALLER_VALUE_NULL", pointer, "null", "caller-owned evidence is still null", expected[0].__name__, "Supply bounded sanitized mission evidence.")); remaining.append(pointer); continue
        invalid = not isinstance(value, expected) or _sentinel(value)
        if isinstance(value, (str, list, dict)) and not value and pointer not in {"/invalidated_assumptions", "/risks_already_identified", "/code_excerpts", "/runtime_evidence", "/relevant_contracts", "/observed_facts"}: invalid = True
        if pointer.startswith("/snapshot/") and (not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{64}", value)): invalid = True
        if invalid:
            diagnostics.append(_diagnostic("CALLER_VALUE_INVALID", pointer, "invalid", "value fails its local type or value constraints", expected[0].__name__, "Replace it with a valid bounded value.")); remaining.append(pointer)
    bundle["caller_required"] = remaining
    return {"bundle": bundle, "caller_required": remaining, "diagnostics": diagnostics}

def preflight_bundle(source: dict[str, Any], *, mission_id: str, mode: str) -> dict[str, Any]:
    normalized = normalize_construction_bundle(source); diagnostics = normalized["diagnostics"]
    if normalized["caller_required"]:
        return {"status": "PREFLIGHT_INVALID", "valid": False, "diagnostics": diagnostics,
                "model_processes_consumed": 0, "checks": {"bundle": False, "local_state": True,
                "ledger_cache": True, "replacement": True, "lock": True}}
    payload = normalized["bundle"]; payload.pop("caller_required", None)
    try: prepared = validate_and_prepare_bundle(payload, mission_id, mode)
    except ConsultError as exc:
        for detail in exc.details:
            diagnostics.append(_diagnostic(exc.code, "/", "invalid", detail, "valid bundle", "Correct the reported field."))
        return {"status": "PREFLIGHT_INVALID", "valid": False, "diagnostics": diagnostics,
                "model_processes_consumed": 0, "checks": {"bundle": False, "local_state": True,
                "ledger_cache": True, "replacement": True, "lock": True}}
    snapshot_fingerprint = sha256(prepared["snapshot"])
    return {"status": "PREFLIGHT_VALID", "valid": True, "diagnostics": [], "payload": prepared,
            "model_processes_consumed": 0, "normalized": {"mode": mode, "mission_id": mission_id,
            "repository_head": prepared["snapshot"]["repository_head"],
            "dirty": bool(source.get("repository", {}).get("dirty")),
            "bundle_fingerprint": prepared["normalized_bundle_fingerprint"],
            "snapshot_fingerprint": snapshot_fingerprint, "caller_required_remaining": 0},
            "checks": {"bundle": True, "local_state": True, "ledger_cache": True,
                       "replacement": True, "lock": True}}

def secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700); info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode): raise ConsultError("INVALID_STATE_PATH", ["state directory must be a real directory"])
    path.chmod(0o700)

def _fsync_directory(path: Path) -> None:
    fd = os.open(path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0))
    try: os.fsync(fd)
    finally: os.close(fd)

def secure_write(path: Path, data: str) -> None:
    secure_dir(path.parent)
    if os.path.lexists(path) and stat.S_ISLNK(path.lstat().st_mode): raise ConsultError("INVALID_STATE_PATH", ["refusing symlink state file"])
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        payload = memoryview(data.encode())
        os.fchmod(fd, 0o600)
        while payload:
            written = os.write(fd, payload)
            if written <= 0: raise OSError("short state-file write")
            payload = payload[written:]
        os.fsync(fd); os.close(fd); fd = -1
        os.replace(name, path); path.chmod(0o600); _fsync_directory(path.parent)
    finally:
        if fd >= 0: os.close(fd)
        try: Path(name).unlink()
        except OSError: pass

def read_regular_input(raw_path: str, max_bytes: int) -> tuple[Path, bytes]:
    raw = Path(raw_path)
    if ".." in raw.parts: raise ConsultError("INVALID_BUNDLE_PATH", ["path traversal is not allowed"])
    try: initial = raw.lstat()
    except OSError: raise ConsultError("INVALID_BUNDLE_PATH", ["bundle is not an accessible regular file"])
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode): raise ConsultError("INVALID_BUNDLE_PATH", ["symlinks and special files are rejected"])
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    try: fd = os.open(raw, flags); info = os.fstat(fd)
    except OSError: raise ConsultError("INVALID_BUNDLE_PATH", ["bundle is not an accessible regular file"])
    if not stat.S_ISREG(info.st_mode): os.close(fd); raise ConsultError("INVALID_BUNDLE_PATH", ["bundle is not regular"])
    if info.st_size > max_bytes: os.close(fd); raise ConsultError("BUNDLE_TOO_LARGE", [f"bundle exceeds {max_bytes} bytes"])
    try: data = os.read(fd, max_bytes + 1)
    finally: os.close(fd)
    if len(data) > max_bytes: raise ConsultError("BUNDLE_TOO_LARGE", [f"bundle exceeds {max_bytes} bytes"])
    return raw.resolve(), data

def _credential_like(key: str, value: Any) -> bool:
    if value in (None, "", [], {}): return False
    if not SENSITIVE_KEY.search(key): return False
    if DESCRIPTIVE_KEY.search(key) and isinstance(value, str) and len(value) < 500: return False
    if isinstance(value, (dict, list)): return True
    if not isinstance(value, str): return True
    if any(pattern.search(value) for pattern in SECRET_PATTERNS): return True
    # A non-empty value under an exact credential key is ambiguous and fails closed;
    # ordinary prose is allowed only in explicitly descriptive fields.
    exact = re.fullmatch(r"(?i)(?:password|passwd|secret|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret|private[_-]?key|credential|authorization|bearer|auth)", key)
    return bool(exact)

def _privacy_category(key: str, value: Any) -> str | None:
    folded = key.casefold()
    if folded in {"sha256", "fingerprint", "repository_head", "working_tree_fingerprint",
                  "plan_fingerprint", "checkpoint_fingerprint", "identity_fingerprint"} and \
            isinstance(value, str) and re.fullmatch(r"[0-9a-f]{40,64}", value): return None
    patterns = [pattern for pattern in SECRET_PATTERNS if pattern.search(value)] if isinstance(value, str) else []
    if patterns:
        if "private key" in value.casefold(): return "private_key_material"
        return "credential_shaped_value"
    if not SENSITIVE_KEY.search(key): return None
    if isinstance(value, bool) and re.search(r"(?i)(?:added|reviewed|present|enabled|disabled|checked)$", key): return None
    if isinstance(value, str) and DESCRIPTIVE_KEY.search(key) and len(value) < 500: return None
    if value in (None, "", [], {}): return None
    return "ambiguous_sensitive_value"

def privacy_findings(value: Any, path: str = "") -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            escaped = str(key).replace("~", "~0").replace("/", "~1"); child_path = f"{path}/{escaped}"
            category = _privacy_category(str(key), child)
            if category: findings.append({"path": child_path, "category": category})
            findings.extend(privacy_findings(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value): findings.extend(privacy_findings(child, f"{path}/{index}"))
    elif isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_PATTERNS):
        findings.append({"path": path or "/", "category": "private_key_material" if "private key" in value.casefold() else "credential_shaped_value"})
    unique = {(item["path"], item["category"]): item for item in findings}
    return [unique[key] for key in sorted(unique)]

def secret_locations(value: Any, path: str = "$") -> list[str]:
    prefix = "" if path == "$" else path
    return sorted({f["path"] if not prefix else f"{prefix}{f['path']}" for f in privacy_findings(value)})

def private_path_locations(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if str(key).casefold() in {"path", "file", "filename"} and isinstance(child, str) and (Path(child).is_absolute() or ".." in Path(child).parts or child.startswith("~")): hits.append(child_path)
            hits.extend(private_path_locations(child, child_path))
    elif isinstance(value, list):
        for i, child in enumerate(value): hits.extend(private_path_locations(child, f"{path}[{i}]"))
    return sorted(set(hits))

def validate_and_prepare_bundle(bundle: Any, mission_id: str, mode: str) -> dict[str, Any]:
    if not isinstance(bundle, dict): raise ConsultError("BUNDLE_INCOMPLETE", ["bundle must be an object"])
    missing = [f"missing field: {k}" for k in sorted(BASE_REQUIRED - set(bundle))]
    if bundle.get("schema_version") != BUNDLE_SCHEMA: missing.append(f"schema_version must be {BUNDLE_SCHEMA}")
    if bundle.get("mission_id") != mission_id: missing.append("bundle mission_id must match --mission-id")
    if bundle.get("mode") != mode or mode not in MODES: missing.append("bundle mode must match supported --mode")
    for key in ("objective", "decision_needed"):
        if not isinstance(bundle.get(key), str) or not bundle[key].strip(): missing.append(f"{key} must be non-empty")
    for key in ("current_plan", "progress", "candidate_decision"):
        if not isinstance(bundle.get(key), dict) or not bundle[key]: missing.append(f"{key} must be a non-empty object")
    if not isinstance(bundle.get("alternatives"), list) or not bundle["alternatives"]: missing.append("alternatives must be a non-empty list")
    if not isinstance(bundle.get("constraints"), list) or not bundle["constraints"] or not all(isinstance(x, str) and x.strip() for x in bundle["constraints"]): missing.append("constraints must be a non-empty string list")
    questions = bundle.get("questions")
    if not isinstance(questions, list) or not any(isinstance(q, (str, dict)) and q for q in questions): missing.append("questions must contain concrete questions")
    requested = bundle.get("requested_output")
    if not isinstance(requested, dict) or requested.get("schema_version") not in {V3_RESPONSE_SCHEMA, RESPONSE_SCHEMA, LEGACY_RESPONSE_SCHEMA}: missing.append(f"requested_output.schema_version must be {V3_RESPONSE_SCHEMA} (v1/v2 are historical compatibility only)")
    snapshot = bundle.get("snapshot"); snapshot_keys = {"repository_head", "working_tree_fingerprint", "plan_fingerprint", "checkpoint_fingerprint"}
    if not isinstance(snapshot, dict) or not snapshot_keys.issubset(snapshot): missing.append("snapshot must identify HEAD and all fingerprints")
    elif (not re.fullmatch(r"[0-9a-f]{40,64}", str(snapshot["repository_head"])) or any(not re.fullmatch(r"[0-9a-f]{64}", str(snapshot[k])) for k in snapshot_keys - {"repository_head"})): missing.append("snapshot fingerprints are invalid")
    if not any(bundle.get(k) for k in ("relevant_contracts", "observed_facts", "code_excerpts", "tests", "runtime_evidence")): missing.append("at least one evidence field must be non-empty")
    for key in ("relevant_contracts", "observed_facts", "invalidated_assumptions", "code_excerpts", "tests", "runtime_evidence", "risks_already_identified"):
        if not isinstance(bundle.get(key), list): missing.append(f"{key} must be an array")
    esc = bundle.get("escalation")
    if not isinstance(esc, dict): missing.append("escalation must be an object")
    else:
        if not isinstance(esc.get("local_deterministic_checks"), list) or not esc["local_deterministic_checks"]: missing.append("escalation.local_deterministic_checks must be non-empty")
        if not isinstance(esc.get("material_impact"), str) or not esc["material_impact"].strip(): missing.append("escalation.material_impact must be non-empty")
    if missing: raise ConsultError("BUNDLE_INCOMPLETE", missing)
    hits = secret_locations(bundle)
    if hits: raise ConsultError("SECRET_DETECTED", [f"secret-like material at {x}" for x in hits])
    private = private_path_locations(bundle)
    if private: raise ConsultError("PRIVATE_PATH_DETECTED", [f"private path at {x}" for x in private])
    normalized = json.loads(json.dumps(bundle)); seen: set[str] = set()
    for i, q in enumerate(normalized["questions"]):
        if isinstance(q, str): q = {"id": f"Q{i + 1}", "text": q}; normalized["questions"][i] = q
        if not isinstance(q, dict) or not re.fullmatch(r"[A-Za-z0-9._-]{1,64}", str(q.get("id", ""))) or not isinstance(q.get("text"), str) or not q["text"].strip() or q["id"] in seen: raise ConsultError("BUNDLE_INCOMPLETE", [f"questions[{i}] requires unique id and text"])
        seen.add(q["id"])
    normalized["normalized_bundle_fingerprint"] = sha256(normalized)
    return normalized

def question_ids(bundle: dict[str, Any]) -> list[str]: return [str(q["id"]) for q in bundle["questions"]]

STRING = {"type": "string", "minLength": 1}
# Codex's structured-output endpoint rejects JSON Schema `uniqueItems`; keep
# list elements non-empty and enforce cross-item rules locally where required.
STRING_LIST = {"type": "array", "items": STRING}
QUESTION_ANSWER = {"type": "object", "additionalProperties": False, "required": ["id", "answer"], "properties": {"id": STRING, "answer": STRING}}
FINDING = {"type": "object", "additionalProperties": False, "required": ["id", "claim", "severity", "evidence", "reasoning_summary"], "properties": {"id": STRING, "claim": STRING, "severity": {"type": "string", "enum": ["blocking", "non_blocking"]}, "evidence": STRING_LIST, "reasoning_summary": STRING}}
CAUSE = {"type": "object", "additionalProperties": False, "required": ["id", "cause", "evidence"], "properties": {"id": STRING, "cause": STRING, "evidence": STRING_LIST}}
PATH = {"type": "object", "additionalProperties": False, "required": ["id", "action", "rationale"], "properties": {"id": STRING, "action": STRING, "rationale": STRING}}
RISK = {"type": "object", "additionalProperties": False, "required": ["id", "risk", "impact"], "properties": {"id": STRING, "risk": STRING, "impact": STRING}}
NON_BLOCKING_OBSERVATION = {"type": "object", "additionalProperties": False,
    "required": ["id", "claim", "evidence", "reasoning_summary"],
    "properties": {"id": STRING, "claim": STRING, "evidence": STRING_LIST, "reasoning_summary": STRING}}
CLAIM = {"type": "object", "additionalProperties": False, "required": ["claim", "classification", "evidence"], "properties": {"claim": STRING, "classification": {"type": "string", "enum": ["supported", "unsupported", "uncertain"]}, "evidence": STRING_LIST}}
DECISION = {"type": "object", "additionalProperties": False, "required": ["recommendation", "rationale"], "properties": {"recommendation": STRING, "rationale": STRING}}
PLAN = {"type": "object", "additionalProperties": False, "required": ["steps", "stop_conditions"], "properties": {"steps": STRING_LIST, "stop_conditions": STRING_LIST}}

# This is the authoritative v2 contract.  Both emitted JSON Schema and the
# local semantic validator below derive their structural rules from it.
MODE_CONTRACTS: dict[str, dict[str, Any]] = {
    "merge-gate": {"verdicts": ("accept", "changes_required", "blocked"), "fields": {"safe_to_merge": {"type": "boolean"}, "blocking_findings": {"type": "array", "items": FINDING}, "required_actions": STRING_LIST, "residual_risks": {"type": "array", "items": RISK}, "summary": STRING}},
    "blocker-analysis": {"verdicts": ("continue", "human_required", "blocked"), "fields": {"ranked_causes": {"type": "array", "items": CAUSE}, "continuation_paths": {"type": "array", "items": PATH}, "recommended_path": STRING, "cheapest_discriminating_experiment": STRING, "stop_conditions": STRING_LIST, "next_safe_step": STRING}},
    "replan": {"verdicts": ("continue", "changes_required", "blocked"), "fields": {"invalidated_assumptions": STRING_LIST, "plan_delta": STRING_LIST, "closed_phases_preserved": STRING_LIST, "new_stop_conditions": STRING_LIST, "next_safe_step": STRING}},
    "integrated-review": {"verdicts": ("accept", "changes_required", "blocked"), "fields": {"summary": STRING, "findings": {"type": "array", "items": FINDING}, "decision": DECISION, "next_safe_step": STRING}},
    "plan": {"verdicts": ("continue", "changes_required", "blocked"), "fields": {"summary": STRING, "plan": PLAN, "risks": {"type": "array", "items": RISK}, "next_safe_step": STRING}},
    "plan-review": {"verdicts": ("accept", "changes_required", "blocked"), "fields": {"summary": STRING, "blocking_findings": {"type": "array", "items": FINDING}, "required_actions": STRING_LIST, "next_safe_step": STRING}},
    "risk-audit": {"verdicts": ("continue", "changes_required", "blocked"), "fields": {"risks": {"type": "array", "items": RISK}, "controls": STRING_LIST, "residual_risks": {"type": "array", "items": RISK}, "next_safe_step": STRING}},
    "final-review": {"verdicts": ("accept", "changes_required", "blocked"), "fields": {"claim_classifications": {"type": "array", "items": CLAIM}, "summary": STRING, "next_safe_step": STRING}},
}
V3_MODE_CONTRACTS = json.loads(json.dumps(MODE_CONTRACTS))
V3_MODE_CONTRACTS["merge-gate"]["fields"]["non_blocking_observations"] = {"type": "array", "items": NON_BLOCKING_OBSERVATION}
MODE_FIELDS = {mode: ("verdict", *contract["fields"].keys(), "question_answers") for mode, contract in MODE_CONTRACTS.items()}
TRANSPORT_SCHEMA_ALLOWLIST = {"type", "properties", "required", "additionalProperties", "items", "enum", "description"}

def local_semantic_contract(mode: str = "integrated-review", schema_version: str = RESPONSE_SCHEMA) -> dict[str, Any]:
    contract = V3_MODE_CONTRACTS[mode] if schema_version == V3_RESPONSE_SCHEMA else MODE_CONTRACTS[mode]
    properties = {"schema_version": {"type": "string", "const": schema_version}, "verdict": {"type": "string", "enum": list(contract["verdicts"])}, "question_answers": {"type": "array", "items": QUESTION_ANSWER}, **contract["fields"]}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False, "required": list(properties), "properties": properties}

def _conservative_transport_shape(value: Any) -> Any:
    if isinstance(value, list): return [_conservative_transport_shape(item) for item in value]
    if not isinstance(value, dict): return value
    out: dict[str, Any] = {}
    for key, child in value.items():
        if key not in TRANSPORT_SCHEMA_ALLOWLIST: continue
        if key == "properties" and isinstance(child, dict):
            out[key] = {name: _conservative_transport_shape(schema) for name, schema in child.items()}
        else:
            out[key] = _conservative_transport_shape(child)
    if out.get("additionalProperties") is False and isinstance(out.get("properties"), dict):
        # The backend's strict-output dialect requires every declared property
        # to be listed in required; local semantics retain true optionality.
        out["required"] = list(out["properties"])
    return out

def backend_transport_schema(mode: str = "integrated-review", schema_version: str = RESPONSE_SCHEMA) -> dict[str, Any]:
    return _conservative_transport_shape(local_semantic_contract(mode, schema_version))

def response_schema(mission_id: str | None = None, mode: str = "integrated-review", model: str | None = None, effort: str | None = None, execution: int | None = None, snapshot: str | None = None, schema_version: str = RESPONSE_SCHEMA) -> dict[str, Any]:
    return backend_transport_schema(mode, schema_version)

def _legacy_errors(value: Any, mission_id: str, mode: str, model: str, effort: str, questions: list[Any], snapshot: str) -> list[str]:
    if not isinstance(value, dict): return ["response must be an object"]
    required = {"schema_version", "mission_id", "mode", "model", "reasoning_effort", "snapshot", "verdict", "summary", "blocking_findings", "required_actions", "confidence"}
    errors = [f"missing {x}" for x in sorted(required - set(value))]
    if value.get("schema_version") != LEGACY_RESPONSE_SCHEMA: errors.append("schema_version must equal legacy v1")
    for key, expected in (("mission_id", mission_id), ("mode", mode), ("model", model), ("reasoning_effort", effort), ("snapshot", snapshot)):
        if value.get(key) != expected: errors.append(f"{key} mismatch")
    if value.get("verdict") not in {"accept", "changes_required", "blocked"}: errors.append("invalid verdict")
    if mode == "merge-gate":
        if value.get("verdict") == "accept" and (value.get("safe_to_merge") is not True or value.get("blocking_findings") != [] or value.get("required_actions") != []): errors.append("merge-gate accept is inconsistent")
        if value.get("verdict") != "accept" and value.get("safe_to_merge") is not False: errors.append("merge-gate non-accept must be unsafe")
    if not isinstance(value.get("blocking_findings"), list) or not isinstance(value.get("required_actions"), list): errors.append("finding arrays invalid")
    for finding in value.get("blocking_findings", []):
        if (not isinstance(finding, dict) or not isinstance(finding.get("id"), str) or not isinstance(finding.get("claim"), str) or not isinstance(finding.get("severity"), str) or not isinstance(finding.get("evidence"), list) or not isinstance(finding.get("reasoning_summary"), str) or ("required_change" in finding and finding.get("required_change") is not None and not isinstance(finding.get("required_change"), str))): errors.append("finding object invalid")
    if len(value.get("questions_answered", [])) != len(questions): errors.append("every grouped question must be addressed")
    if set(value) - {"schema_version", "mission_id", "mode", "model", "reasoning_effort", "snapshot", "verdict", "summary", "blocking_findings", "non_blocking_findings", "assumptions", "required_actions", "plan_delta", "evidence_missing", "questions_answered", "next_safe_step", "confidence", "safe_to_merge"}: errors.append("additional property")
    return errors

def validate_response(value: Any, mission_id: str, mode: str, model: str, effort: str, questions: list[Any], snapshot: str, *, allow_legacy: bool = True, allow_historical: bool = True) -> list[str]:
    if isinstance(value, dict) and value.get("schema_version") == LEGACY_RESPONSE_SCHEMA:
        return _legacy_errors(value, mission_id, mode, model, effort, questions, snapshot) if allow_legacy else ["legacy v1 response requires --legacy-response-v1"]
    if not isinstance(value, dict): return ["response must be an object"]
    version = value.get("schema_version")
    if version == RESPONSE_SCHEMA and not allow_historical: return [f"historical response requires explicit compatibility mode; expected {V3_RESPONSE_SCHEMA}"]
    if version not in {RESPONSE_SCHEMA, V3_RESPONSE_SCHEMA}: return [f"schema_version must equal {V3_RESPONSE_SCHEMA}"]
    schema = local_semantic_contract(mode=mode, schema_version=version); errors = schema_errors(value, schema)
    expected_ids = [str(q.get("id")) if isinstance(q, dict) else f"Q{i + 1}" for i, q in enumerate(questions)]
    answers = value.get("question_answers", [])
    if isinstance(answers, list):
        ids = [answer.get("id") for answer in answers if isinstance(answer, dict)]
        if len(ids) != len(expected_ids) or set(ids) != set(expected_ids) or len(set(ids)) != len(ids): errors.append("question_answers must contain every supplied question ID exactly once")
    if mode == "merge-gate":
        if value.get("verdict") == "accept":
            if value.get("safe_to_merge") is not True: errors.append("MERGE_GATE_ACCEPT_CONTRADICTION /safe_to_merge expected true")
            if value.get("blocking_findings") != []: errors.append("MERGE_GATE_ACCEPT_CONTRADICTION /blocking_findings expected empty array")
            if value.get("required_actions") != []: errors.append("MERGE_GATE_ACCEPT_CONTRADICTION /required_actions expected empty array")
        if value.get("verdict") != "accept" and value.get("safe_to_merge") is not False: errors.append("merge-gate non-accept must be unsafe")
        if value.get("verdict") == "changes_required" and not value.get("blocking_findings") and not value.get("required_actions"): errors.append("merge-gate changes_required requires a finding or action")
        if value.get("verdict") == "blocked" and not value.get("blocking_findings"): errors.append("merge-gate blocked requires blocking evidence")
    if mode == "plan-review" and value.get("verdict") == "accept" and (value.get("blocking_findings") != [] or value.get("required_actions") != []): errors.append("plan-review accept is inconsistent")
    if mode == "integrated-review" and value.get("verdict") == "accept" and value.get("findings") != []: errors.append("integrated-review accept is inconsistent")
    return errors

def schema_errors(value: Any, schema: dict[str, Any], path: str = "$") -> list[str]:
    errors: list[str] = []; typ = schema.get("type")
    expected = {"object": dict, "array": list, "string": str, "boolean": bool}
    if typ and (not isinstance(value, expected[typ]) or typ == "boolean" and not isinstance(value, bool)):
        return [f"{path} has invalid type"]
    if typ == "string":
        if len(value) < schema.get("minLength", 0): errors.append(f"{path} must be non-empty")
        if "enum" in schema and value not in schema["enum"]: errors.append(f"{path} invalid verdict")
    if typ == "array":
        if len(value) < schema.get("minItems", 0): errors.append(f"{path} has too few items")
        if schema.get("uniqueItems") and len({json.dumps(item, sort_keys=True) for item in value}) != len(value): errors.append(f"{path} has duplicate items")
        for index, item in enumerate(value): errors.extend(schema_errors(item, schema.get("items", {}), f"{path}[{index}]"))
    if typ == "object":
        properties = schema.get("properties", {}); missing = set(schema.get("required", ())) - set(value)
        errors.extend(f"missing {path}.{key}" for key in sorted(missing))
        if schema.get("additionalProperties") is False: errors.extend(f"additional property {path}.{key}" for key in sorted(set(value) - set(properties)))
        for key, child in value.items():
            if key in properties: errors.extend(schema_errors(child, properties[key], f"{path}.{key}"))
    return errors

def count_events(stdout: str) -> tuple[int, int, bool, list[str]]:
    turns = tools = 0; terminal = False; diagnostics: list[str] = []; seen_tools: set[str] = set()
    for number, line in enumerate(stdout.splitlines(), 1):
        if not line.strip(): continue
        try: event = json.loads(line)
        except json.JSONDecodeError: diagnostics.append(f"invalid JSONL event at line {number}"); continue
        typ = event.get("type")
        if typ not in {"thread.started", "turn.started", "turn.completed", "turn.failed", "item.started", "item.updated", "item.completed", "error", *TOOL_ITEM_TYPES}: diagnostics.append(f"unknown JSONL event type at line {number}")
        if typ == "turn.started": turns += 1
        if typ == "turn.completed": terminal = True
        item = event.get("item") if isinstance(event.get("item"), dict) else event
        item_type = item.get("type") if isinstance(item, dict) else None
        if item_type in TOOL_ITEM_TYPES:
            ident = item.get("id", f"line-{number}"); seen_tools.add(str(ident))
    return turns, len(seen_tools), terminal, diagnostics

def child_environment() -> dict[str, str]:
    # CODEX_HOME is deliberately the only authentication-bearing location that
    # survives.  The CLI documents that --ignore-user-config still uses it for
    # authentication; credentials and provider variables never cross this boundary.
    keep = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "CODEX_HOME"}
    env = {k: v for k, v in os.environ.items() if k in keep}
    env["CODEX_SENIOR_CONSULT_ACTIVE"] = "1"
    return env

def sanitize_stderr(stderr: str, limit: int = 400) -> str:
    value = stderr
    for pattern in SECRET_PATTERNS: value = pattern.sub("[REDACTED]", value)
    value = re.sub(r"(?i)\b(authorization|password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token|client[_-]?secret)\s*[:=]\s*[^\s]+", r"\1=[REDACTED]", value)
    value = re.sub(r"(?i)\bBearer\s+[^\s]+", "Bearer [REDACTED]", value)
    value = re.sub(r"(?<![A-Za-z0-9_.-])/(?:[^\s'\"]+)", "[PRIVATE_PATH]", value)
    return " ".join(value.split())[:limit]

def transport_event_summary(stdout: str, limit: int = 4) -> list[str]:
    summary: list[str] = []
    for line in stdout.splitlines():
        try: event = json.loads(line)
        except json.JSONDecodeError: continue
        if not isinstance(event, dict): continue
        if event.get("type") == "error":
            error = event.get("error", {})
            code = error.get("code") if isinstance(error, dict) else None
            message = error.get("message") if isinstance(error, dict) else event.get("message", "")
            summary.append(f"jsonl error: {code}" if isinstance(code, str) and code else f"jsonl error: {sanitize_stderr(str(message), 240)}")
        elif event.get("type") == "turn.failed": summary.append("turn.failed")
        if len(summary) >= limit: break
    return summary

def classify_transport_failure(stderr: str, stdout: str = "") -> str:
    events = transport_event_summary(stdout)
    if any("invalid_json_schema" in item for item in events): return "SCHEMA_OR_REQUEST_REJECTION"
    text = (stderr + "\n" + "\n".join(events)).casefold()
    categories = (
        ("CLI_ARGUMENT_ERROR", ("unknown option", "unrecognized option", "unexpected argument", "cannot be used multiple times", "invalid value for", "requires a value")),
        ("AUTHENTICATION_ERROR", ("not logged in", "authentication", "login required", "unauthorized", "forbidden", "401", "403")),
        ("MODEL_UNAVAILABLE", ("model unavailable", "model not found", "unknown model", "does not exist")),
        ("RATE_LIMIT_OR_QUOTA", ("rate limit", "quota", "too many requests", "429")),
        ("NETWORK_OR_SERVICE_ERROR", ("network", "connection", "connect", "dns", "service unavailable", "gateway", "timed out", "timeout", "502", "503", "504")),
    )
    return next((category for category, evidence in categories if any(marker in text for marker in evidence)), "UNKNOWN_TRANSPORT_ERROR")

def sanitize_transport_stderr(stderr: str) -> str:
    """Retain bounded transport diagnostics without exposing secrets or paths."""
    value = re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", stderr or "")
    for pattern in SECRET_PATTERNS:
        value = pattern.sub("[REDACTED]", value)
    value = re.sub(r"(?<![A-Za-z0-9])(?:/home/[^\s]+|/tmp/[^\s]+)", "<path>", value)
    lines = [line.strip() for line in value.splitlines() if line.strip()]
    return " | ".join(lines[-8:])[:1200]

def parse_transport_evidence(stdout: str, stderr: str, exit_code: int, timed_out: bool,
                             *, event_limit: int = 128, evidence_limit: int = 8) -> dict[str, Any]:
    malformed = unknown = 0; structured = False; evidence: list[dict[str, str]] = []
    known = {"thread.started", "turn.started", "turn.completed", "turn.failed", "item.started",
             "item.updated", "item.completed", "error", *TOOL_ITEM_TYPES}
    for line in stdout.splitlines()[:event_limit]:
        if not line.strip(): continue
        try: event = json.loads(line)
        except json.JSONDecodeError: malformed += 1; continue
        typ = event.get("type")
        if typ not in known: unknown += 1
        if typ not in {"error", "turn.failed"}: continue
        structured = True; error = event.get("error") if isinstance(event.get("error"), dict) else {}
        code = error.get("code") or event.get("code") or "unclassified"
        evidence.append({"source": f"jsonl.{typ}", "code": re.sub(r"[^a-z0-9_.-]", "_", str(code).casefold())[:80]})
    sanitized = sanitize_transport_stderr(stderr)
    codes = " ".join(item["code"] for item in evidence); text = (codes + " " + sanitized).casefold()
    if timed_out: category = "PROCESS_TIMEOUT"
    elif any(x in text for x in ("unknown option", "unrecognized option", "unexpected argument", "invalid value for")): category = "CLI_ARGUMENT_FAILURE"
    elif any(x in text for x in ("unauthorized", "authentication", "not logged in", "login required", "401", "403")): category = "AUTHENTICATION_FAILURE"
    elif any(x in text for x in ("model_not_found", "model unavailable", "unknown model")): category = "MODEL_UNAVAILABLE"
    elif any(x in text for x in ("rate_limit", "quota", "too many requests", "429")): category = "QUOTA_OR_RATE_LIMIT"
    elif any(x in text for x in ("invalid_json_schema", "invalid_request", "schema rejection")): category = "SCHEMA_OR_REQUEST_REJECTION"
    elif any(x in text for x in ("safety_policy", "policy rejection", "safety rejection")): category = "SAFETY_OR_POLICY_REJECTION"
    elif any(x in text for x in ("network", "connection", "dns", "service unavailable", "502", "503", "504")): category = "NETWORK_OR_SERVICE_FAILURE"
    elif structured: category = "UNKNOWN_TRANSPORT_ERROR"
    else: category = "PROCESS_EXIT_WITHOUT_STRUCTURED_EVIDENCE"
    if sanitized:
        evidence.append({"source": "stderr", "category": category.casefold()})
    evidence = evidence[:evidence_limit]
    normalized = {"transport_category": category, "transport_evidence": evidence,
                  "transport_exit_code": exit_code, "structured_transport_evidence": structured,
                  "malformed_jsonl_events": malformed, "unknown_event_types": unknown,
                  "diagnostics_truncated": len(stdout.splitlines()) > event_limit or len(evidence) >= evidence_limit}
    normalized["diagnostic_fingerprint"] = sha256(normalized)
    return normalized

def run_process(command: list[str], prompt: str, timeout: int, cwd: Path) -> tuple[int, str, str, bool]:
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, cwd=cwd, env=child_environment(), start_new_session=True)
    try:
        stdout, stderr = proc.communicate(prompt, timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGKILL); proc.communicate(); return 124, "", "timeout", True
    return proc.returncode, stdout, stderr, False

def read_ledger(path: Path, mission: str) -> list[dict[str, Any]]:
    if not path.exists(): return []
    out = []
    for line in path.read_text().splitlines():
        try:
            value = json.loads(line)
            if value.get("mission_id") == mission: out.append(value)
        except json.JSONDecodeError: raise ConsultError("LEDGER_CORRUPT", ["ledger contains invalid JSON"])
    return out

def append_ledger(path: Path, entry: dict[str, Any]) -> None:
    secure_dir(path.parent); with_path = path
    if os.path.lexists(with_path) and stat.S_ISLNK(with_path.lstat().st_mode): raise ConsultError("INVALID_STATE_PATH", ["ledger cannot be symlinked"])
    with with_path.open("a+", encoding="utf-8") as f:
        os.chmod(with_path, 0o600); fcntl.flock(f, fcntl.LOCK_EX)
        try:
            f.seek(0)
            for line in f:
                try: existing = json.loads(line)
                except json.JSONDecodeError: raise ConsultError("LEDGER_CORRUPT", ["ledger contains invalid JSON"])
                if existing.get("execution_id") == entry.get("execution_id"):
                    raise ConsultError("DUPLICATE_EXECUTION_REPLAY", ["execution_id already exists in ledger"])
            f.seek(0, os.SEEK_END); f.write(json.dumps(entry, sort_keys=True) + "\n"); f.flush(); os.fsync(f.fileno()); _fsync_directory(with_path.parent)
        finally: fcntl.flock(f, fcntl.LOCK_UN)

def artifact_path(cache_dir: Path, fingerprint: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{64}", fingerprint): raise ConsultError("VERDICT_EVIDENCE_UNUSABLE", ["invalid response artifact fingerprint"])
    return cache_dir / "responses" / f"{fingerprint}.json"

def identity_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    return {"snapshot": entry.get("snapshot"), "bundle": entry.get("normalized_bundle_fingerprint"), "mode": entry.get("mode"), "model": entry.get("model"), "effort": entry.get("reasoning_effort")}

def response_answer_ids(response: dict[str, Any], legacy_ids: list[str]) -> list[str]:
    if response.get("schema_version") == LEGACY_RESPONSE_SCHEMA:
        answers = response.get("questions_answered")
        return list(legacy_ids) if isinstance(answers, list) and len(answers) == len(legacy_ids) else []
    answers = response.get("question_answers")
    return [answer.get("id") for answer in answers if isinstance(answer, dict)] if isinstance(answers, list) else []

def response_persistence_sensitive_locations(value: Any, path: str = "$") -> list[str]:
    hits = secret_locations(value) + private_path_locations(value)
    if isinstance(value, dict):
        for key, child in value.items(): hits.extend(response_persistence_sensitive_locations(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value): hits.extend(response_persistence_sensitive_locations(child, f"{path}[{index}]"))
    elif isinstance(value, str) and re.search(r"(?:^|\s)(?:/home/|/tmp/|/Users/|~(?:/|$))", value):
        hits.append(path)
    return sorted(set(hits))

def _response_artifact_record(response: dict[str, Any], identity: dict[str, Any], question_answer_ids: list[str]) -> dict[str, Any]:
    fingerprint = sha256(response)
    return {"artifact_schema": RESPONSE_ARTIFACT_SCHEMA, "response_schema_version": response.get("schema_version"), "response_fingerprint": fingerprint, "identity": identity, "question_answer_ids": question_answer_ids, "response": response}

def _read_artifact(path: Path, fingerprint: str, identity: dict[str, Any]) -> dict[str, Any]:
    try:
        info = path.lstat()
        if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or stat.S_IMODE(info.st_mode) != 0o600:
            raise ValueError("artifact is not a private regular file")
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ConsultError("VERDICT_EVIDENCE_UNUSABLE", ["response evidence is missing or unreadable"]) from exc
    if (not isinstance(value, dict) or value.get("artifact_schema") != RESPONSE_ARTIFACT_SCHEMA or
            value.get("response_fingerprint") != fingerprint or value.get("identity") != identity or
            not isinstance(value.get("response"), dict) or sha256(value["response"]) != fingerprint or
            not isinstance(value.get("question_answer_ids"), list) or
            value.get("question_answer_ids") != response_answer_ids(value["response"], value["question_answer_ids"])):
        raise ConsultError("VERDICT_EVIDENCE_UNUSABLE", ["response evidence fingerprint or identity mismatch"])
    return value

def persist_response_evidence(cache_dir: Path, response: dict[str, Any], identity: dict[str, Any], question_answer_ids: list[str]) -> dict[str, Any]:
    if response_persistence_sensitive_locations(response):
        raise ConsultError("VERDICT_PERSISTENCE_FAILURE", ["validated response contains sensitive material unsuitable for persistence"])
    if question_answer_ids != response_answer_ids(response, question_answer_ids):
        raise ConsultError("VERDICT_PERSISTENCE_FAILURE", ["validated response question-answer coverage changed before persistence"])
    record = _response_artifact_record(response, identity, question_answer_ids)
    fingerprint = record["response_fingerprint"]; path = artifact_path(cache_dir, fingerprint)
    if path.exists():
        _read_artifact(path, fingerprint, identity)
    else:
        secure_write(path, json.dumps(record, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
        _read_artifact(path, fingerprint, identity)
    return {"relative_path": f"responses/{fingerprint}.json", "fingerprint": fingerprint, "artifact_schema": RESPONSE_ARTIFACT_SCHEMA}

def read_persisted_response(cache_dir: Path, entry: dict[str, Any]) -> dict[str, Any]:
    reference = entry.get("response_artifact")
    if not isinstance(reference, dict): raise ConsultError("VERDICT_EVIDENCE_UNUSABLE", ["historical verdict has no retained response payload"])
    fingerprint = reference.get("fingerprint")
    if (not isinstance(fingerprint, str) or reference.get("artifact_schema") != RESPONSE_ARTIFACT_SCHEMA or
            reference.get("relative_path") != f"responses/{fingerprint}.json"):
        raise ConsultError("VERDICT_EVIDENCE_UNUSABLE", ["invalid response artifact reference"])
    if entry.get("response_fingerprint") != fingerprint:
        raise ConsultError("VERDICT_EVIDENCE_UNUSABLE", ["ledger response fingerprint mismatch"])
    return _read_artifact(artifact_path(cache_dir, fingerprint), fingerprint, identity_from_entry(entry))

def commit_usable_verdict(ledger: Path, cache_dir: Path, entry: dict[str, Any], response: dict[str, Any], identity: dict[str, Any], question_answer_ids: list[str]) -> dict[str, Any]:
    """Persist and verify canonical evidence before atomically appending a usable verdict."""
    reference = persist_response_evidence(cache_dir, response, identity, question_answer_ids)
    entry.update({"response_artifact": reference, "response_fingerprint": reference["fingerprint"],
                  "response_schema_version": response.get("schema_version"), "question_answer_coverage": question_answer_ids,
                  "model_response_validated": True, "validated_model_verdict": response.get("verdict"),
                  "operational_usability": True})
    # Re-read before the ledger commit: an entry is never appended as usable
    # unless a post-rename reader can verify its exact canonical payload.
    recovered = read_persisted_response(cache_dir, entry)
    if recovered.get("response") != response: raise ConsultError("VERDICT_EVIDENCE_UNUSABLE", ["canonical response changed before ledger commit"])
    append_ledger(ledger, entry)
    return entry

def acquire_lock(ledger: Path, mission: str):
    secure_dir(ledger.parent); lock = ledger.parent / f".{safe_mission_id(mission)}.lock"; handle = lock.open("a+"); os.chmod(lock, 0o600); fcntl.flock(handle, fcntl.LOCK_EX); return handle

def cache_key(bundle: dict[str, Any], model: str, effort: str) -> str: return sha256({"version": VERSION, "bundle": bundle, "model": model, "effort": effort})

def base_metrics(status: str, mission: str) -> dict[str, Any]: return {"status": status, "mission_id": mission, "verdict": None, "details": [], "process_attempts": 0, "codex_exec_processes": 0, "superior_sessions": 0, "valid_verdicts": 0, "protocol_failures": 0, "replacement_attempts": 0, "cache_hits": 0, "transport_retries": 0}
def emit(payload: dict[str, Any], code: int = 0) -> int: print(json.dumps(payload, sort_keys=True)); return code

def evidence_state(cache_dir: Path, entry: dict[str, Any]) -> str:
    if entry.get("verdict") is None: return "NO_MODEL_VERDICT"
    if not entry.get("response_artifact"):
        return "HISTORICAL_VALID_VERDICT_UNUSABLE"
    try: read_persisted_response(cache_dir, entry)
    except ConsultError: return "VERDICT_EVIDENCE_UNUSABLE"
    return "VALID_ADVISORY_VERDICT"

def evidence_reason(state: str | None) -> str | None:
    return {
        "HISTORICAL_VALID_VERDICT_UNUSABLE": "response payload not retained by the historical execution",
        "VERDICT_EVIDENCE_UNUSABLE": "referenced response evidence is missing, unreadable, or corrupt",
    }.get(state)

def status_report(args: argparse.Namespace) -> dict[str, Any]:
    entries = read_ledger(Path(args.ledger), args.mission_id); cache_dir = Path(args.cache_dir).expanduser().resolve()
    processes = sum(int(e.get("process_attempts", e.get("codex_exec_processes", 0))) for e in entries); verdicts = sum(1 for e in entries if e.get("verdict") is not None and e.get("cache") != "HIT"); failures = sum(1 for e in entries if e.get("protocol_failure")); replacements = sum(1 for e in entries if e.get("replacement_for")); hits = sum(e.get("cache") == "HIT" for e in entries); turns = sum(int(e.get("observed_model_turns", e.get("model_turns_observed", 0))) for e in entries); tools = sum(int(e.get("tool_calls_observed", 0)) for e in entries); retries = sum(int(e.get("transport_retries", e.get("automatic_transport_retries", 0))) for e in entries); last = entries[-1] if entries else {}; states = [evidence_state(cache_dir, entry) for entry in entries]
    usable = sum(state == "VALID_ADVISORY_VERDICT" for state in states); unusable = sum(state in {"HISTORICAL_VALID_VERDICT_UNUSABLE", "VERDICT_EVIDENCE_UNUSABLE"} for state in states); last_state = states[-1] if states else None
    return {"status": "STATUS", "mission_id": args.mission_id, "version": VERSION, "process_attempts": processes, "valid_verdicts": verdicts, "usable_valid_verdicts": usable, "unusable_valid_verdicts": unusable, "protocol_failures": failures, "replacement_attempts": replacements, "cache_hits": hits, "transport_retries": retries, "observed_model_turns": turns, "codex_exec_processes": processes, "model_turns_observed": turns, "backend_requests_observed": None, "tool_calls_observed": tools, "follow_up_turns": 0, "resume_operations": 0, "repair_executions": 0, "sessions_used": processes, "soft_sessions_remaining": max(0, args.soft_budget - verdicts), "hard_sessions_remaining": max(0, args.hard_budget - verdicts), "last_verdict": last.get("verdict") if last_state == "VALID_ADVISORY_VERDICT" else None, "last_validated_model_verdict": last.get("validated_model_verdict", last.get("verdict")), "last_operational_status": last_state, "last_operational_reason": evidence_reason(last_state), "exit_statuses": sorted({e.get("detailed_status") for e in entries if e.get("detailed_status")})}

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    state = Path.home() / ".local" / "state" / "codex-senior-consult"; p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=sorted(MODES)); p.add_argument("--mission-id", required=True); p.add_argument("--bundle"); p.add_argument("--model", default="gpt-5.6-sol"); p.add_argument("--effort", choices=sorted(EFFORTS), default="low"); p.add_argument("--critical", action="append", choices=sorted(MEDIUM_TRIGGERS), default=[]); p.add_argument("--replacement-for"); p.add_argument("--legacy-response-v1", action="store_true"); p.add_argument("--historical-response-v2", action="store_true"); p.add_argument("--status", action="store_true"); p.add_argument("--workspace-read"); p.add_argument("--workspace-read-justification"); p.add_argument("--no-cache", action="store_true"); p.add_argument("--refresh", action="store_true"); p.add_argument("--timeout", type=int, default=180); p.add_argument("--transport-retries", type=int, choices=(0, 1), default=0); p.add_argument("--dangerous-yolo", action="store_true"); p.add_argument("--ledger", default=str(state / "ledger.jsonl")); p.add_argument("--cache-dir", default=str(state / "cache")); p.add_argument("--max-bundle-bytes", type=int, default=131072); p.add_argument("--soft-budget", type=int, default=2); p.add_argument("--hard-budget", type=int, default=3); p.add_argument("--process-hard-budget", type=int); p.add_argument("--replacement-budget", type=int, default=1); return p.parse_args(argv)

def construction_parser(command: str) -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog=f"codex_senior_consult.py {command}")
    p.add_argument("--mission-id", required=True); p.add_argument("--mode", required=True, choices=sorted(MODES))
    if command == "build-bundle":
        p.add_argument("--repository", default="."); p.add_argument("--output"); p.add_argument("--overwrite", action="store_true")
    else:
        p.add_argument("--bundle", required=True); p.add_argument("--normalized-output"); p.add_argument("--overwrite", action="store_true")
        p.add_argument("--max-bundle-bytes", type=int, default=131072)
    return p

def command_help() -> str:
    return "commands: build-bundle, preflight, consult, status"

def build_prompt(bundle: dict[str, Any], model: str, effort: str) -> str:
    mode = bundle["mode"]; return ("You are a bounded, single-pass senior consultant.\nUse only this supplied bundle. Do not use tools, inspect workspace, read files, execute commands, invoke MCP. Do not invoke subagents or other models. Do not ask follow-ups, resume, repair, or request another turn. Return exactly one final JSON object matching the mode contract. The wrapper owns identity metadata; do not reproduce it. Address every question by stable question id. A consultation execution may terminate fail-closed while the mission owner continues locally. For merge-gate: blocking_findings are only facts preventing acceptance; required_actions are only work required before acceptance; non_blocking_observations are optional notes compatible with acceptance; residual_risks are explicitly accepted risks requiring no pre-merge action. Any real blocker or required pre-merge action makes accept invalid.\nMode: " + mode + "\nTarget model: " + model + "\nReasoning effort: " + effort + "\nBundle:\n" + json.dumps(bundle, sort_keys=True, ensure_ascii=False))

def make_entry(args: argparse.Namespace, execution_id: str, identity: dict[str, Any], status: str, detailed: str, *, processes: int, turns: int, tools: int, verdict: str | None, replacement_for: str | None, cache: str = "MISS", protocol_failure: bool = False, retries: int = 0, transport: dict[str, Any] | None = None, model_response_validated: bool = False, validated_model_verdict: str | None = None) -> dict[str, Any]:
    return {"execution_id": execution_id, "timestamp": utc_now(), "mission_id": args.mission_id, "mode": args.mode, "model": args.model, "reasoning_effort": getattr(args, "effective_effort", args.effort), "snapshot": identity["snapshot"], "normalized_bundle_fingerprint": identity["bundle"], "replacement_for": replacement_for, "replacement_authorized": bool(replacement_for), "cache": cache, "process_attempts": processes, "valid_verdicts": int(verdict is not None), "protocol_failure": bool(protocol_failure), "protocol_failures": int(protocol_failure), "replacement_attempts": int(bool(replacement_for)), "observed_model_turns": turns, "codex_exec_processes": processes, "model_turns_observed": turns, "tool_calls_observed": tools, "transport_retries": retries, "automatic_repair_calls": 0, "resume_operations": 0, "follow_up_turns": 0, "detailed_status": detailed, "status": status, "verdict": verdict, "model_response_validated": model_response_validated, "validated_model_verdict": validated_model_verdict, "operational_usability": bool(verdict is not None), "secret_exposure": False, **(transport or {})}

def main(argv: list[str] | None = None) -> int:
    try:
        raw_argv = list(sys.argv[1:] if argv is None else argv)
        if not raw_argv or raw_argv == ["--help"]:
            print(command_help()); return 0
        translated = translate_legacy_argv(raw_argv); command = translated[0]
        if command == "build-bundle":
            build_args = construction_parser(command).parse_args(translated[1:])
            bundle = build_bundle_skeleton(build_args.mission_id, build_args.mode, Path(build_args.repository))
            if build_args.output:
                target = Path(build_args.output)
                if target.exists() and not build_args.overwrite: return emit({**base_metrics("OUTPUT_EXISTS", build_args.mission_id), "details": ["use --overwrite to replace output"]}, 2)
                secure_write(target, json.dumps(bundle, sort_keys=True, indent=2) + "\n")
                return emit({"status": "BUNDLE_BUILT", "mission_id": build_args.mission_id, "output": str(target), "model_processes_consumed": 0})
            return emit({"status": "BUNDLE_BUILT", "mission_id": build_args.mission_id, "bundle": bundle, "model_processes_consumed": 0})
        if command == "preflight":
            pre_args = construction_parser(command).parse_args(translated[1:]); _, raw = read_regular_input(pre_args.bundle, pre_args.max_bundle_bytes)
            try: source = json.loads(raw)
            except json.JSONDecodeError as exc: return emit({"status": "PREFLIGHT_INVALID", "valid": False, "diagnostics": [_diagnostic("BUNDLE_JSON_INVALID", "/", "invalid", exc.msg, "JSON object", "Correct the JSON syntax.")], "model_processes_consumed": 0}, 2)
            result = preflight_bundle(source, mission_id=pre_args.mission_id, mode=pre_args.mode)
            if result.get("valid") and pre_args.normalized_output:
                target = Path(pre_args.normalized_output)
                if target.exists() and not pre_args.overwrite: return emit({**result, "status": "OUTPUT_EXISTS"}, 2)
                secure_write(target, json.dumps(result["payload"], sort_keys=True, indent=2) + "\n")
            return emit({k: v for k, v in result.items() if k != "payload"}, 0 if result.get("valid") else 2)
        legacy_argv = translated[1:]
        if command == "status" and "--status" not in legacy_argv: legacy_argv = [*legacy_argv, "--status"]
        args = parse_args(legacy_argv); safe_mission_id(args.mission_id)
        if args.status: return emit(status_report(args))
        if os.environ.get("CODEX_SENIOR_CONSULT_ACTIVE") == "1": return emit(base_metrics("RECURSIVE_ESCALATION_BLOCKED", args.mission_id), 2)
        if not args.bundle or not args.mode: return emit(base_metrics("BUNDLE_INCOMPLETE", args.mission_id), 2)
        _, raw = read_regular_input(args.bundle, args.max_bundle_bytes)
        try: source = json.loads(raw)
        except json.JSONDecodeError as exc: return emit({**base_metrics("BUNDLE_INCOMPLETE", args.mission_id), "details": [f"invalid JSON: {exc.msg}"]}, 2)
        local_preflight = preflight_bundle(source, mission_id=args.mission_id, mode=args.mode)
        if not local_preflight["valid"]:
            codes = {d["code"] for d in local_preflight["diagnostics"]}
            status = "SECRET_DETECTED" if "SECRET_DETECTED" in codes else "PRIVATE_PATH_DETECTED" if "PRIVATE_PATH_DETECTED" in codes else "BUNDLE_INCOMPLETE"
            return emit({**base_metrics(status, args.mission_id), "diagnostics": local_preflight["diagnostics"], "details": [d["reason"] for d in local_preflight["diagnostics"]], "model_processes_consumed": 0}, 2)
        bundle = local_preflight["payload"]; args.effort_triggers = sorted(set(args.critical)); args.effective_effort = "medium" if args.effort in {"low", "medium"} and args.effort_triggers else args.effort; args.response_schema_version = bundle["requested_output"].get("schema_version"); args.allow_legacy = args.legacy_response_v1 or args.response_schema_version == LEGACY_RESPONSE_SCHEMA; args.allow_historical = args.historical_response_v2 or args.response_schema_version == RESPONSE_SCHEMA
        if not bundle["escalation"].get("justified", True): return emit({**base_metrics("ESCALATION_NOT_JUSTIFIED", args.mission_id), "superior_sessions": 0, "codex_exec_processes": 0}, 0)
        if args.workspace_read: return emit({**base_metrics("WORKSPACE_READ_UNSUPPORTED", args.mission_id), "details": ["workspace access cannot preserve zero tools"]}, 3)
        if args.dangerous_yolo: return emit({**base_metrics("DANGEROUS_YOLO_DISABLED", args.mission_id), "details": ["dangerous bypass is disabled"]}, 3)
        ledger = Path(args.ledger).expanduser().resolve(); cache_dir = Path(args.cache_dir).expanduser().resolve(); secure_dir(cache_dir); lock = acquire_lock(ledger, args.mission_id)
        try:
            entries = read_ledger(ledger, args.mission_id); identity = {"snapshot": sha256(bundle["snapshot"]), "bundle": bundle["normalized_bundle_fingerprint"], "mode": args.mode, "model": args.model, "effort": args.effective_effort}
            replacement_for = args.replacement_for
            if replacement_for:
                prior = next((e for e in entries if e.get("execution_id") == replacement_for), None)
                if not prior: return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["referenced execution does not exist"]}, 4)
                if prior.get("verdict") is not None or prior.get("model_response_validated"):
                    return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["validated model verdict cannot be replaced"]}, 4)
                if prior.get("replacement_for"): return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["replacement of a replacement is forbidden"]}, 4)
                if sum(1 for e in entries if e.get("replacement_for")) >= args.replacement_budget or any(e.get("replacement_for") == replacement_for for e in entries): return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["replacement allowance exhausted"]}, 4)
                for key in ("mode", "model", "reasoning_effort"):
                    if prior.get(key) != (args.mode if key == "mode" else args.model if key == "model" else args.effective_effort): return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": [f"{key} differs"]}, 4)
                if prior.get("snapshot") != identity["snapshot"] or prior.get("normalized_bundle_fingerprint") != identity["bundle"]: return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["snapshot or normalized bundle differs"]}, 4)
            key = cache_key(bundle, args.model, args.effective_effort); cache_path = cache_dir / f"{key}.json"
            if not replacement_for and not args.no_cache and not args.refresh and os.path.lexists(cache_path):
                try:
                    info = cache_path.lstat(); cached = json.loads(cache_path.read_text())
                    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or cached.get("schema_version") != args.response_schema_version or cached.get("identity") != identity: raise ValueError
                    errors = validate_response(cached.get("response"), args.mission_id, args.mode, args.model, args.effective_effort, bundle["questions"], bundle["snapshot"]["repository_head"], allow_legacy=args.allow_legacy, allow_historical=args.allow_historical)
                    if errors: raise ValueError
                except (OSError, ValueError, json.JSONDecodeError, AttributeError, TypeError): return emit({**base_metrics("CACHE_INVALID", args.mission_id), "details": ["cache entry failed schema or identity validation"]}, 2)
                eid = str(uuid.uuid4()); cached_response = cached["response"]
                entry = make_entry(args, eid, identity, "CACHE_HIT", "CACHE_HIT", processes=0, turns=0, tools=0, verdict=cached_response.get("verdict"), replacement_for=None, cache="HIT")
                try:
                    commit_usable_verdict(ledger, cache_dir, entry, cached_response, identity, question_ids(bundle))
                except (ConsultError, OSError, ValueError):
                    return emit({**base_metrics("NO_USABLE_VERDICT", args.mission_id), "detailed_status": "VERDICT_PERSISTENCE_FAILURE", "execution_id": eid, "model_response_validated": True, "validated_model_verdict": cached_response.get("verdict"), "details": ["validated cached response could not be retained"], "cache_hits": 1}, 2)
                return emit({"status": "CACHE_HIT", "detailed_status": "VALID_ADVISORY_VERDICT", "mission_id": args.mission_id, "version": VERSION, "response": cached_response, "execution_id": eid, "replacement_for": None, "process_attempts": 0, "codex_exec_processes": 0, "superior_sessions": 0, "valid_verdicts": 0, "cache_hits": 1, "verdict": cached_response.get("verdict"), "response_fingerprint": entry["response_fingerprint"]})
            process_budget = args.process_hard_budget if args.process_hard_budget is not None else (args.hard_budget if args.hard_budget != 3 else 4); used = sum(int(e.get("process_attempts", 0)) for e in entries); planned = 1 + args.transport_retries
            if used + planned > process_budget or sum(1 for e in entries if e.get("verdict") is not None) >= args.hard_budget and not replacement_for: return emit({**base_metrics("MISSION_BUDGET_EXCEEDED", args.mission_id), "process_attempts": used, "valid_verdicts": sum(1 for e in entries if e.get("verdict") is not None)}, 4)
            prompt = build_prompt(bundle, args.model, args.effective_effort); total_processes = turns = tools = retries = 0; final = None; detailed = "TRANSPORT_ERROR"; timeout = False; diagnostics: list[str] = []; transport: dict[str, Any] = {}
            with tempfile.TemporaryDirectory(prefix="codex-senior-work-") as work, tempfile.TemporaryDirectory(prefix="codex-senior-control-") as ctl:
                schema_file = Path(ctl) / "schema.json"; output_file = Path(ctl) / "response.json"; secure_write(schema_file, json.dumps(response_schema(mode=args.mode, schema_version=args.response_schema_version)))
                command = ["codex", "--ask-for-approval", "never", "exec", "--ephemeral", "-C", work, "--sandbox", "read-only", "--json", "--output-schema", str(schema_file), "-o", str(output_file), "--ignore-user-config", "--ignore-rules", "-c", "shell_environment_policy.inherit=none", "--skip-git-repo-check", "-m", args.model, "-c", f'model_reasoning_effort="{args.effective_effort}"', "-"]
                for attempt in range(1 + args.transport_retries):
                    total_processes += 1; rc, stdout, stderr, timeout = run_process(command, prompt, args.timeout, Path(work)); t, tool_count, terminal, diagnostics = count_events(stdout); turns += t; tools += tool_count
                    if timeout:
                        detailed = "TIMEOUT"; transport = parse_transport_evidence(stdout, stderr, rc, True); break
                    if rc != 0:
                        detailed = "TRANSPORT_ERROR"
                        transport = parse_transport_evidence(stdout, stderr, rc, False)
                        retries += int(attempt < args.transport_retries)
                        continue
                    if diagnostics or tools or turns != 1 or not terminal: detailed = "SINGLE_PASS_CONTRACT_VIOLATION"; break
                    try: final = json.loads(output_file.read_text())
                    except (OSError, json.JSONDecodeError): detailed = "MALFORMED_SUPERIOR_RESPONSE"; break
                    errors = validate_response(final, args.mission_id, args.mode, args.model, args.effective_effort, bundle["questions"], bundle["snapshot"]["repository_head"], allow_legacy=args.allow_legacy, allow_historical=args.allow_historical)
                    if errors: detailed = "MALFORMED_SUPERIOR_RESPONSE"; diagnostics = errors[:8]; final = None; break
                    detailed = "VALID_ADVISORY_VERDICT"; break
            eid = str(uuid.uuid4()); verdict = final.get("verdict") if final else None
            if final:
                entry = make_entry(args, eid, identity, "COMPLETED", "VALID_ADVISORY_VERDICT", processes=total_processes, turns=turns, tools=tools, verdict=verdict, replacement_for=replacement_for, retries=retries, transport=transport)
                try:
                    commit_usable_verdict(ledger, cache_dir, entry, final, identity, question_ids(bundle))
                except (ConsultError, OSError, ValueError):
                    # A semantically valid model response that cannot be durably
                    # retained is not an actionable advisory verdict.  Do not leak
                    # its payload or convert it into a retry/replacement signal.
                    failed = make_entry(args, eid, identity, "NO_USABLE_VERDICT", "VERDICT_PERSISTENCE_FAILURE", processes=total_processes, turns=turns, tools=tools, verdict=None, replacement_for=replacement_for, retries=retries, transport=transport, model_response_validated=True, validated_model_verdict=verdict)
                    try: append_ledger(ledger, failed)
                    except (ConsultError, OSError, ValueError): pass
                    out = {"status": "NO_USABLE_VERDICT", "detailed_status": "VERDICT_PERSISTENCE_FAILURE", "mission_id": args.mission_id, "version": VERSION, "execution_id": eid, "replacement_for": replacement_for, "response": None, "verdict": None, "model_response_validated": True, "validated_model_verdict": verdict, "operational_usability": False, "process_attempts": total_processes, "valid_verdicts": 0, "protocol_failures": 0, "replacement_attempts": int(bool(replacement_for)), "cache_hits": 0, "transport_retries": retries, "observed_model_turns": turns, "codex_exec_processes": total_processes, "superior_sessions": total_processes, "question_count": len(bundle["questions"]), "reasoning_effort": args.effective_effort, "effort_triggers": args.effort_triggers, "backend_requests_observed": None, "model_turns_observed": turns, "tool_calls_observed": tools, "follow_up_turns": 0, "resume_operations": 0, "repair_executions": 0, "details": ["validated response could not be durably retained"], **transport}
                    return emit(out, 2)
                if not args.no_cache:
                    try: secure_write(cache_path, json.dumps({"schema_version": args.response_schema_version, "identity": identity, "response": final}))
                    except (ConsultError, OSError): pass
                out = {"status": "COMPLETED", "detailed_status": "VALID_ADVISORY_VERDICT", "mission_id": args.mission_id, "version": VERSION, "execution_id": eid, "replacement_for": replacement_for, "response": final, "verdict": verdict, "response_fingerprint": entry["response_fingerprint"], "response_artifact": entry["response_artifact"], "operational_usability": True, "process_attempts": total_processes, "valid_verdicts": 1, "protocol_failures": 0, "replacement_attempts": int(bool(replacement_for)), "cache_hits": 0, "transport_retries": retries, "observed_model_turns": turns, "codex_exec_processes": total_processes, "superior_sessions": total_processes, "question_count": len(bundle["questions"]), "reasoning_effort": args.effective_effort, "effort_triggers": args.effort_triggers, "backend_requests_observed": None, "model_turns_observed": turns, "tool_calls_observed": tools, "follow_up_turns": 0, "resume_operations": 0, "repair_executions": 0, "details": diagnostics, **transport}
                return emit(out)
            status = "NO_VERDICT_PROTOCOL_FAILURE"; entry = make_entry(args, eid, identity, status, detailed, processes=total_processes, turns=turns, tools=tools, verdict=None, replacement_for=replacement_for, retries=retries, protocol_failure=True, transport=transport); append_ledger(ledger, entry)
            out = {"status": status, "detailed_status": detailed, "mission_id": args.mission_id, "version": VERSION, "execution_id": eid, "replacement_for": replacement_for, "response": None, "verdict": None, "process_attempts": total_processes, "valid_verdicts": 0, "protocol_failures": 1, "replacement_attempts": int(bool(replacement_for)), "cache_hits": 0, "transport_retries": retries, "observed_model_turns": turns, "codex_exec_processes": total_processes, "superior_sessions": total_processes, "question_count": len(bundle["questions"]), "reasoning_effort": args.effective_effort, "effort_triggers": args.effort_triggers, "backend_requests_observed": None, "model_turns_observed": turns, "tool_calls_observed": tools, "follow_up_turns": 0, "resume_operations": 0, "repair_executions": 0, "details": diagnostics, **transport}
            return emit(out, 2)
        finally: fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
    except ConsultError as exc: return emit({**base_metrics(exc.code, args.mission_id if 'args' in locals() else "unknown"), "details": exc.details}, 2)
    except (OSError, subprocess.SubprocessError) as exc: return emit({"status": "TRANSPORT_ERROR", "details": [str(exc)[:300]], "verdict": None}, 2)

if __name__ == "__main__": raise SystemExit(main())
