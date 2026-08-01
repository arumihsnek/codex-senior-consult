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

VERSION = "2.0.0"
BUNDLE_SCHEMA = "codex-senior-consult/v1"
RESPONSE_SCHEMA = "codex-senior-consult-response/v2"
LEGACY_RESPONSE_SCHEMA = "codex-senior-consult-response/v1"
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

class ConsultError(Exception):
    def __init__(self, code: str, details: list[str] | None = None):
        super().__init__(code); self.code = code; self.details = details or []

def utc_now() -> str: return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
def canonical(value: Any) -> bytes: return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
def sha256(value: Any) -> str: return hashlib.sha256(canonical(value)).hexdigest()
def safe_mission_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value or ""): raise ConsultError("INVALID_MISSION_ID", ["mission_id must be path-safe and 1-128 characters"])
    return value

def secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700); info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode): raise ConsultError("INVALID_STATE_PATH", ["state directory must be a real directory"])
    path.chmod(0o700)

def secure_write(path: Path, data: str) -> None:
    secure_dir(path.parent)
    if os.path.lexists(path) and stat.S_ISLNK(path.lstat().st_mode): raise ConsultError("INVALID_STATE_PATH", ["refusing symlink state file"])
    fd, name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        os.fchmod(fd, 0o600); os.write(fd, data.encode()); os.fsync(fd); os.close(fd); fd = -1; os.replace(name, path); path.chmod(0o600)
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

def secret_locations(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if _credential_like(str(key), child): hits.append(child_path)
            hits.extend(secret_locations(child, child_path))
    elif isinstance(value, list):
        for i, child in enumerate(value): hits.extend(secret_locations(child, f"{path}[{i}]"))
    elif isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_PATTERNS): hits.append(path)
    return sorted(set(hits))

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
    if not isinstance(requested, dict) or requested.get("schema_version") not in {RESPONSE_SCHEMA, LEGACY_RESPONSE_SCHEMA}: missing.append("requested_output.schema_version must be v2 or explicit legacy v1")
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

MODE_FIELDS: dict[str, tuple[str, ...]] = {
    "merge-gate": ("verdict", "safe_to_merge", "blocking_findings", "required_actions", "residual_risks", "summary"),
    "blocker-analysis": ("verdict", "ranked_causes", "continuation_paths", "recommended_path", "cheapest_discriminating_experiment", "stop_conditions", "next_safe_step"),
    "replan": ("verdict", "invalidated_assumptions", "plan_delta", "closed_phases_preserved", "new_stop_conditions", "next_safe_step"),
    "integrated-review": ("verdict", "summary", "findings", "decision", "next_safe_step"),
    "plan": ("verdict", "summary", "plan", "risks", "next_safe_step"),
    "plan-review": ("verdict", "summary", "blocking_findings", "required_actions", "next_safe_step"),
    "risk-audit": ("verdict", "risks", "controls", "residual_risks", "next_safe_step"),
    "final-review": ("verdict", "claim_classifications", "summary", "next_safe_step"),
}

def response_schema(mission_id: str | None = None, mode: str = "integrated-review", model: str | None = None, effort: str | None = None, execution: int | None = None, snapshot: str | None = None, schema_version: str = RESPONSE_SCHEMA) -> dict[str, Any]:
    fields = MODE_FIELDS.get(mode, MODE_FIELDS["integrated-review"])
    properties = {"schema_version": {"type": "string", "const": schema_version}, **{name: {"type": "object" if name in {"decision", "plan"} else "array" if name.endswith("s") or name in {"findings", "risks", "controls", "blocking_findings", "required_actions", "residual_risks", "claim_classifications", "invalidated_assumptions", "plan_delta", "closed_phases_preserved", "new_stop_conditions", "ranked_causes", "continuation_paths", "stop_conditions"} else "boolean" if name == "safe_to_merge" else "string"} for name in fields}}
    if mission_id is not None:
        properties.update({"mission_id": {"type": "string", "const": mission_id}, "mode": {"type": "string", "const": mode}, "model": {"type": "string", "const": model}, "reasoning_effort": {"type": "string", "const": effort}, "snapshot": {"type": "string", "const": snapshot}})
        properties["schema_version"] = {"type": "string", "const": schema_version}
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object", "additionalProperties": False, "required": ["schema_version", *fields], "properties": properties}

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

