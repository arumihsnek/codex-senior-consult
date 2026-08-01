#!/usr/bin/env python3
"""Run one bounded, single-pass Codex senior consultation."""

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
from typing import Any


VERSION = "1.0.0"
BUNDLE_SCHEMA = "codex-senior-consult/v1"
RESPONSE_SCHEMA = "codex-senior-consult-response/v1"
MODES = {
    "integrated-review", "plan", "plan-review", "replan", "blocker-analysis",
    "risk-audit", "final-review", "merge-gate",
}
EFFORTS = {"low", "medium", "high", "xhigh"}
MEDIUM_TRIGGERS = {
    "cross_cutting_architecture", "security", "credentials", "process_isolation",
    "contradictory_evidence", "concurrency", "duplicate_side_effects",
    "public_contract", "destructive_migration", "alternatives_tie",
    "conceptual_plan_failure", "recovery",
}
ESCALATION_REASONS = MEDIUM_TRIGGERS | {"merge_decision", "irreversible_action"}
TOOL_ITEM_TYPES = {
    "command_execution", "mcp_tool_call", "dynamic_tool_call", "collab_tool_call",
    "web_search", "computer_tool_call", "file_search_call", "function_call", "file_change",
}
NON_TOOL_ITEM_TYPES = {"agent_message", "reasoning", "todo_list", "error"}
SECRET_PATTERNS = [
    re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b"),
    re.compile(r"\b(?:ghp|github_pat)_[A-Za-z0-9_]{20,}\b"),
    re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"),
    re.compile(r"\b(?:xox[baprs]-|ya29\.)[A-Za-z0-9._-]{16,}\b"),
    re.compile(r"(?i)\bBearer\s+[A-Za-z0-9._~+/-]{16,}={0,2}\b"),
    re.compile(r"(?i)\b(?:postgres(?:ql)?|mysql|mongodb(?:\+srv)?|redis)://[^\s:@/]+:[^\s@/]+@"),
    re.compile(r"(?i)\b(?:password|passwd|api[_-]?key|access[_-]?token|refresh[_-]?token)\b\s*[:=]\s*['\"]?[^\s'\"]{8,}"),
]
BASE_REQUIRED = {
    "schema_version", "mission_id", "mode", "objective", "decision_needed",
    "current_plan", "progress", "relevant_contracts", "observed_facts",
    "invalidated_assumptions", "candidate_decision", "alternatives", "code_excerpts",
    "diff", "tests", "runtime_evidence", "constraints", "risks_already_identified",
    "questions", "requested_output", "snapshot", "escalation",
}


class ConsultError(Exception):
    def __init__(self, code: str, details: list[str] | None = None):
        super().__init__(code)
        self.code = code
        self.details = details or []


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def canonical(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256(value: Any) -> str:
    return hashlib.sha256(canonical(value)).hexdigest()


def safe_mission_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,127}", value or ""):
        raise ConsultError("INVALID_MISSION_ID", ["mission_id must be path-safe and 1-128 characters"])
    return value


def secure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISDIR(info.st_mode):
        raise ConsultError("INVALID_STATE_PATH", ["state directory must not be a symlink or special file"])
    path.chmod(0o700)


def secure_write(path: Path, data: str) -> None:
    secure_dir(path.parent)
    if os.path.lexists(path) and stat.S_ISLNK(path.lstat().st_mode):
        raise ConsultError("INVALID_STATE_PATH", ["refusing to replace a symlinked state file"])
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temp_path = Path(temp_name)
    try:
        os.fchmod(fd, 0o600)
        payload = memoryview(data.encode())
        while payload:
            payload = payload[os.write(fd, payload):]
        os.fsync(fd)
        os.close(fd)
        fd = -1
        os.replace(temp_path, path)
    except BaseException:
        if fd >= 0:
            os.close(fd)
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise
    path.chmod(0o600)


def read_regular_input(raw_path: str, max_bytes: int) -> tuple[Path, bytes]:
    raw = Path(raw_path)
    if ".." in raw.parts:
        raise ConsultError("INVALID_BUNDLE_PATH", ["path traversal is not allowed"])
    try:
        initial = raw.lstat()
    except OSError:
        raise ConsultError("INVALID_BUNDLE_PATH", ["bundle is not an accessible regular file"])
    if stat.S_ISLNK(initial.st_mode) or not stat.S_ISREG(initial.st_mode):
        raise ConsultError("INVALID_BUNDLE_PATH", ["symlinks, FIFOs, sockets, and devices are rejected"])
    flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0)
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = -1
    try:
        fd = os.open(raw, flags)
        info = os.fstat(fd)
    except OSError:
        if fd >= 0:
            os.close(fd)
        raise ConsultError("INVALID_BUNDLE_PATH", ["bundle is not an accessible regular file"])
    if not stat.S_ISREG(info.st_mode):
        os.close(fd)
        raise ConsultError("INVALID_BUNDLE_PATH", ["symlinks, FIFOs, sockets, and devices are rejected"])
    if info.st_size > max_bytes:
        os.close(fd)
        raise ConsultError("BUNDLE_TOO_LARGE", [f"bundle exceeds {max_bytes} bytes"])
    try:
        chunks: list[bytes] = []
        remaining = max_bytes + 1
        while remaining:
            chunk = os.read(fd, remaining)
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        data = b"".join(chunks)
    finally:
        os.close(fd)
    if len(data) > max_bytes:
        raise ConsultError("BUNDLE_TOO_LARGE", [f"bundle exceeds {max_bytes} bytes"])
    return raw.resolve(), data


