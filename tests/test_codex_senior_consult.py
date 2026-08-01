import importlib.util
import json
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "codex_senior_consult.py"


def load_module():
    spec = importlib.util.spec_from_file_location("codex_senior_consult", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def complete_bundle(mission_id="mission-1", mode="integrated-review", questions=None):
    return {
        "schema_version": "codex-senior-consult/v1",
        "mission_id": mission_id,
        "mode": mode,
        "objective": "Ship the bounded consultation transport safely.",
        "decision_needed": "Decide whether the candidate is safe to continue.",
        "current_plan": {"version": "p1", "phases": ["inspect", "implement", "verify"]},
        "progress": {"completed": ["inspect"], "current": "implement"},
        "relevant_contracts": ["No writes by the senior consultant."],
        "observed_facts": ["The local unit suite passed at snapshot s1."],
        "invalidated_assumptions": [],
        "candidate_decision": {"choice": "continue with bounded delta"},
        "alternatives": [{"choice": "stop", "tradeoff": "delay"}],
        "code_excerpts": [{"path": "src/example.py", "lines": "10-14", "content": "return safe"}],
        "diff": {"summary": "One bounded validation change", "sha256": "d" * 64},
        "tests": [{"command": "pytest -q", "exit_code": 0, "summary": "12 passed"}],
        "runtime_evidence": [{"source": "smoke", "result": "pass"}],
        "constraints": ["Single pass", "No tools", "Read only"],
        "risks_already_identified": ["Malformed output must fail closed."],
        "questions": questions or ["Is the candidate decision supported by the supplied evidence?"],
        "requested_output": {"schema_version": "codex-senior-consult-response/v1"},
        "snapshot": {
            "repository_head": "a" * 40,
            "working_tree_fingerprint": "b" * 64,
            "plan_fingerprint": "c" * 64,
            "checkpoint_fingerprint": "e" * 64,
        },
        "escalation": {
            "justified": True,
            "reasons": ["public_contract"],
            "local_deterministic_checks": ["Read the contract", "Ran the focused tests"],
            "material_impact": "The answer changes a public contract gate.",
        },
    }


def response(mission_id="mission-1", mode="integrated-review", confidence="high", questions=None,
             snapshot="a" * 40):
    questions = questions or ["Is the candidate decision supported by the supplied evidence?"]
    value = {
        "schema_version": "codex-senior-consult-response/v1",
        "mission_id": mission_id,
        "mode": mode,
        "model": "gpt-5.6-sol",
        "reasoning_effort": "low",
        "snapshot": snapshot,
        "verdict": "accept",
        "summary": "The bounded decision is supported.",
        "blocking_findings": [],
        "non_blocking_findings": [],
        "assumptions": [],
        "required_actions": [],
        "plan_delta": [],
        "evidence_missing": [],
        "questions_answered": [{"question": question, "answer": "Yes."} for question in questions],
        "next_safe_step": "Continue with local verification.",
        "confidence": confidence,
    }
    if mode == "merge-gate":
        value["safe_to_merge"] = True
    return value


def write_fake_codex(path, payload, *, tool=False, malformed=False, fail_transport=False, sleep_seconds=0):
    final = "{not-json" if malformed else json.dumps(payload)
    events = [
        {"type": "thread.started", "thread_id": "t-1"},
        {"type": "turn.started"},
    ]
    if tool:
        events.append({"type": "item.started", "item": {"type": "command_execution", "command": "pwd"}})
    events.extend([
        {"type": "item.completed", "item": {"type": "agent_message", "text": final}},
        {"type": "turn.completed"},
    ])
    code = """#!/usr/bin/env python3
import json, os, pathlib, sys, time
time.sleep(%r)
counter = pathlib.Path(os.environ['FAKE_COUNTER'])
counter.write_text(str(int(counter.read_text() or '0') + 1))
pathlib.Path(os.environ['FAKE_ARGV']).write_text(json.dumps(sys.argv))
stdin_counter = pathlib.Path(os.environ['FAKE_STDIN_COUNTER'])
stdin_counter.write_text(str(int(stdin_counter.read_text() or '0') + 1))
prompt = sys.stdin.read()
pathlib.Path(os.environ['FAKE_PROMPT']).write_text(prompt)
if %r:
    print('transport unavailable', file=sys.stderr)
    raise SystemExit(75)
events = %r
for event in events:
    print(json.dumps(event), flush=True)
out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])
out.write_text(%r)
""" % (sleep_seconds, fail_transport, events, final)
    code = code.replace("pathlib.Path(os.environ['FAKE_COUNTER'])", f"pathlib.Path({str(path.parent / 'counter')!r})")
    code = code.replace("pathlib.Path(os.environ['FAKE_ARGV'])", f"pathlib.Path({str(path.parent / 'argv')!r})")
    code = code.replace("pathlib.Path(os.environ['FAKE_STDIN_COUNTER'])", f"pathlib.Path({str(path.parent / 'stdin-counter')!r})")
    code = code.replace("pathlib.Path(os.environ['FAKE_PROMPT'])", f"pathlib.Path({str(path.parent / 'prompt')!r})")
    path.write_text(code)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


def write_flaky_codex(path, payload):
    final = json.dumps(payload)
    code = """#!/usr/bin/env python3
import json, os, pathlib, sys
counter = pathlib.Path(os.environ['FAKE_COUNTER'])
attempt = int(counter.read_text() or '0') + 1
counter.write_text(str(attempt))
stdin_counter = pathlib.Path(os.environ['FAKE_STDIN_COUNTER'])
stdin_counter.write_text(str(int(stdin_counter.read_text() or '0') + 1))
pathlib.Path(os.environ['FAKE_PROMPT']).write_text(sys.stdin.read())
if attempt == 1:
    print('connection reset', file=sys.stderr)
    raise SystemExit(75)
for event in [
    {'type': 'thread.started', 'thread_id': 't-2'},
    {'type': 'turn.started'},
    {'type': 'item.completed', 'item': {'type': 'agent_message', 'text': %r}},
    {'type': 'turn.completed'},
]:
    print(json.dumps(event), flush=True)
pathlib.Path(sys.argv[sys.argv.index('-o') + 1]).write_text(%r)
""" % (final, final)
    code = code.replace("pathlib.Path(os.environ['FAKE_COUNTER'])", f"pathlib.Path({str(path.parent / 'counter')!r})")
    code = code.replace("pathlib.Path(os.environ['FAKE_STDIN_COUNTER'])", f"pathlib.Path({str(path.parent / 'stdin-counter')!r})")
    code = code.replace("pathlib.Path(os.environ['FAKE_PROMPT'])", f"pathlib.Path({str(path.parent / 'prompt')!r})")
    path.write_text(code)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)


class ConsultProductTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.bundle_path = self.base / "bundle.json"
        self.ledger = self.base / "ledger.jsonl"
        self.cache = self.base / "cache"
        self.counter = self.base / "counter"
        self.stdin_counter = self.base / "stdin-counter"
        self.prompt = self.base / "prompt"
        self.argv_log = self.base / "argv"
        self.counter.write_text("0")
        self.stdin_counter.write_text("0")

    def test_response_schema_const_properties_declare_json_types(self):
        schema = self.mod.response_schema("mission-1", "merge-gate", "gpt-5.6-sol", "medium", 1, "a" * 40)
        for name in ("schema_version", "mission_id", "mode", "model", "reasoning_effort", "snapshot"):
            self.assertEqual(schema["properties"][name]["type"], "string")

    def test_response_schema_requires_exact_snapshot(self):
        schema = self.mod.response_schema("mission-1", "merge-gate", "gpt-5.6-sol", "medium", 1, "a" * 40)
        self.assertNotIn("snapshot", schema["required"])
        self.assertEqual(schema["properties"]["snapshot"]["const"], "a" * 40)

    def test_validate_response_rejects_snapshot_mismatch(self):
        valid = response(mode="merge-gate", snapshot="a" * 40)
        errors = self.mod.validate_response(valid, "mission-1", "merge-gate", "gpt-5.6-sol", "low",
                                             ["Is the candidate decision supported by the supplied evidence?"],
                                             "a" * 40)
        self.assertEqual(errors, [])
        invalid = dict(valid, snapshot="b" * 40)
        errors = self.mod.validate_response(invalid, "mission-1", "merge-gate", "gpt-5.6-sol", "low",
                                             ["Is the candidate decision supported by the supplied evidence?"],
                                             "a" * 40)
        self.assertTrue(any("snapshot" in error for error in errors))

    def test_merge_gate_rejects_proposed_verdict(self):
        value = response(mode="merge-gate", snapshot="a" * 40)
        value["verdict"] = "proposed"
        value["safe_to_merge"] = False
        errors = self.mod.validate_response(value, "mission-1", "merge-gate", "gpt-5.6-sol", "low",
                                             ["Is the candidate decision supported by the supplied evidence?"],
                                             "a" * 40)
        self.assertTrue(any("invalid verdict" in error for error in errors))

    def env_for(self, fake):
        env = os.environ.copy()
        env["PATH"] = str(fake.parent) + os.pathsep + env.get("PATH", "")
        env.pop("CODEX_SENIOR_CONSULT_ACTIVE", None)
        return env

    def invoke(self, bundle, payload=None, extra=None, **fake_options):
        self.bundle_path.write_text(json.dumps(bundle))
        fake = self.base / "codex"
        write_fake_codex(fake, payload or response(bundle["mission_id"], bundle["mode"]), **fake_options)
        cmd = [sys.executable, str(SCRIPT), "--bundle", str(self.bundle_path),
               "--mode", bundle["mode"], "--mission-id", bundle["mission_id"],
               "--ledger", str(self.ledger), "--cache-dir", str(self.cache)]
        if extra:
            cmd.extend(extra)
        return subprocess.run(cmd, text=True, capture_output=True, env=self.env_for(fake), timeout=10)

    def parsed(self, proc):
        return json.loads(proc.stdout)

    def test_complete_bundle_uses_one_process_one_stdin_one_turn_and_no_tools(self):
        proc = self.invoke(complete_bundle())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = self.parsed(proc)
        self.assertEqual(out["status"], "COMPLETED")
        self.assertEqual(out["codex_exec_processes"], 1)
        self.assertEqual(out["model_turns_observed"], 1)
        self.assertIsNone(out["backend_requests_observed"])
        self.assertEqual(out["tool_calls_observed"], 0)
        self.assertEqual(out["follow_up_turns"], 0)
        self.assertEqual(out["resume_operations"], 0)
        self.assertEqual(out["repair_executions"], 0)
        self.assertEqual(out["transport_retries"], 0)
        self.assertEqual(self.counter.read_text(), "1")
        self.assertEqual(self.stdin_counter.read_text(), "1")
        prompt = self.prompt.read_text()
        self.assertIn("You are a bounded, single-pass senior consultant.", prompt)
        self.assertIn("Do not invoke subagents or other models.", prompt)

    def test_approval_flag_precedes_exec_and_shell_environment_inherits_nothing(self):
        proc = self.invoke(complete_bundle())
        self.assertEqual(proc.returncode, 0, proc.stderr)
        argv = json.loads(self.argv_log.read_text())
        self.assertLess(argv.index("--ask-for-approval"), argv.index("exec"))
        self.assertIn("shell_environment_policy.inherit=none", argv)

    def test_six_related_questions_are_grouped_into_one_session(self):
        questions = [f"Q{i}: Is risk {i} controlled?" for i in range(1, 7)]
        proc = self.invoke(complete_bundle(questions=questions), payload=response(questions=questions))
        out = self.parsed(proc)
        self.assertEqual((out["superior_sessions"], out["question_count"]), (1, 6))
        self.assertEqual(self.counter.read_text(), "1")

    def test_incomplete_bundle_stops_before_exec(self):
        bundle = complete_bundle()
        bundle["objective"] = ""
        bundle["observed_facts"] = []
        bundle["tests"] = []
        bundle["runtime_evidence"] = []
        bundle["code_excerpts"] = []
        bundle["diff"] = {}
        proc = self.invoke(bundle)
        out = self.parsed(proc)
        self.assertEqual(out["status"], "BUNDLE_INCOMPLETE")
        self.assertEqual((out["superior_sessions"], out["codex_exec_processes"]), (0, 0))
        self.assertEqual(self.counter.read_text(), "0")

    def test_escalation_not_justified_stops_before_exec(self):
        bundle = complete_bundle()
        bundle["escalation"] = {
            "justified": False, "reasons": [],
            "local_deterministic_checks": ["Ran deterministic local checks"],
            "material_impact": "No material decision remains.",
        }
        proc = self.invoke(bundle)
        out = self.parsed(proc)
        self.assertEqual(out["status"], "ESCALATION_NOT_JUSTIFIED")
        self.assertEqual(out["superior_sessions"], 0)
        self.assertEqual(self.counter.read_text(), "0")

    def test_identical_query_is_cache_hit_without_new_session(self):
        first = self.invoke(complete_bundle())
        second = self.invoke(complete_bundle())
        self.assertEqual(first.returncode, 0)
        out = self.parsed(second)
        self.assertEqual(out["status"], "CACHE_HIT")
        self.assertEqual((out["superior_sessions"], out["codex_exec_processes"]), (0, 0))
        self.assertEqual(self.counter.read_text(), "1")

    def test_malformed_response_has_no_repair_call(self):
        proc = self.invoke(complete_bundle(), malformed=True)
        out = self.parsed(proc)
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "MALFORMED_SUPERIOR_RESPONSE"))
        self.assertEqual(out["repair_executions"], 0)
        self.assertEqual(self.counter.read_text(), "1")

    def test_low_confidence_has_no_follow_up(self):
        proc = self.invoke(complete_bundle(), payload=response(confidence="low"))
        out = self.parsed(proc)
        self.assertEqual(out["status"], "COMPLETED")
        self.assertEqual(out["response"]["confidence"], "low")
        self.assertEqual(out["follow_up_turns"], 0)
        self.assertEqual(self.counter.read_text(), "1")

    def test_tool_call_is_contract_violation_without_relaunch(self):
        proc = self.invoke(complete_bundle(), tool=True)
        out = self.parsed(proc)
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "SINGLE_PASS_CONTRACT_VIOLATION"))
        self.assertEqual(out["tool_calls_observed"], 1)
        self.assertEqual(self.counter.read_text(), "1")

    def test_tool_started_and_completed_events_count_as_one_call(self):
        stdout = "\n".join(json.dumps(event) for event in [
            {"type": "thread.started", "thread_id": "t-1"},
            {"type": "turn.started"},
            {"type": "item.started", "item": {"id": "tool-1", "type": "command_execution"}},
            {"type": "item.completed", "item": {"id": "tool-1", "type": "command_execution"}},
            {"type": "turn.completed"},
        ])
        turns, tools, terminal, diagnostics = self.mod.count_events(stdout)
        self.assertEqual((turns, tools, terminal, diagnostics), (1, 1, True, []))

    def test_response_with_extra_field_is_malformed_without_repair(self):
        payload = response()
        payload["unexpected"] = "must not be accepted"
        proc = self.invoke(complete_bundle(), payload=payload)
        out = self.parsed(proc)
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "MALFORMED_SUPERIOR_RESPONSE"))
        self.assertEqual(out["repair_executions"], 0)

    def test_invalid_finding_types_and_container_severity_are_malformed(self):
        payload = response()
        payload["blocking_findings"] = [{
            "id": 7, "claim": "unsafe", "severity": "non_blocking",
            "evidence": "not-an-array", "reasoning_summary": "bad", "required_change": 42,
        }]
        out = self.parsed(self.invoke(complete_bundle(), payload=payload))
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "MALFORMED_SUPERIOR_RESPONSE"))

    def test_merge_gate_verdict_safe_flag_and_blockers_must_be_consistent(self):
        bundle = complete_bundle(mode="merge-gate")
        payload = response(mode="merge-gate")
        payload["blocking_findings"] = [{
            "id": "F-001", "claim": "Missing runtime proof", "severity": "blocking",
            "evidence": ["No runtime trace supplied"], "reasoning_summary": "Merge is not proven",
            "required_change": "Supply runtime proof",
        }]
        out = self.parsed(self.invoke(bundle, payload=payload))
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "MALFORMED_SUPERIOR_RESPONSE"))

    def test_invalid_jsonl_fails_closed_as_contract_violation(self):
        bundle = complete_bundle()
        self.bundle_path.write_text(json.dumps(bundle))
        fake = self.base / "codex"
        write_fake_codex(fake, response())
        original = fake.read_text()
        fake.write_text(original.replace("for event in events:", "print('not-json', flush=True)\nfor event in events:"))
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--bundle", str(self.bundle_path),
             "--mode", bundle["mode"], "--mission-id", bundle["mission_id"],
             "--ledger", str(self.ledger), "--cache-dir", str(self.cache)],
            text=True, capture_output=True, env=self.env_for(fake), timeout=10)
        parsed = self.parsed(proc)
        self.assertEqual((parsed["status"], parsed["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "SINGLE_PASS_CONTRACT_VIOLATION"))

    def test_corrupt_cache_is_rejected_without_exec(self):
        bundle = complete_bundle()
        self.assertEqual(self.invoke(bundle).returncode, 0)
        cache_file = next(self.cache.glob("*.json"))
        cache_file.write_text("{broken")
        out = self.parsed(self.invoke(bundle))
        self.assertEqual(out["status"], "CACHE_INVALID")
        self.assertEqual(out["codex_exec_processes"], 0)
        self.assertEqual(self.counter.read_text(), "1")

    def test_workspace_read_and_dangerous_yolo_fail_closed_on_this_cli(self):
        bundle = complete_bundle()
        workspace = self.base / "repo"
        workspace.mkdir()
        out = self.parsed(self.invoke(bundle, extra=[
            "--workspace-read", str(workspace),
            "--workspace-read-justification", "Exceptional evidence is not bundleable.",
        ]))
        self.assertEqual(out["status"], "WORKSPACE_READ_UNSUPPORTED")
        out2 = self.parsed(self.invoke(bundle, extra=["--dangerous-yolo"]))
        self.assertEqual(out2["status"], "DANGEROUS_YOLO_DISABLED")
        self.assertEqual(self.counter.read_text(), "0")

    def test_every_grouped_question_must_be_answered_in_first_response(self):
        questions = [f"Q{i}: Is risk {i} controlled?" for i in range(1, 7)]
        proc = self.invoke(complete_bundle(questions=questions), payload=response())
        out = self.parsed(proc)
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "MALFORMED_SUPERIOR_RESPONSE"))
        self.assertEqual(self.counter.read_text(), "1")

    def test_recursion_is_blocked_before_exec(self):
        bundle = complete_bundle()
        self.bundle_path.write_text(json.dumps(bundle))
        fake = self.base / "codex"
        write_fake_codex(fake, response())
        env = self.env_for(fake)
        env["CODEX_SENIOR_CONSULT_ACTIVE"] = "1"
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--bundle", str(self.bundle_path),
             "--mode", bundle["mode"], "--mission-id", bundle["mission_id"],
             "--ledger", str(self.ledger), "--cache-dir", str(self.cache)],
            text=True, capture_output=True, env=env, timeout=10)
        out = self.parsed(proc)
        self.assertEqual(out["status"], "RECURSIVE_ESCALATION_BLOCKED")
        self.assertEqual(out["superior_sessions"], 0)
        self.assertEqual(self.counter.read_text(), "0")

    def test_critical_trigger_selects_medium_for_one_session(self):
        bundle = complete_bundle()
        bundle["risks_already_identified"] = ["Credential isolation across processes is unresolved."]
        proc = self.invoke(bundle, extra=["--critical", "credentials"])
        out = self.parsed(proc)
        self.assertEqual(out["reasoning_effort"], "medium")
        self.assertEqual(out["effort_triggers"], ["credentials"])
        self.assertEqual(out["superior_sessions"], 1)

    def test_transport_retry_requires_explicit_flag_and_counts_execution(self):
        proc = self.invoke(complete_bundle(), fail_transport=True)
        out = self.parsed(proc)
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "TRANSPORT_ERROR"))
        self.assertEqual(out["transport_retries"], 0)
        self.assertEqual(self.counter.read_text(), "1")

    def test_explicit_single_transport_retry_replays_stdin_and_counts_two_processes(self):
        bundle = complete_bundle()
        self.bundle_path.write_text(json.dumps(bundle))
        fake = self.base / "codex"
        write_flaky_codex(fake, response())
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--bundle", str(self.bundle_path),
             "--mode", bundle["mode"], "--mission-id", bundle["mission_id"],
             "--transport-retries", "1", "--ledger", str(self.ledger),
             "--cache-dir", str(self.cache)],
            text=True, capture_output=True, env=self.env_for(fake), timeout=10)
        out = self.parsed(proc)
        self.assertEqual(out["status"], "COMPLETED")
        self.assertEqual(out["codex_exec_processes"], 2)
        self.assertEqual(out["superior_sessions"], 2)
        self.assertEqual(out["transport_retries"], 1)
        self.assertEqual(self.stdin_counter.read_text(), "2")

    def test_cache_hit_remains_available_after_hard_budget_is_consumed(self):
        first = complete_bundle("budgeted", "integrated-review")
        self.assertEqual(self.invoke(first, payload=response("budgeted", "integrated-review")).returncode, 0)
        for mode, marker in (("plan-review", "1"), ("final-review", "2")):
            bundle = complete_bundle("budgeted", mode)
            bundle["snapshot"]["checkpoint_fingerprint"] = marker * 64
            self.assertEqual(self.invoke(bundle, payload=response("budgeted", mode)).returncode, 0)
        cached = self.invoke(first, payload=response("budgeted", "integrated-review"))
        out = self.parsed(cached)
        self.assertEqual(out["status"], "CACHE_HIT")
        self.assertEqual(out["superior_sessions"], 0)
        self.assertEqual(self.counter.read_text(), "3")

    def test_concurrent_invocations_cannot_exceed_hard_budget(self):
        fake = self.base / "codex"
        write_fake_codex(fake, response("concurrent"), sleep_seconds=0.4)
        paths = []
        commands = []
        for index in (1, 2):
            bundle = complete_bundle("concurrent")
            bundle["snapshot"]["checkpoint_fingerprint"] = str(index) * 64
            path = self.base / f"bundle-{index}.json"
            path.write_text(json.dumps(bundle))
            paths.append(path)
            commands.append([
                sys.executable, str(SCRIPT), "--bundle", str(path), "--mode", "integrated-review",
                "--mission-id", "concurrent", "--hard-budget", "1", "--soft-budget", "1",
                "--ledger", str(self.ledger), "--cache-dir", str(self.cache),
            ])
        env = self.env_for(fake)
        processes = [subprocess.Popen(cmd, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env)
                     for cmd in commands]
        outputs = [json.loads(proc.communicate(timeout=10)[0]) for proc in processes]
        self.assertEqual(sorted(out["status"] for out in outputs), ["COMPLETED", "MISSION_BUDGET_EXCEEDED"])
        self.assertEqual(self.counter.read_text(), "1")

    def test_secret_and_fifo_are_rejected_before_exec(self):
        bundle = complete_bundle()
        bundle["observed_facts"].append("token=sk-abcdefghijklmnopqrstuvwxyz123456")
        proc = self.invoke(bundle)
        self.assertEqual(self.parsed(proc)["status"], "SECRET_DETECTED")
        fifo = self.base / "bundle.fifo"
        os.mkfifo(fifo)
        fake = self.base / "codex"
        write_fake_codex(fake, response())
        cmd = [sys.executable, str(SCRIPT), "--bundle", str(fifo), "--mode", "integrated-review",
               "--mission-id", "mission-1", "--ledger", str(self.ledger), "--cache-dir", str(self.cache)]
        proc2 = subprocess.run(cmd, text=True, capture_output=True, env=self.env_for(fake), timeout=10)
        self.assertEqual(self.parsed(proc2)["status"], "INVALID_BUNDLE_PATH")
        self.assertEqual(self.counter.read_text(), "0")

    def test_status_reports_budget_and_observed_metrics(self):
        self.assertEqual(self.invoke(complete_bundle()).returncode, 0)
        proc = subprocess.run(
            [sys.executable, str(SCRIPT), "--status", "--mission-id", "mission-1",
             "--ledger", str(self.ledger), "--cache-dir", str(self.cache)],
            text=True, capture_output=True, timeout=10)
        out = self.parsed(proc)
        self.assertEqual(out["sessions_used"], 1)
        self.assertEqual(out["soft_sessions_remaining"], 1)
        self.assertEqual(out["hard_sessions_remaining"], 2)
        self.assertEqual(out["codex_exec_processes"], 1)
        self.assertEqual(out["model_turns_observed"], 1)
        self.assertEqual(out["follow_up_turns"], 0)
        self.assertEqual(out["last_verdict"], "accept")

    def test_twenty_phase_mission_uses_two_sessions_and_deterministic_uses_zero(self):
        initial = complete_bundle("twenty-phases", "integrated-review")
        self.assertEqual(self.invoke(initial).returncode, 0)
        final = complete_bundle("twenty-phases", "merge-gate")
        final["progress"] = {"completed_phases": list(range(1, 21)), "current": "merge-gate"}
        final["snapshot"]["checkpoint_fingerprint"] = "f" * 64
        self.assertEqual(self.invoke(final, payload=response("twenty-phases", "merge-gate")).returncode, 0)
        entries = [json.loads(x) for x in self.ledger.read_text().splitlines()]
        mission = [x for x in entries if x["mission_id"] == "twenty-phases"]
        self.assertEqual(sum(x["codex_exec_processes"] for x in mission), 2)
        self.assertEqual(sum(x["model_turns_observed"] for x in mission), 2)
        self.assertEqual(sum(x["tool_calls_observed"] for x in mission), 0)
        deterministic = complete_bundle("deterministic")
        deterministic["escalation"] = {
            "justified": False, "reasons": [],
            "local_deterministic_checks": ["All decisions resolved locally"],
            "material_impact": "No material decision remains.",
        }
        out = self.parsed(self.invoke(deterministic))
        self.assertEqual((out["status"], out["superior_sessions"]), ("ESCALATION_NOT_JUSTIFIED", 0))

    def test_v2_focused_mode_contracts_do_not_require_wrapper_metadata(self):
        for mode, payload in {
            "merge-gate": {"verdict": "accept", "safe_to_merge": True,
                           "blocking_findings": [], "required_actions": [],
                           "residual_risks": [], "summary": "safe"},
            "blocker-analysis": {"verdict": "continue", "ranked_causes": [],
                                 "continuation_paths": [], "recommended_path": "local",
                                 "cheapest_discriminating_experiment": "inspect",
                                 "stop_conditions": [], "next_safe_step": "inspect"},
            "replan": {"verdict": "replan", "invalidated_assumptions": [],
                       "plan_delta": [], "closed_phases_preserved": [],
                       "new_stop_conditions": [], "next_safe_step": "inspect"},
        }.items():
            payload["schema_version"] = "codex-senior-consult-response/v2"
            self.assertEqual(self.mod.validate_response(payload, "m", mode, "model", "low", [], "x" * 64),
                             [])

    def test_malformed_response_is_no_verdict_and_exposes_execution_id(self):
        out = self.parsed(self.invoke(complete_bundle(), malformed=True))
        self.assertEqual(out["status"], "NO_VERDICT_PROTOCOL_FAILURE")
        self.assertEqual(out["detailed_status"], "MALFORMED_SUPERIOR_RESPONSE")
        self.assertIsNone(out["verdict"])
        self.assertTrue(out["execution_id"])

    def test_one_explicit_replacement_is_fresh_and_linked(self):
        first = self.parsed(self.invoke(complete_bundle(), malformed=True))
        second = self.parsed(self.invoke(complete_bundle(), payload=response(),
                                         extra=["--replacement-for", first["execution_id"]]))
        self.assertEqual(second["status"], "COMPLETED")
        self.assertEqual(second["replacement_for"], first["execution_id"])
        entries = [json.loads(line) for line in self.ledger.read_text().splitlines()]
        self.assertEqual(entries[-1]["replacement_for"], first["execution_id"])
        self.assertEqual(self.counter.read_text(), "2")

    def test_second_replacement_and_replacement_after_valid_verdict_are_rejected(self):
        first = self.parsed(self.invoke(complete_bundle(), malformed=True))
        second = self.parsed(self.invoke(complete_bundle(), payload=response(),
                                         extra=["--replacement-for", first["execution_id"]]))
        rejected = self.parsed(self.invoke(complete_bundle(), payload=response(),
                                           extra=["--replacement-for", first["execution_id"]]))
        self.assertEqual(rejected["status"], "REPLACEMENT_NOT_AUTHORIZED")
        valid = self.parsed(self.invoke(complete_bundle("valid")))
        unwanted = self.parsed(self.invoke(complete_bundle("valid"), payload=response()))
        self.assertIn(unwanted["status"], {"CACHE_HIT", "COMPLETED"})
        self.assertEqual(second["status"], "COMPLETED")
        self.assertEqual(valid["status"], "COMPLETED")

    def test_secret_scope_descriptions_pass_but_ambiguous_credentials_fail_closed(self):
        bundle = complete_bundle()
        bundle["observed_facts"] = [{"secret_scope": "contract metadata; values are redacted",
                                     "authentication_contract": "caller supplies no credentials"}]
        self.assertEqual(self.mod.secret_locations(bundle), [])
        bundle["observed_facts"].append({"client_secret": "unknown-value"})
        self.assertTrue(self.mod.secret_locations(bundle))

    def test_status_separates_process_and_verdict_counters(self):
        self.invoke(complete_bundle())
        out = self.parsed(subprocess.run(
            [sys.executable, str(SCRIPT), "--status", "--mission-id", "mission-1",
             "--ledger", str(self.ledger), "--cache-dir", str(self.cache)],
            text=True, capture_output=True, timeout=10))
        self.assertEqual(out["process_attempts"], 1)
        self.assertEqual(out["valid_verdicts"], 1)
        self.assertEqual(out["protocol_failures"], 0)
        self.assertEqual(out["replacement_attempts"], 0)

    def test_replacement_with_changed_snapshot_is_rejected_before_transport(self):
        first = self.parsed(self.invoke(complete_bundle(), malformed=True))
        changed = complete_bundle()
        changed["snapshot"]["checkpoint_fingerprint"] = "f" * 64
        out = self.parsed(self.invoke(changed, payload=response(),
                                      extra=["--replacement-for", first["execution_id"]]))
        self.assertEqual(out["status"], "REPLACEMENT_NOT_AUTHORIZED")
        self.assertEqual(self.counter.read_text(), "1")

    def test_v2_merge_gate_cli_uses_focused_response_without_metadata(self):
        bundle = complete_bundle("v2", "merge-gate")
        bundle["requested_output"] = {"schema_version": "codex-senior-consult-response/v2"}
        payload = {"schema_version": "codex-senior-consult-response/v2", "verdict": "accept",
                   "safe_to_merge": True, "blocking_findings": [], "required_actions": [],
                   "residual_risks": [], "summary": "safe"}
        out = self.parsed(self.invoke(bundle, payload=payload))
        self.assertEqual(out["status"], "COMPLETED")
        self.assertEqual(out["response"], payload)


if __name__ == "__main__":
    unittest.main()