def validate_response(value: Any, mission_id: str, mode: str, model: str, effort: str, questions: list[Any], snapshot: str, *, allow_legacy: bool = True) -> list[str]:
    if isinstance(value, dict) and value.get("schema_version") == LEGACY_RESPONSE_SCHEMA:
        return _legacy_errors(value, mission_id, mode, model, effort, questions, snapshot) if allow_legacy else ["legacy v1 response requires --legacy-response-v1"]
    if not isinstance(value, dict): return ["response must be an object"]
    fields = MODE_FIELDS.get(mode, MODE_FIELDS["integrated-review"]); errors = []
    if value.get("schema_version") != RESPONSE_SCHEMA: errors.append("schema_version must equal v2")
    if set(value) - {"schema_version", *fields}: errors.append("additional property")
    for field in fields:
        if field not in value: errors.append(f"missing {field}")
        elif field == "safe_to_merge" and not isinstance(value[field], bool): errors.append("safe_to_merge must be boolean")
        elif field != "safe_to_merge" and not isinstance(value[field], str if field in {"verdict", "recommended_path", "cheapest_discriminating_experiment", "next_safe_step", "summary"} else list): errors.append(f"{field} has invalid type")
    if mode == "merge-gate":
        if value.get("verdict") not in {"accept", "changes_required", "blocked"}: errors.append("invalid verdict")
        if value.get("verdict") == "accept" and (value.get("safe_to_merge") is not True or value.get("blocking_findings") != [] or value.get("required_actions") != []): errors.append("merge-gate accept is inconsistent")
        if value.get("verdict") != "accept" and value.get("safe_to_merge") is not False: errors.append("merge-gate non-accept must be unsafe")
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
    keep = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR"}; env = {k: v for k, v in os.environ.items() if k in keep}; env["CODEX_SENIOR_CONSULT_ACTIVE"] = "1"; return env

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
    with with_path.open("a", encoding="utf-8") as f:
        os.chmod(with_path, 0o600); fcntl.flock(f, fcntl.LOCK_EX); f.write(json.dumps(entry, sort_keys=True) + "\n"); f.flush(); os.fsync(f.fileno()); fcntl.flock(f, fcntl.LOCK_UN)

def acquire_lock(ledger: Path, mission: str):
    secure_dir(ledger.parent); lock = ledger.parent / f".{safe_mission_id(mission)}.lock"; handle = lock.open("a+"); os.chmod(lock, 0o600); fcntl.flock(handle, fcntl.LOCK_EX); return handle

def cache_key(bundle: dict[str, Any], model: str, effort: str) -> str: return sha256({"version": VERSION, "bundle": bundle, "model": model, "effort": effort})

def base_metrics(status: str, mission: str) -> dict[str, Any]: return {"status": status, "mission_id": mission, "verdict": None, "details": [], "process_attempts": 0, "codex_exec_processes": 0, "superior_sessions": 0, "valid_verdicts": 0, "protocol_failures": 0, "replacement_attempts": 0, "cache_hits": 0, "transport_retries": 0}
def emit(payload: dict[str, Any], code: int = 0) -> int: print(json.dumps(payload, sort_keys=True)); return code