def secret_locations(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = f"{path}.{key}"
            if re.search(r"(?i)(password|passwd|secret|api.?key|access.?token|refresh.?token|private.?key|auth)", str(key)):
                if child not in (None, "", [], {}):
                    hits.append(key_path)
            hits.extend(secret_locations(child, key_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            hits.extend(secret_locations(child, f"{path}[{idx}]"))
    elif isinstance(value, str) and any(pattern.search(value) for pattern in SECRET_PATTERNS):
        hits.append(path)
    return sorted(set(hits))


def private_path_locations(value: Any, path: str = "$") -> list[str]:
    hits: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            key_path = f"{path}.{key}"
            if str(key).casefold() in {"path", "file", "filename"} and isinstance(child, str):
                candidate = Path(child)
                if candidate.is_absolute() or ".." in candidate.parts or child.startswith("~"):
                    hits.append(key_path)
            hits.extend(private_path_locations(child, key_path))
    elif isinstance(value, list):
        for idx, child in enumerate(value):
            hits.extend(private_path_locations(child, f"{path}[{idx}]"))
    return sorted(set(hits))


def validate_and_prepare_bundle(bundle: Any, mission_id: str, mode: str) -> dict[str, Any]:
    missing: list[str] = []
    if not isinstance(bundle, dict):
        raise ConsultError("BUNDLE_INCOMPLETE", ["bundle must be a JSON object"])
    for key in sorted(BASE_REQUIRED - set(bundle)):
        missing.append(f"missing field: {key}")
    if bundle.get("schema_version") != BUNDLE_SCHEMA:
        missing.append(f"schema_version must be {BUNDLE_SCHEMA}")
    if bundle.get("mission_id") != mission_id:
        missing.append("bundle mission_id must match --mission-id")
    if bundle.get("mode") != mode or mode not in MODES:
        missing.append("bundle mode must match a supported --mode")
    for key in ("objective", "decision_needed"):
        if not isinstance(bundle.get(key), str) or not bundle.get(key, "").strip():
            missing.append(f"{key} must be a non-empty string")
    for key in ("current_plan", "progress", "candidate_decision"):
        if not isinstance(bundle.get(key), dict) or not bundle.get(key):
            missing.append(f"{key} must be a non-empty object")
    if not isinstance(bundle.get("alternatives"), list) or not bundle.get("alternatives"):
        missing.append("alternatives must be a non-empty list")
    if (not isinstance(bundle.get("constraints"), list) or not bundle.get("constraints") or
            not all(isinstance(item, str) and item.strip() for item in bundle.get("constraints", []))):
        missing.append("constraints must be a non-empty string list")
    questions = bundle.get("questions")
    if not isinstance(questions, list) or not any(isinstance(q, str) and q.strip() for q in questions or []):
        missing.append("questions must contain concrete questions")
    requested = bundle.get("requested_output")
    if not isinstance(requested, dict) or requested.get("schema_version") != RESPONSE_SCHEMA:
        missing.append(f"requested_output.schema_version must be {RESPONSE_SCHEMA}")
    snapshot = bundle.get("snapshot")
    snapshot_keys = {"repository_head", "working_tree_fingerprint", "plan_fingerprint", "checkpoint_fingerprint"}
    if not isinstance(snapshot, dict) or not snapshot_keys.issubset(snapshot):
        missing.append("snapshot must identify HEAD, working tree, plan, and checkpoint")
    elif (not re.fullmatch(r"[0-9a-f]{40,64}", snapshot["repository_head"]) or
          any(not re.fullmatch(r"[0-9a-f]{64}", snapshot[k])
              for k in snapshot_keys - {"repository_head"})):
        missing.append("snapshot must use a 40-64 hex HEAD and 64-hex fingerprints")
    evidence_fields = ("relevant_contracts", "observed_facts", "code_excerpts", "tests", "runtime_evidence")
    if not any(bundle.get(key) for key in evidence_fields):
        missing.append("at least one relevant evidence field must be non-empty")
    for key in ("relevant_contracts", "observed_facts", "invalidated_assumptions",
                "code_excerpts", "tests", "runtime_evidence", "risks_already_identified"):
        if not isinstance(bundle.get(key), list):
            missing.append(f"{key} must be an array")
    escalation = bundle.get("escalation")
    if not isinstance(escalation, dict):
        missing.append("escalation must be an object")
    else:
        checks = escalation.get("local_deterministic_checks")
        if not isinstance(checks, list) or not checks or not all(isinstance(x, str) and x.strip() for x in checks):
            missing.append("escalation.local_deterministic_checks must list completed local work")
        if not isinstance(escalation.get("material_impact"), str) or not escalation.get("material_impact", "").strip():
            missing.append("escalation.material_impact must explain what the answer can change")
    if missing:
        raise ConsultError("BUNDLE_INCOMPLETE", missing)
    hits = secret_locations(bundle)
    if hits:
        raise ConsultError("SECRET_DETECTED", [f"secret-like value at {path}" for path in hits])
    private_paths = private_path_locations(bundle)
    if private_paths:
        raise ConsultError("PRIVATE_PATH_DETECTED", [f"absolute or traversing path at {path}" for path in private_paths])
    normalized = json.loads(json.dumps(bundle))
    seen: set[str] = set()
    deduped: list[str] = []
    for raw_question in normalized["questions"]:
        if not isinstance(raw_question, str) or not raw_question.strip():
            continue
        question = " ".join(raw_question.split())
        key = question.casefold()
        if key not in seen:
            seen.add(key)
            deduped.append(question)
    normalized["questions"] = deduped
    long_values: list[str] = []
    def collect(v: Any) -> None:
        if isinstance(v, dict):
            for child in v.values(): collect(child)
        elif isinstance(v, list):
            for child in v: collect(child)
        elif isinstance(v, str) and len(v) >= 512:
            long_values.append(v)
    collect(normalized)
    duplicates = len(long_values) - len(set(long_values))
    if duplicates > 2:
        raise ConsultError("BUNDLE_INCOMPLETE", ["bundle contains large duplicated evidence"])
    return normalized


def escalation_reasons(bundle: dict[str, Any]) -> list[str]:
    gate = bundle.get("escalation", {})
    reasons = gate.get("reasons", []) if isinstance(gate, dict) else []
    return [r for r in reasons if isinstance(r, str) and r in ESCALATION_REASONS]


def response_schema(mission_id: str, mode: str, model: str, effort: str, question_count: int,
                    snapshot: str) -> dict[str, Any]:
    finding = {
        "type": "object", "additionalProperties": False,
        "required": ["id", "claim", "severity", "evidence", "reasoning_summary", "required_change"],
        "properties": {
            "id": {"type": "string"}, "claim": {"type": "string"},
            "severity": {"enum": ["blocking", "non_blocking"]},
            "evidence": {"type": "array", "items": {"type": "string"}},
            "reasoning_summary": {"type": "string"},
            "required_change": {"anyOf": [{"type": "string"}, {"type": "null"}]},
        },
    }
    properties: dict[str, Any] = {
        "schema_version": {"type": "string", "const": RESPONSE_SCHEMA},
        "mission_id": {"type": "string", "const": mission_id},
        "mode": {"type": "string", "const": mode},
        "model": {"type": "string", "const": model},
        "reasoning_effort": {"type": "string", "const": effort},
        "snapshot": {"type": "string", "const": snapshot},
        "verdict": {"enum": ["accept", "changes_required", "blocked"] if mode == "merge-gate"
                    else ["accept", "changes_required", "blocked", "proposed"]},
        "summary": {"type": "string"},
        "blocking_findings": {"type": "array", "items": finding},
        "non_blocking_findings": {"type": "array", "items": finding},
        "assumptions": {"type": "array", "items": {"type": "string"}},
        "required_actions": {"type": "array", "items": {"type": "string"}},
        "plan_delta": {"type": "array", "items": {"type": "string"}},
        "evidence_missing": {"type": "array", "items": {"type": "string"}},
        "questions_answered": {
            "type": "array", "minItems": question_count, "maxItems": question_count,
            "items": {
                "type": "object", "additionalProperties": False,
                "required": ["question", "answer"],
                "properties": {"question": {"type": "string"}, "answer": {"type": "string"}},
            },
        },
        "next_safe_step": {"type": "string"}, "confidence": {"enum": ["low", "medium", "high"]},
        "safe_to_merge": {"type": "boolean"},
    }
    if mode != "merge-gate":
        properties.pop("safe_to_merge")
    required = list(properties)
    return {"$schema": "https://json-schema.org/draft/2020-12/schema", "type": "object",
            "additionalProperties": False, "required": required, "properties": properties}


def validate_response(value: Any, mission_id: str, mode: str, model: str, effort: str,
                      questions: list[str], snapshot: str) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["response must be a JSON object"]
    expected = {
        "schema_version": RESPONSE_SCHEMA, "mission_id": mission_id, "mode": mode,
        "model": model, "reasoning_effort": effort, "snapshot": snapshot,
    }
    for key, wanted in expected.items():
        if value.get(key) != wanted:
            errors.append(f"{key} must equal {wanted}")
    schema = response_schema(mission_id, mode, model, effort, len(questions), snapshot)
    required = set(schema["required"])
    for key in sorted(required - set(value)):
        errors.append(f"missing response field: {key}")
    extras = set(value) - set(schema["properties"])
    for key in sorted(extras):
        errors.append(f"unexpected response field: {key}")
    allowed_verdicts = {"accept", "changes_required", "blocked"}
    if mode != "merge-gate":
        allowed_verdicts.add("proposed")
    if value.get("verdict") not in allowed_verdicts:
        errors.append("invalid verdict")
    if value.get("confidence") not in {"low", "medium", "high"}:
        errors.append("invalid confidence")
    for field in ("blocking_findings", "non_blocking_findings"):
        findings = value.get(field)
        if not isinstance(findings, list):
            errors.append(f"{field} must be an array")
            continue
        for idx, finding in enumerate(findings):
            needed = {"id", "claim", "severity", "evidence", "reasoning_summary", "required_change"}
            if not isinstance(finding, dict) or set(finding) != needed:
                errors.append(f"{field}[{idx}] is not a complete finding")
                continue
            expected_severity = "blocking" if field == "blocking_findings" else "non_blocking"
            if (not isinstance(finding["id"], str) or not finding["id"].strip() or
                    not isinstance(finding["claim"], str) or not finding["claim"].strip() or
                    finding["severity"] != expected_severity or
                    not isinstance(finding["evidence"], list) or
                    not all(isinstance(item, str) for item in finding["evidence"]) or
                    not isinstance(finding["reasoning_summary"], str) or
                    not finding["reasoning_summary"].strip() or
                    finding["required_change"] is not None and
                    not isinstance(finding["required_change"], str)):
                errors.append(f"{field}[{idx}] has invalid field types or severity")
    for field in ("assumptions", "required_actions", "plan_delta", "evidence_missing"):
        if not isinstance(value.get(field), list) or not all(isinstance(item, str) for item in value.get(field, [])):
            errors.append(f"{field} must be an array of strings")
    answered = value.get("questions_answered")
    if not isinstance(answered, list) or len(answered) != len(questions):
        errors.append("questions_answered must answer every grouped question exactly once")
    elif any(not isinstance(item, dict) or set(item) != {"question", "answer"} or
             not isinstance(item.get("answer"), str) or not item["answer"].strip()
             for item in answered):
        errors.append("each questions_answered item must contain a non-empty question and answer")
    elif [item["question"] for item in answered] != questions:
        errors.append("questions_answered must preserve the normalized question order")
    if not isinstance(value.get("summary"), str) or not value.get("summary", "").strip():
        errors.append("summary must be non-empty")
    if not isinstance(value.get("next_safe_step"), str) or not value.get("next_safe_step", "").strip():
        errors.append("next_safe_step must be non-empty")
    if mode == "merge-gate":
        accept = value.get("verdict") == "accept"
        if accept != (value.get("safe_to_merge") is True):
            errors.append("merge-gate safe_to_merge must be true exactly when verdict is accept")
        if accept and (value.get("blocking_findings") or value.get("required_actions")):
            errors.append("merge-gate accept cannot contain blocking findings or required actions")
    return errors


def normalize_json(text: str) -> Any:
    candidate = text.strip()
    if candidate.startswith("```") and candidate.endswith("```"):
        lines = candidate.splitlines()
        if len(lines) >= 3:
            candidate = "\n".join(lines[1:-1]).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError:
        start = candidate.find("{")
        if start < 0:
            raise
        value, end = json.JSONDecoder().raw_decode(candidate[start:])
        trailing = candidate[start + end:].strip()
        if trailing and not trailing.startswith("```"):
            raise json.JSONDecodeError("non-syntactic trailing content", candidate, start + end)
        return value


def build_prompt(bundle: dict[str, Any], model: str, effort: str) -> str:
    mode_note = {
        "integrated-review": "Integrate plan review, unsupported assumptions, risks, all questions, alternatives, candidate decision, minimum plan delta, and next safe step.",
        "plan": "Propose a complete plan only because local investigation could not produce a viable one.",
        "plan-review": "Return a verdict, blockers, assumptions, missing gates, minimum changes, and next safe step without needless rewrite.",
        "replan": "Return a delta from the current plan; return a full replacement only if a delta is impossible and explain why.",
        "blocker-analysis": "Rank causes and return the cheapest discriminating experiment, stop conditions, and next action.",
        "risk-audit": "Audit security, privacy, isolation, concurrency, duplicate side effects, rollback, compatibility, data, and observability together.",
        "final-review": "Classify claims as demonstrated, inferred, deferred, or not demonstrated.",
        "merge-gate": "Apply a strict merge gate and set safe_to_merge explicitly.",
    }[bundle["mode"]]
    contract = """You are a bounded, single-pass senior consultant.

Use only the supplied consultation bundle.

Do not use tools.
Do not inspect the workspace.
Do not read files.
Do not execute commands.
Do not invoke MCP.
Do not invoke subagents or other models.
Do not call codex-senior-consult.
Do not ask follow-up questions.
Do not request another turn.
Do not produce interim progress messages.
Do not propose continuing later.

Perform all requested analysis from the supplied evidence and return exactly one final response matching the requested contract.

The response must include the exact snapshot string from bundle.snapshot.repository_head in its snapshot field.
The snapshot field is an immutable identity check; do not omit it or substitute another value.
For merge-gate, verdict must be exactly accept, changes_required, or blocked; proposed is invalid.
For merge-gate accept means safe_to_merge=true, blocking_findings=[], and required_actions=[] exactly.
For merge-gate changes_required or blocked means safe_to_merge=false.

The session terminates after your first response, whether valid or invalid. Return reasoning summaries, never private chain of thought.
"""
    return (contract + "\nMode requirement: " + mode_note +
            f"\nActual model: {model}\nActual reasoning effort: {effort}\nConsultation bundle:\n" +
            json.dumps(bundle, sort_keys=True, ensure_ascii=False))


def cache_key(bundle: dict[str, Any], model: str, effort: str) -> str:
    snapshot = bundle["snapshot"]
    material = {
        "schema_version": BUNDLE_SCHEMA, "mission_id": bundle["mission_id"], "mode": bundle["mode"],
        "repository_head": snapshot["repository_head"],
        "working_tree_fingerprint": snapshot["working_tree_fingerprint"],
        "plan_fingerprint": snapshot["plan_fingerprint"],
        "checkpoint_fingerprint": snapshot["checkpoint_fingerprint"],
        "evidence_fingerprint": sha256({k: bundle[k] for k in (
            "relevant_contracts", "observed_facts", "invalidated_assumptions", "code_excerpts",
            "diff", "tests", "runtime_evidence", "constraints", "risks_already_identified")}),
        "questions_fingerprint": sha256(bundle["questions"]), "bundle_fingerprint": sha256(bundle),
        "model": model, "reasoning_effort": effort,
    }
    return sha256(material)


def read_ledger(path: Path, mission_id: str) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
        raise ConsultError("LEDGER_INVALID", ["ledger must be a regular non-symlink file"])
    entries: list[dict[str, Any]] = []
    try:
        for line in path.read_text().splitlines():
            item = json.loads(line)
            if item.get("mission_id") == mission_id:
                entries.append(item)
    except (OSError, json.JSONDecodeError):
        raise ConsultError("LEDGER_INVALID", ["ledger is unreadable or malformed"])
    return entries


def append_ledger(path: Path, entry: dict[str, Any]) -> None:
    secure_dir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        with os.fdopen(fd, "a", encoding="utf-8") as handle:
            fcntl.flock(handle, fcntl.LOCK_EX)
            handle.write(json.dumps(entry, sort_keys=True) + "\n")
            handle.flush()
            os.fsync(handle.fileno())
            fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        try: os.close(fd)
        except OSError: pass
    path.chmod(0o600)


def acquire_mission_lock(ledger_path: Path, mission_id: str):
    lock_dir = ledger_path.parent / ".codex-senior-consult-locks"
    secure_dir(lock_dir)
    lock_path = lock_dir / f"{safe_mission_id(mission_id)}.lock"
    flags = os.O_RDWR | os.O_CREAT
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    fd = os.open(lock_path, flags, 0o600)
    handle = os.fdopen(fd, "r+")
    fcntl.flock(handle, fcntl.LOCK_EX)
    return handle


def base_metrics(status: str, mission_id: str | None = None) -> dict[str, Any]:
    return {
        "status": status, "mission_id": mission_id, "superior_sessions": 0,
        "codex_exec_processes": 0, "model_turns_observed": 0,
        "backend_requests_observed": None, "tool_calls_observed": 0,
        "follow_up_turns": 0, "resume_operations": 0, "repair_executions": 0,
        "transport_retries": 0,
    }


def count_events(stdout: str) -> tuple[int, int, bool, list[str]]:
    turns = 0
    tools = 0
    tool_ids: set[str] = set()
    terminal = False
    diagnostics: list[str] = []
    threads = 0
    terminals = 0
    for number, line in enumerate(stdout.splitlines(), 1):
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            diagnostics.append(f"invalid JSONL event at line {number}")
            continue
        event_type = event.get("type")
        known_events = {"thread.started", "turn.started", "turn.completed", "turn.failed",
                        "item.started", "item.updated", "item.completed", "error"}
        if event_type not in known_events and event_type not in TOOL_ITEM_TYPES:
            diagnostics.append(f"unknown JSONL event type at line {number}")
        if event_type == "thread.started": threads += 1
        if event_type == "turn.started": turns += 1
        if event_type == "turn.completed":
            terminal = True
            terminals += 1
        if event_type in {"turn.failed", "error"}:
            raw_error = event.get("error") or event.get("message") or "unspecified Codex error"
            if isinstance(raw_error, dict):
                raw_error = raw_error.get("message") or raw_error.get("code") or "structured Codex error"
            safe_error = str(raw_error)[:500]
            for pattern in SECRET_PATTERNS:
                safe_error = pattern.sub("[REDACTED]", safe_error)
            diagnostics.append(f"{event_type}: {safe_error}")
        item = event.get("item") if isinstance(event, dict) else None
        if (event_type in {"item.started", "item.updated", "item.completed"} and
                (not isinstance(item, dict) or item.get("type") not in TOOL_ITEM_TYPES | NON_TOOL_ITEM_TYPES)):
            diagnostics.append(f"unknown JSONL item type at line {number}")
        if isinstance(item, dict) and item.get("type") in TOOL_ITEM_TYPES:
            item_id = item.get("id")
            if isinstance(item_id, str):
                if item_id not in tool_ids:
                    tool_ids.add(item_id)
                    tools += 1
            elif event_type == "item.started":
                tools += 1
        if event_type in TOOL_ITEM_TYPES: tools += 1
    if stdout.strip() and threads != 1:
        diagnostics.append(f"expected one thread.started event; observed {threads}")
    if stdout.strip() and terminals != 1:
        diagnostics.append(f"expected one turn.completed event; observed {terminals}")
    return turns, tools, terminal, diagnostics


def child_environment() -> dict[str, str]:
    allowed = ("PATH", "HOME", "CODEX_HOME", "LANG", "LC_ALL", "SSL_CERT_FILE", "SSL_CERT_DIR")
    env = {key: os.environ[key] for key in allowed if key in os.environ}
    env["CODEX_SENIOR_CONSULT_ACTIVE"] = "1"
    return env


def run_process(command: list[str], prompt: str, timeout: int, cwd: Path) -> tuple[int, str, str, bool]:
    proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=cwd, env=child_environment(), start_new_session=True)
    previous_handlers: dict[int, Any] = {}
    def cancel_handler(signum, frame):
        raise InterruptedError(f"received signal {signum}")
    for signum in (signal.SIGINT, signal.SIGTERM):
        previous_handlers[signum] = signal.getsignal(signum)
        signal.signal(signum, cancel_handler)
    try:
        stdout, stderr = proc.communicate(prompt, timeout=timeout)
        return proc.returncode, stdout, stderr, False
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            stdout, stderr = proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            stdout, stderr = proc.communicate()
        return 124, stdout, stderr, True
    except (InterruptedError, KeyboardInterrupt):
        os.killpg(proc.pid, signal.SIGTERM)
        try:
            proc.communicate(timeout=2)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            proc.communicate()
        raise ConsultError("CANCELLED", ["codex exec process group terminated cleanly"])
    finally:
        for signum, previous in previous_handlers.items():
            signal.signal(signum, previous)


def ledger_entry(args: argparse.Namespace, *, session_number: int | None, cache: str,
                 context_bytes: int, question_count: int, workspace_access: str,
                 processes: int, turns: int, tools: int, retries: int, status: str,
                 verdict: str | None, secret_exposure: bool = False) -> dict[str, Any]:
    return {
        "timestamp": utc_now(), "mission_id": args.mission_id, "mode": args.mode,
        "session_number": session_number, "soft_budget": args.soft_budget, "hard_budget": args.hard_budget,
        "cache": cache, "model": args.model, "reasoning_effort": args.effective_effort,
        "effort_triggers": args.effort_triggers, "context_bytes": context_bytes,
        "question_count": question_count, "workspace_access": workspace_access,
        "codex_exec_processes": processes, "model_turns_observed": turns,
        "backend_requests_observed": None, "tool_calls_observed": tools,
        "follow_up_turns": max(0, turns - processes), "resume_operations": 0,
        "automatic_repair_calls": 0, "automatic_transport_retries": retries,
        "exit_status": status, "verdict": verdict, "secret_exposure": secret_exposure,
    }


def emit(payload: dict[str, Any], exit_code: int = 0) -> int:
    print(json.dumps(payload, sort_keys=True))
    return exit_code


def status_report(args: argparse.Namespace) -> dict[str, Any]:
    entries = read_ledger(Path(args.ledger), args.mission_id)
    processes = sum(int(e.get("codex_exec_processes", 0)) for e in entries)
    turns = sum(int(e.get("model_turns_observed", 0)) for e in entries)
    tools = sum(int(e.get("tool_calls_observed", 0)) for e in entries)
    followups = max(0, turns - processes)
    resumes = sum(int(e.get("resume_operations", 0)) for e in entries)
    repairs = sum(int(e.get("automatic_repair_calls", 0)) for e in entries)
    transport_retries = sum(int(e.get("automatic_transport_retries", 0)) for e in entries)
    cache_hits = sum(e.get("cache") == "HIT" for e in entries)
    last = entries[-1] if entries else {}
    return {
        "status": "STATUS", "mission_id": args.mission_id, "sessions_used": processes,
        "soft_sessions_remaining": max(0, args.soft_budget - processes),
        "hard_sessions_remaining": max(0, args.hard_budget - processes),
        "codex_exec_processes": processes, "model_turns_observed": turns,
        "backend_requests_observed": None, "tool_calls_observed": tools,
        "follow_up_turns": followups, "resume_operations": resumes,
        "repair_executions": repairs, "transport_retries": transport_retries,
        "cache_hits": cache_hits, "models": sorted({e.get("model") for e in entries if e.get("model")}),
        "efforts": sorted({e.get("reasoning_effort") for e in entries if e.get("reasoning_effort")}),
        "modes": sorted({e.get("mode") for e in entries if e.get("mode")}),
        "last_verdict": last.get("verdict"),
        "exit_statuses": sorted({e.get("exit_status") for e in entries if e.get("exit_status")}),
    }


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    state = Path.home() / ".local" / "state" / "codex-senior-consult"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=sorted(MODES))
    parser.add_argument("--mission-id", required=True)
    parser.add_argument("--bundle")
    parser.add_argument("--model", default="gpt-5.6-sol")
    parser.add_argument("--effort", choices=sorted(EFFORTS), default="low")
    parser.add_argument("--critical", action="append", choices=sorted(MEDIUM_TRIGGERS), default=[])
    parser.add_argument("--workspace-read", metavar="DIR")
    parser.add_argument("--workspace-read-justification")
    parser.add_argument("--no-cache", action="store_true")
    parser.add_argument("--refresh", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--transport-retries", type=int, choices=(0, 1), default=0)
    parser.add_argument("--dangerous-yolo", action="store_true")
    parser.add_argument("--ledger", default=str(state / "ledger.jsonl"))
    parser.add_argument("--cache-dir", default=str(state / "cache"))
    parser.add_argument("--max-bundle-bytes", type=int, default=131072)
    parser.add_argument("--soft-budget", type=int, default=2)
    parser.add_argument("--hard-budget", type=int, default=3)
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--version", action="version", version=VERSION)
    args = parser.parse_args(argv)
    safe_mission_id(args.mission_id)
    if args.status:
        return args
    if not args.mode or not args.bundle:
        parser.error("--mode and --bundle are required unless --status is used")
    if args.timeout < 1 or args.hard_budget < 1 or args.soft_budget < 0 or args.soft_budget > args.hard_budget:
        parser.error("invalid timeout or mission budget")
    if args.workspace_read and not args.workspace_read_justification:
        parser.error("--workspace-read requires --workspace-read-justification")
    return args


def main(argv: list[str] | None = None) -> int:
    try:
        args = parse_args(argv)
        if args.status:
            return emit(status_report(args))
        if os.environ.get("CODEX_SENIOR_CONSULT_ACTIVE") == "1":
            return emit(base_metrics("RECURSIVE_ESCALATION_BLOCKED", args.mission_id), 2)
        bundle_path, raw = read_regular_input(args.bundle, args.max_bundle_bytes)
        try:
            bundle = json.loads(raw)
        except (UnicodeDecodeError, json.JSONDecodeError):
            raise ConsultError("BUNDLE_INCOMPLETE", ["bundle must be valid UTF-8 JSON"])
        bundle = validate_and_prepare_bundle(bundle, args.mission_id, args.mode)
        gate = bundle.get("escalation", {})
        reasons = escalation_reasons(bundle)
        if not isinstance(gate, dict) or gate.get("justified") is not True or not reasons:
            out = base_metrics("ESCALATION_NOT_JUSTIFIED", args.mission_id)
            out["local_research_needed"] = [
                "Use local reading, documentation, deterministic searches, tests, schemas, reproduction, diffs, logs, and approved contracts first."
            ]
            return emit(out, 3)
        if args.workspace_read:
            out = base_metrics("WORKSPACE_READ_UNSUPPORTED", args.mission_id)
            out["details"] = [
                "codex-cli 0.146.0 cannot expose workspace reads while preserving the zero-tool contract"
            ]
            return emit(out, 3)
        if args.dangerous_yolo:
            out = base_metrics("DANGEROUS_YOLO_DISABLED", args.mission_id)
            out["details"] = ["danger-full-access is incompatible with this installed skill's safety contract"]
            return emit(out, 3)
        args.effort_triggers = sorted(set(args.critical))
        args.effective_effort = args.effort
        if args.effort in {"low", "medium"} and args.effort_triggers:
            args.effective_effort = "medium"
        ledger_path = Path(args.ledger).expanduser().resolve()
        cache_dir = Path(args.cache_dir).expanduser().resolve()
        secure_dir(cache_dir)
        mission_lock = acquire_mission_lock(ledger_path, args.mission_id)
        entries = read_ledger(ledger_path, args.mission_id)
        sessions_used = sum(int(e.get("codex_exec_processes", 0)) for e in entries)
        key = cache_key(bundle, args.model, args.effective_effort)
        cache_path = cache_dir / f"{key}.json"
        if not args.no_cache and not args.refresh and os.path.lexists(cache_path):
            try:
                cache_info = cache_path.lstat()
                if stat.S_ISLNK(cache_info.st_mode) or not stat.S_ISREG(cache_info.st_mode):
                    raise ValueError("cache entry is not a regular file")
                cached = json.loads(cache_path.read_text())
                cached_response = cached.get("response") if isinstance(cached, dict) else None
                cache_errors = [] if isinstance(cached, dict) and cached.get("schema_version") == RESPONSE_SCHEMA else ["cache schema mismatch"]
                cache_errors.extend(validate_response(
                    cached_response, args.mission_id, args.mode, args.model,
                    args.effective_effort, bundle["questions"],
                    bundle["snapshot"]["repository_head"]))
                if cache_errors:
                    raise ValueError("; ".join(cache_errors))
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                out = base_metrics("CACHE_INVALID", args.mission_id)
                out["details"] = ["cache entry failed local schema and integrity validation"]
                return emit(out, 2)
            out = base_metrics("CACHE_HIT", args.mission_id)
            out.update({"cache": "HIT", "response": cached["response"], "model": args.model,
                        "reasoning_effort": args.effective_effort, "question_count": len(bundle["questions"])})
            entry = ledger_entry(args, session_number=None, cache="HIT", context_bytes=len(raw),
                                 question_count=len(bundle["questions"]), workspace_access="none",
                                 processes=0, turns=0, tools=0, retries=0, status="cache_hit",
                                 verdict=cached["response"].get("verdict"))
            append_ledger(ledger_path, entry)
            return emit(out)
        possible_processes = 1 + args.transport_retries
        if sessions_used + possible_processes > args.hard_budget:
            out = base_metrics("MISSION_BUDGET_EXCEEDED", args.mission_id)
            out.update({"sessions_used": sessions_used, "hard_budget": args.hard_budget})
            return emit(out, 4)
        workspace_access = "none"
        workspace: Path | None = None
        prompt = build_prompt(bundle, args.model, args.effective_effort)
        command_bin = "codex"
        total_processes = total_turns = total_tools = retries = 0
        final_text = ""
        transport_stderr = ""
        timed_out = False
        terminal = False
        jsonl_diagnostics: list[str] = []
        with tempfile.TemporaryDirectory(prefix="codex-senior-work-") as work_name, tempfile.TemporaryDirectory(prefix="codex-senior-control-") as ctl_name:
            work_dir = workspace or Path(work_name)
            ctl_dir = Path(ctl_name)
            schema_path = ctl_dir / "response.schema.json"
            result_path = ctl_dir / "last-message.json"
            secure_write(schema_path, json.dumps(response_schema(
                args.mission_id, args.mode, args.model, args.effective_effort, len(bundle["questions"]),
                bundle["snapshot"]["repository_head"])))
            command = [command_bin]
            if not args.dangerous_yolo:
                command.extend(["--ask-for-approval", "never"])
            command.extend(["exec", "-c", f'model_reasoning_effort="{args.effective_effort}"',
                       "-c", "shell_environment_policy.inherit=none",
                       "-m", args.model, "-C", str(work_dir), "--ephemeral", "--ignore-user-config",
                       "--ignore-rules", "--output-schema", str(schema_path), "--json",
                       "-o", str(result_path)])
            if args.dangerous_yolo:
                command.append("--dangerously-bypass-approvals-and-sandbox")
            else:
                command.extend(["--sandbox", "read-only"])
            if workspace is None:
                command.append("--skip-git-repo-check")
            command.append("-")
            attempts = 1 + args.transport_retries
            for attempt in range(attempts):
                total_processes += 1
                reservation = ledger_entry(
                    args, session_number=sessions_used + total_processes, cache="MISS",
                    context_bytes=len(prompt.encode()), question_count=len(bundle["questions"]),
                    workspace_access=workspace_access, processes=1, turns=0, tools=0,
                    retries=1 if attempt else 0, status="started", verdict=None)
                reservation["record_type"] = "session_reservation"
                append_ledger(ledger_path, reservation)
                exit_code, stdout, stderr, did_timeout = run_process(command, prompt, args.timeout, work_dir)
                turns, tools_seen, completed, diag = count_events(stdout)
                total_turns += turns
                total_tools += tools_seen
                terminal = terminal or completed
                jsonl_diagnostics.extend(diag)
                transport_stderr = stderr
                timed_out = did_timeout
                final_text = result_path.read_text() if result_path.is_file() else ""
                response_observed = bool(final_text.strip()) or completed or turns > 0
                if exit_code == 0 or response_observed or did_timeout or attempt + 1 == attempts:
                    break
                retries += 1
        followups = max(0, total_turns - total_processes)
        status = "completed"
        response_value: dict[str, Any] | None = None
        verdict: str | None = None
        if timed_out:
            status = "timeout"
            public_status = "TIMEOUT"
        elif not final_text.strip() or not terminal:
            status = "transport_error"
            public_status = "TRANSPORT_ERROR"
        elif total_tools > 0 or total_turns != 1 or followups > 0 or jsonl_diagnostics:
            status = "contract_violation"
            public_status = "SINGLE_PASS_CONTRACT_VIOLATION"
        else:
            try:
                parsed = normalize_json(final_text)
                errors = validate_response(
                    parsed, args.mission_id, args.mode, args.model, args.effective_effort, bundle["questions"],
                    bundle["snapshot"]["repository_head"])
                if errors:
                    raise ConsultError("MALFORMED_SUPERIOR_RESPONSE", errors)
                response_value = parsed
                verdict = parsed["verdict"]
                public_status = "COMPLETED"
            except (json.JSONDecodeError, ConsultError) as error:
                status = "malformed_response"
                public_status = "MALFORMED_SUPERIOR_RESPONSE"
                jsonl_diagnostics.extend(getattr(error, "details", []) or ["final response is not valid JSON"])
        entry = ledger_entry(args, session_number=sessions_used + 1, cache="MISS", context_bytes=len(prompt.encode()),
                             question_count=len(bundle["questions"]), workspace_access=workspace_access,
                             processes=0, turns=total_turns, tools=total_tools, retries=retries,
                             status=status, verdict=verdict)
        entry["follow_up_turns"] = followups
        entry["record_type"] = "consultation_result"
        append_ledger(ledger_path, entry)
        out = base_metrics(public_status, args.mission_id)
        out.update({
            "superior_sessions": total_processes, "codex_exec_processes": total_processes,
            "model_turns_observed": total_turns, "tool_calls_observed": total_tools,
            "follow_up_turns": followups, "transport_retries": retries,
            "model": args.model, "reasoning_effort": args.effective_effort,
            "effort_triggers": args.effort_triggers, "question_count": len(bundle["questions"]),
            "cache": "MISS", "workspace_access": workspace_access,
        })
        if response_value is not None:
            out["response"] = response_value
            if not args.no_cache:
                secure_dir(cache_dir)
                secure_write(cache_path, json.dumps({"schema_version": RESPONSE_SCHEMA, "response": response_value}, sort_keys=True))
        if jsonl_diagnostics:
            out["diagnostics"] = jsonl_diagnostics
        if transport_stderr:
            print("codex exec diagnostics: " + transport_stderr.strip()[:2000], file=sys.stderr)
        return emit(out, 0 if public_status in {"COMPLETED", "CACHE_HIT"} else 5)
    except ConsultError as error:
        out = base_metrics(error.code, getattr(locals().get("args", None), "mission_id", None))
        out["details"] = error.details
        return emit(out, 2)


if __name__ == "__main__":
    raise SystemExit(main())