def status_report(args: argparse.Namespace) -> dict[str, Any]:
    entries = read_ledger(Path(args.ledger), args.mission_id); processes = sum(int(e.get("process_attempts", e.get("codex_exec_processes", 0))) for e in entries); verdicts = sum(1 for e in entries if e.get("verdict") is not None and e.get("cache") != "HIT"); failures = sum(1 for e in entries if e.get("protocol_failure")); replacements = sum(1 for e in entries if e.get("replacement_for")); hits = sum(e.get("cache") == "HIT" for e in entries); turns = sum(int(e.get("observed_model_turns", e.get("model_turns_observed", 0))) for e in entries); tools = sum(int(e.get("tool_calls_observed", 0)) for e in entries); retries = sum(int(e.get("transport_retries", e.get("automatic_transport_retries", 0))) for e in entries); last = entries[-1] if entries else {}
    return {"status": "STATUS", "mission_id": args.mission_id, "version": VERSION, "process_attempts": processes, "valid_verdicts": verdicts, "protocol_failures": failures, "replacement_attempts": replacements, "cache_hits": hits, "transport_retries": retries, "observed_model_turns": turns, "codex_exec_processes": processes, "model_turns_observed": turns, "backend_requests_observed": None, "tool_calls_observed": tools, "follow_up_turns": 0, "resume_operations": 0, "repair_executions": 0, "sessions_used": processes, "soft_sessions_remaining": max(0, args.soft_budget - verdicts), "hard_sessions_remaining": max(0, args.hard_budget - verdicts), "last_verdict": last.get("verdict"), "exit_statuses": sorted({e.get("detailed_status") for e in entries if e.get("detailed_status")})}

def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    state = Path.home() / ".local" / "state" / "codex-senior-consult"; p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--mode", choices=sorted(MODES)); p.add_argument("--mission-id", required=True); p.add_argument("--bundle"); p.add_argument("--model", default="gpt-5.6-sol"); p.add_argument("--effort", choices=sorted(EFFORTS), default="low"); p.add_argument("--critical", action="append", choices=sorted(MEDIUM_TRIGGERS), default=[]); p.add_argument("--replacement-for"); p.add_argument("--legacy-response-v1", action="store_true"); p.add_argument("--status", action="store_true"); p.add_argument("--workspace-read"); p.add_argument("--workspace-read-justification"); p.add_argument("--no-cache", action="store_true"); p.add_argument("--refresh", action="store_true"); p.add_argument("--timeout", type=int, default=180); p.add_argument("--transport-retries", type=int, choices=(0, 1), default=0); p.add_argument("--dangerous-yolo", action="store_true"); p.add_argument("--ledger", default=str(state / "ledger.jsonl")); p.add_argument("--cache-dir", default=str(state / "cache")); p.add_argument("--max-bundle-bytes", type=int, default=131072); p.add_argument("--soft-budget", type=int, default=2); p.add_argument("--hard-budget", type=int, default=3); p.add_argument("--process-hard-budget", type=int); p.add_argument("--replacement-budget", type=int, default=1); return p.parse_args(argv)

def build_prompt(bundle: dict[str, Any], model: str, effort: str) -> str:
    mode = bundle["mode"]; return ("You are a bounded, single-pass senior consultant.\nUse only this supplied bundle. Do not use tools, inspect workspace, read files, execute commands, invoke MCP. Do not invoke subagents or other models. Do not ask follow-ups, resume, repair, or request another turn. Return exactly one final JSON object matching the mode contract. The wrapper owns identity metadata; do not reproduce it. Address every question by stable question id. A consultation execution may terminate fail-closed while the mission owner continues locally.\nMode: " + mode + "\nTarget model: " + model + "\nReasoning effort: " + effort + "\nBundle:\n" + json.dumps(bundle, sort_keys=True, ensure_ascii=False))

def make_entry(args: argparse.Namespace, execution_id: str, identity: dict[str, Any], status: str, detailed: str, *, processes: int, turns: int, tools: int, verdict: str | None, replacement_for: str | None, cache: str = "MISS", protocol_failure: bool = False, retries: int = 0) -> dict[str, Any]:
    return {"execution_id": execution_id, "timestamp": utc_now(), "mission_id": args.mission_id, "mode": args.mode, "model": args.model, "reasoning_effort": getattr(args, "effective_effort", args.effort), "snapshot": identity["snapshot"], "normalized_bundle_fingerprint": identity["bundle"], "replacement_for": replacement_for, "replacement_authorized": bool(replacement_for), "cache": cache, "process_attempts": processes, "valid_verdicts": int(verdict is not None), "protocol_failure": bool(protocol_failure), "protocol_failures": int(protocol_failure), "replacement_attempts": int(bool(replacement_for)), "observed_model_turns": turns, "codex_exec_processes": processes, "model_turns_observed": turns, "tool_calls_observed": tools, "transport_retries": retries, "automatic_repair_calls": 0, "resume_operations": 0, "follow_up_turns": 0, "detailed_status": detailed, "status": status, "verdict": verdict, "secret_exposure": False}

def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv); safe_mission_id(args.mission_id)
        if args.status: return emit(status_report(args))
        if os.environ.get("CODEX_SENIOR_CONSULT_ACTIVE") == "1": return emit(base_metrics("RECURSIVE_ESCALATION_BLOCKED", args.mission_id), 2)
        if not args.bundle or not args.mode: return emit(base_metrics("BUNDLE_INCOMPLETE", args.mission_id), 2)
        _, raw = read_regular_input(args.bundle, args.max_bundle_bytes)
        try: source = json.loads(raw)
        except json.JSONDecodeError as exc: return emit({**base_metrics("BUNDLE_INCOMPLETE", args.mission_id), "details": [f"invalid JSON: {exc.msg}"]}, 2)
        bundle = validate_and_prepare_bundle(source, args.mission_id, args.mode); args.effort_triggers = sorted(set(args.critical)); args.effective_effort = "medium" if args.effort in {"low", "medium"} and args.effort_triggers else args.effort; args.allow_legacy = args.legacy_response_v1 or bundle["requested_output"].get("schema_version") == LEGACY_RESPONSE_SCHEMA
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
                if prior.get("verdict") is not None: return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["valid verdict cannot be replaced"]}, 4)
                if prior.get("replacement_for"): return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["replacement of a replacement is forbidden"]}, 4)
                if sum(1 for e in entries if e.get("replacement_for")) >= args.replacement_budget or any(e.get("replacement_for") == replacement_for for e in entries): return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["replacement allowance exhausted"]}, 4)
                for key in ("mode", "model", "reasoning_effort"):
                    if prior.get(key) != (args.mode if key == "mode" else args.model if key == "model" else args.effective_effort): return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": [f"{key} differs"]}, 4)
                if prior.get("snapshot") != identity["snapshot"] or prior.get("normalized_bundle_fingerprint") != identity["bundle"]: return emit({**base_metrics("REPLACEMENT_NOT_AUTHORIZED", args.mission_id), "details": ["snapshot or normalized bundle differs"]}, 4)
            key = cache_key(bundle, args.model, args.effective_effort); cache_path = cache_dir / f"{key}.json"
            if not replacement_for and not args.no_cache and not args.refresh and os.path.lexists(cache_path):
                try:
                    info = cache_path.lstat(); cached = json.loads(cache_path.read_text())
                    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode) or cached.get("schema_version") != RESPONSE_SCHEMA or cached.get("identity") != identity: raise ValueError
                    errors = validate_response(cached.get("response"), args.mission_id, args.mode, args.model, args.effective_effort, bundle["questions"], bundle["snapshot"]["repository_head"], allow_legacy=args.allow_legacy)
                    if errors: raise ValueError
                except (OSError, ValueError, json.JSONDecodeError, AttributeError, TypeError): return emit({**base_metrics("CACHE_INVALID", args.mission_id), "details": ["cache entry failed schema or identity validation"]}, 2)
                eid = str(uuid.uuid4()); append_ledger(ledger, make_entry(args, eid, identity, "CACHE_HIT", "CACHE_HIT", processes=0, turns=0, tools=0, verdict=cached["response"].get("verdict"), replacement_for=None, cache="HIT")); return emit({"status": "CACHE_HIT", "mission_id": args.mission_id, "version": VERSION, "response": cached["response"], "execution_id": eid, "replacement_for": None, "process_attempts": 0, "codex_exec_processes": 0, "superior_sessions": 0, "valid_verdicts": 0, "cache_hits": 1, "verdict": cached["response"].get("verdict")})
            process_budget = args.process_hard_budget if args.process_hard_budget is not None else (args.hard_budget if args.hard_budget != 3 else 4); used = sum(int(e.get("process_attempts", 0)) for e in entries); planned = 1 + args.transport_retries
            if used + planned > process_budget or sum(1 for e in entries if e.get("verdict") is not None) >= args.hard_budget and not replacement_for: return emit({**base_metrics("MISSION_BUDGET_EXCEEDED", args.mission_id), "process_attempts": used, "valid_verdicts": sum(1 for e in entries if e.get("verdict") is not None)}, 4)
            prompt = build_prompt(bundle, args.model, args.effective_effort); total_processes = turns = tools = retries = 0; final = None; detailed = "TRANSPORT_ERROR"; timeout = False; diagnostics: list[str] = []
            with tempfile.TemporaryDirectory(prefix="codex-senior-work-") as work, tempfile.TemporaryDirectory(prefix="codex-senior-control-") as ctl:
                schema_file = Path(ctl) / "schema.json"; output_file = Path(ctl) / "response.json"; secure_write(schema_file, json.dumps(response_schema(mode=args.mode)))
                command = ["codex", "--ask-for-approval", "never", "exec", "--ephemeral", "-C", work, "--sandbox", "read-only", "--json", "--output-schema", str(schema_file), "--output-last-message", str(output_file), "-o", str(output_file), "--ignore-user-config", "--ignore-rules", "-c", "shell_environment_policy.inherit=none", "--skip-git-repo-check", "-"]
                for attempt in range(1 + args.transport_retries):
                    total_processes += 1; rc, stdout, stderr, timeout = run_process(command, prompt, args.timeout, Path(work)); t, tool_count, terminal, diagnostics = count_events(stdout); turns += t; tools += tool_count
                    if timeout: detailed = "TIMEOUT"; break
                    if rc != 0: detailed = "TRANSPORT_ERROR"; retries += int(attempt < args.transport_retries); continue
                    if diagnostics or tools or turns != 1 or not terminal: detailed = "SINGLE_PASS_CONTRACT_VIOLATION"; break
                    try: final = json.loads(output_file.read_text())
                    except (OSError, json.JSONDecodeError): detailed = "MALFORMED_SUPERIOR_RESPONSE"; break
                    errors = validate_response(final, args.mission_id, args.mode, args.model, args.effective_effort, bundle["questions"], bundle["snapshot"]["repository_head"], allow_legacy=args.allow_legacy)
                    if errors: detailed = "MALFORMED_SUPERIOR_RESPONSE"; diagnostics = errors[:8]; final = None; break
                    detailed = "VALID_ADVISORY_VERDICT"; break
            eid = str(uuid.uuid4()); verdict = final.get("verdict") if final else None; status = "COMPLETED" if final else "NO_VERDICT_PROTOCOL_FAILURE"; entry = make_entry(args, eid, identity, status, detailed, processes=total_processes, turns=turns, tools=tools, verdict=verdict, replacement_for=replacement_for, retries=retries, protocol_failure=not bool(final)); append_ledger(ledger, entry)
            out = {"status": status, "detailed_status": detailed, "mission_id": args.mission_id, "version": VERSION, "execution_id": eid, "replacement_for": replacement_for, "response": final, "verdict": verdict, "process_attempts": total_processes, "valid_verdicts": int(bool(final)), "protocol_failures": int(not bool(final)), "replacement_attempts": int(bool(replacement_for)), "cache_hits": 0, "transport_retries": retries, "observed_model_turns": turns, "codex_exec_processes": total_processes, "superior_sessions": total_processes, "question_count": len(bundle["questions"]), "reasoning_effort": args.effective_effort, "effort_triggers": args.effort_triggers, "backend_requests_observed": None, "model_turns_observed": turns, "tool_calls_observed": tools, "follow_up_turns": 0, "resume_operations": 0, "repair_executions": 0, "details": diagnostics}
            if final and not args.no_cache: secure_write(cache_path, json.dumps({"schema_version": RESPONSE_SCHEMA, "identity": identity, "response": final}))
            return emit(out, 0 if final else 2)
        finally: fcntl.flock(lock, fcntl.LOCK_UN); lock.close()
    except ConsultError as exc: return emit({**base_metrics(exc.code, args.mission_id if 'args' in locals() else "unknown"), "details": exc.details}, 2)
    except (OSError, subprocess.SubprocessError) as exc: return emit({"status": "TRANSPORT_ERROR", "details": [str(exc)[:300]], "verdict": None}, 2)

if __name__ == "__main__": raise SystemExit(main())
