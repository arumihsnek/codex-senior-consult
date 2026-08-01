import importlib.util
import json
import jsonschema
import os
from pathlib import Path
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest import mock


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


def v2_response(mode, question_ids=("Q1",)):
    answers = [{"id": question_id, "answer": "Addressed from the frozen evidence."}
               for question_id in question_ids]
    payloads = {
        "merge-gate": {"verdict": "accept", "safe_to_merge": True,
                       "blocking_findings": [], "required_actions": [],
                       "residual_risks": [], "summary": "Safe to merge."},
        "blocker-analysis": {"verdict": "continue", "ranked_causes": [],
                             "continuation_paths": [], "recommended_path": "Inspect local evidence.",
                             "cheapest_discriminating_experiment": "Run the focused check.",
                             "stop_conditions": [], "next_safe_step": "Run the focused check."},
        "replan": {"verdict": "continue", "invalidated_assumptions": [], "plan_delta": [],
                   "closed_phases_preserved": [], "new_stop_conditions": [],
                   "next_safe_step": "Keep the closed phase."},
        "integrated-review": {"verdict": "accept", "summary": "Evidence is consistent.",
                              "findings": [], "decision": {"recommendation": "continue", "rationale": "Evidence supports it."},
                              "next_safe_step": "Continue locally."},
        "plan": {"verdict": "continue", "summary": "The bounded plan is sufficient.",
                 "plan": {"steps": ["Run the focused check."], "stop_conditions": []},
                 "risks": [], "next_safe_step": "Run the focused check."},
        "plan-review": {"verdict": "accept", "summary": "The plan is acceptable.",
                        "blocking_findings": [], "required_actions": [], "next_safe_step": "Execute the plan."},
        "risk-audit": {"verdict": "continue", "risks": [], "controls": [],
                       "residual_risks": [], "next_safe_step": "Maintain controls."},
        "final-review": {"verdict": "accept", "claim_classifications": [],
                         "summary": "Claims are supported.", "next_safe_step": "Use the merge gate."},
    }
    return {"schema_version": "codex-senior-consult-response/v2", "question_answers": answers,
            **payloads[mode]}


def v3_response(mode, question_ids=("Q1",)):
    payload = v2_response(mode, question_ids)
    payload["schema_version"] = "codex-senior-consult-response/v3"
    if mode == "merge-gate": payload["non_blocking_observations"] = []
    return payload


def write_fake_codex(path, payload, *, tool=False, malformed=False, fail_transport=False, stderr_text="transport unavailable", sleep_seconds=0):
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
pathlib.Path(%r).write_text(json.dumps(dict(os.environ), sort_keys=True))
if %r:
    print(%r, file=sys.stderr)
    raise SystemExit(75)
events = %r
for event in events:
    print(json.dumps(event), flush=True)
out = pathlib.Path(sys.argv[sys.argv.index('-o') + 1])
out.write_text(%r)
""" % (sleep_seconds, str(path.parent / "env"), fail_transport, stderr_text, events, final)
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
    def test_transport_stderr_is_bounded_and_redacted(self):
        module = load_module()
        value = module.sanitize_transport_stderr(
            "fatal /home/ubuntu/.codex/config.toml sk-abcdefghijklmnopqrstuvwxyz\n"
            "Bearer abcdefghijklmnop\n"
            "permission denied /tmp/codex-senior-work-123"
        )
        self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz", value)
        self.assertNotIn("Bearer abcdefghijklmnop", value)
        self.assertNotIn("/home/ubuntu", value)
        self.assertNotIn("/tmp/codex-senior-work-123", value)
        self.assertLessEqual(len(value), 1200)

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
        self.env_log = self.base / "env"
        self.counter.write_text("0")
        self.stdin_counter.write_text("0")

    def test_response_schema_declares_only_focused_v2_payload_properties(self):
        schema = self.mod.response_schema("mission-1", "merge-gate", "gpt-5.6-sol", "medium", 1, "a" * 40)
        for name in ("schema_version", "verdict"):
            self.assertEqual(schema["properties"][name]["type"], "string")
        self.assertEqual(schema["properties"]["question_answers"]["type"], "array")
        self.assertNotIn("mission_id", schema["properties"])

    def test_response_schema_does_not_require_wrapper_metadata(self):
        schema = self.mod.response_schema("mission-1", "merge-gate", "gpt-5.6-sol", "medium", 1, "a" * 40)
        self.assertNotIn("snapshot", schema["required"])
        self.assertNotIn("snapshot", schema["properties"])

    def test_v2_output_schemas_omit_codex_rejected_unique_items_keyword(self):
        def keys(value):
            if isinstance(value, dict):
                return set(value) | set().union(*(keys(child) for child in value.values()))
            if isinstance(value, list):
                return set().union(*(keys(child) for child in value)) if value else set()
            return set()
        for mode in self.mod.MODES:
            self.assertNotIn("uniqueItems", keys(self.mod.response_schema(mode=mode)), mode)

    def test_transport_schemas_use_only_the_conservative_backend_allowlist(self):
        allowlist = {"type", "properties", "required", "additionalProperties", "items", "enum", "description"}

        def keywords(value, property_map=False):
            if isinstance(value, dict):
                found = set() if property_map else set(value)
                for key, child in value.items():
                    found |= keywords(child, key == "properties")
                return found
            if isinstance(value, list):
                return set().union(*(keywords(child) for child in value)) if value else set()
            return set()

        for mode in self.mod.MODES:
            self.assertTrue(keywords(self.mod.backend_transport_schema(mode)).issubset(allowlist), mode)

    def test_transport_strict_objects_require_every_declared_property(self):
        def violations(schema):
            found = []
            if isinstance(schema, dict):
                properties = schema.get("properties")
                if isinstance(properties, dict) and schema.get("additionalProperties") is False:
                    if set(schema.get("required", ())) != set(properties):
                        found.append(sorted(set(properties) - set(schema.get("required", ()))))
                for child in schema.values():
                    found.extend(violations(child))
            elif isinstance(schema, list):
                for child in schema:
                    found.extend(violations(child))
            return found

        for mode in self.mod.MODES:
            self.assertEqual(violations(self.mod.backend_transport_schema(mode)), [], mode)

    def test_transport_contracts_exclude_conditional_singular_fields(self):
        def property_names(schema):
            found = set()
            if isinstance(schema, dict):
                if isinstance(schema.get("properties"), dict):
                    found |= set(schema["properties"])
                for child in schema.values():
                    found |= property_names(child)
            elif isinstance(schema, list):
                for child in schema:
                    found |= property_names(child)
            return found

        for mode in self.mod.MODES:
            names = property_names(self.mod.backend_transport_schema(mode))
            self.assertNotIn("required_change", names, mode)
            self.assertNotIn("control", names, mode)

    def test_merge_gate_blocked_requires_blocking_evidence(self):
        payload = v2_response("merge-gate", ("Q1",))
        blocked = dict(payload, verdict="blocked", safe_to_merge=False,
                       blocking_findings=[], required_actions=["Stop the release."])
        self.assertTrue(self.mod.validate_response(blocked, "m", "merge-gate", "model", "low",
                                                   [{"id": "Q1", "text": "Question"}], "a" * 40))

    def test_accept_like_verdicts_reject_findings_or_actions(self):
        questions = [{"id": "Q1", "text": "Question"}]
        finding = {"id": "F-1", "claim": "Unexpected change", "severity": "blocking",
                   "evidence": ["Observed in the supplied diff."], "reasoning_summary": "Requires review."}
        plan_review = dict(v2_response("plan-review", ("Q1",)), required_actions=["Change the plan."])
        integrated = dict(v2_response("integrated-review", ("Q1",)), findings=[finding])
        self.assertTrue(self.mod.validate_response(plan_review, "m", "plan-review", "model", "low", questions, "a" * 40))
        self.assertTrue(self.mod.validate_response(integrated, "m", "integrated-review", "model", "low", questions, "a" * 40))

    def test_canonical_response_for_every_mode_verdict_passes_both_layers(self):
        questions = [{"id": "Q1", "text": "Question"}]
        finding = {"id": "F-1", "claim": "Blocking evidence", "severity": "blocking",
                   "evidence": ["Supplied evidence."], "reasoning_summary": "The gate cannot proceed."}
        for mode, contract in self.mod.MODE_CONTRACTS.items():
            for verdict in contract["verdicts"]:
                payload = v2_response(mode, ("Q1",))
                payload["verdict"] = verdict
                if mode == "merge-gate" and verdict != "accept":
                    payload["safe_to_merge"] = False
                    payload["blocking_findings"] = [finding]
                transport = jsonschema.Draft202012Validator(self.mod.backend_transport_schema(mode))
                self.assertFalse(list(transport.iter_errors(payload)), f"transport {mode} {verdict}")
                self.assertEqual(self.mod.validate_response(payload, "m", mode, "model", "low", questions, "a" * 40), [],
                                 f"local {mode} {verdict}")

    def test_invalid_json_schema_jsonl_event_is_a_schema_request_rejection(self):
        stream = "\n".join(json.dumps(event) for event in [
            {"type": "thread.started", "thread_id": "t-1"},
            {"type": "turn.started"},
            {"type": "error", "error": {"type": "invalid_request_error", "code": "invalid_json_schema",
             "message": "Invalid schema for response_format"}, "status": 400},
            {"type": "turn.failed"},
        ])
        self.assertEqual(self.mod.classify_transport_failure("", stream), "SCHEMA_OR_REQUEST_REJECTION")
        self.assertEqual(self.mod.transport_event_summary(stream), ["jsonl error: invalid_json_schema", "turn.failed"])

    def test_local_semantics_remain_stricter_than_transport_shape(self):
        payload = v2_response("merge-gate", ("Q1",))
        transport = jsonschema.Draft202012Validator(self.mod.backend_transport_schema("merge-gate"))
        questions = [{"id": "Q1", "text": "Question"}]
        for invalid in (
            dict(payload, question_answers=[{"id": "Q1", "answer": ""}]),
            dict(payload, question_answers=[{"id": "Q1", "answer": "yes"}, {"id": "Q1", "answer": "again"}]),
            dict(payload, question_answers=[]),
            dict(payload, verdict="not-a-verdict"),
            dict(payload, safe_to_merge=False),
            dict(payload, verdict="changes_required", safe_to_merge=False,
                 blocking_findings=[], required_actions=[]),
        ):
            self.assertTrue(self.mod.validate_response(invalid, "m", "merge-gate", "model", "low", questions, "a" * 40))
        self.assertFalse(list(transport.iter_errors(dict(payload, question_answers=[{"id": "Q1", "answer": ""}]))))
        self.assertTrue(list(transport.iter_errors(dict(payload, unexpected="no"))))
        self.assertTrue(list(transport.iter_errors(dict(payload, safe_to_merge="yes"))))

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

    def invoke(self, bundle, payload=None, extra=None, child_env=None, **fake_options):
        self.bundle_path.write_text(json.dumps(bundle))
        fake = self.base / "codex"
        write_fake_codex(fake, payload or response(bundle["mission_id"], bundle["mode"]), **fake_options)
        cmd = [sys.executable, str(SCRIPT), "--bundle", str(self.bundle_path),
               "--mode", bundle["mode"], "--mission-id", bundle["mission_id"],
               "--ledger", str(self.ledger), "--cache-dir", str(self.cache)]
        if extra:
            cmd.extend(extra)
        env = self.env_for(fake)
        if child_env:
            env.update(child_env)
        return subprocess.run(cmd, text=True, capture_output=True, env=env, timeout=10)

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

    def test_cli_contract_binds_requested_model_effective_effort_and_single_output_file(self):
        payload = response()
        payload["model"] = "requested-model"
        payload["reasoning_effort"] = "medium"
        proc = self.invoke(complete_bundle(), payload=payload, extra=["--model", "requested-model", "--critical", "credentials"],
                           child_env={"CODEX_HOME": "/isolated/auth-home", "OPENAI_API_KEY": "secret-value",
                                      "ANTHROPIC_API_KEY": "other-secret", "AUTHORIZATION": "Bearer value"})
        self.assertEqual(proc.returncode, 0, proc.stderr)
        argv = json.loads(self.argv_log.read_text())
        self.assertEqual(argv[argv.index("-m") + 1], "requested-model")
        self.assertEqual(argv[argv.index("-c", argv.index("-m")) + 1], 'model_reasoning_effort="medium"')
        self.assertEqual(sum(arg in {"-o", "--output-last-message"} for arg in argv), 1)
        child = json.loads(self.env_log.read_text())
        self.assertEqual(child.get("CODEX_HOME"), "/isolated/auth-home")
        self.assertNotIn("OPENAI_API_KEY", child)
        self.assertNotIn("ANTHROPIC_API_KEY", child)
        self.assertNotIn("AUTHORIZATION", child)
        allowed = {"PATH", "HOME", "USER", "LANG", "LC_ALL", "TMPDIR", "CODEX_HOME", "CODEX_SENIOR_CONSULT_ACTIVE"}
        # Assert the wrapper boundary directly. Python may add LC_CTYPE inside
        # the fake CLI while coercing an unavailable parent locale; that value
        # was not inherited or supplied by child_environment().
        self.assertTrue(set(self.mod.child_environment()).issubset(allowed))

    def test_transport_failure_retains_sanitized_actionable_diagnostics(self):
        proc = self.invoke(complete_bundle(), fail_transport=True,
                           stderr_text="network connection reset token=sk-abcdefghijklmnopqrstuvwxyz123456 /private/project",
                           child_env={"OPENAI_API_KEY": "sk-abcdefghijklmnopqrstuvwxyz123456"})
        out = self.parsed(proc)
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_VERDICT_PROTOCOL_FAILURE", "TRANSPORT_ERROR"))
        self.assertEqual(out["transport_exit_code"], 75)
        self.assertEqual(out["transport_category"], "NETWORK_OR_SERVICE_FAILURE")
        self.assertTrue(out["transport_evidence"])
        self.assertNotIn("sk-", json.dumps(out["transport_evidence"]))
        self.assertNotIn("/private/project", json.dumps(out["transport_evidence"]))
        self.assertTrue(out["diagnostic_fingerprint"])
        self.assertNotIn("stderr_summary", out)

    def test_every_v2_mode_has_schema_and_local_validator_parity(self):
        for mode in sorted(self.mod.MODES):
            payload = v2_response(mode)
            schema = self.mod.response_schema(mode=mode)
            validator = jsonschema.Draft202012Validator(schema)
            checks = {
                "canonical": payload,
                "wrong_type": dict(payload, verdict=[]),
                "extra": dict(payload, unexpected="no"),
                "missing": {key: value for key, value in payload.items() if key != "verdict"},
                "invalid_verdict": dict(payload, verdict="not-a-verdict"),
            }
            for name, candidate in checks.items():
                schema_ok = not list(validator.iter_errors(candidate))
                local_ok = not self.mod.validate_response(candidate, "m", mode, "model", "low",
                                                           [{"id": "Q1", "text": "Question"}], "a" * 40)
                self.assertEqual(schema_ok, local_ok, f"{mode} {name}")
                self.assertEqual(schema_ok, name == "canonical", f"{mode} {name}")

    def test_v2_question_answers_require_exact_unique_known_ids_and_nonempty_answers(self):
        payload = v2_response("merge-gate", ("Q1", "Q2"))
        questions = [{"id": "Q1", "text": "One"}, {"id": "Q2", "text": "Two"}]
        self.assertEqual(self.mod.validate_response(payload, "m", "merge-gate", "model", "low", questions, "a" * 40), [])
        for answers in (
            [{"id": "Q1", "answer": "Yes"}],
            [{"id": "Q1", "answer": "Yes"}, {"id": "Q1", "answer": "Again"}],
            [{"id": "Q1", "answer": "Yes"}, {"id": "Q3", "answer": "Unknown"}],
            [{"id": "Q1", "answer": ""}, {"id": "Q2", "answer": "Yes"}],
        ):
            self.assertTrue(self.mod.validate_response(dict(payload, question_answers=answers), "m", "merge-gate", "model", "low", questions, "a" * 40))

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
        for mode in ("merge-gate", "blocker-analysis", "replan"):
            payload = v2_response(mode, ())
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
        payload = v2_response("merge-gate")
        out = self.parsed(self.invoke(bundle, payload=payload))
        self.assertEqual(out["status"], "COMPLETED")
        self.assertEqual(out["response"], payload)

    def test_completed_verdict_retains_lossless_canonical_evidence(self):
        bundle = complete_bundle("durable", "merge-gate")
        bundle["requested_output"] = {"schema_version": "codex-senior-consult-response/v2"}
        payload = v2_response("merge-gate")
        out = self.parsed(self.invoke(bundle, payload=payload))
        self.assertEqual((out["status"], out["detailed_status"]), ("COMPLETED", "VALID_ADVISORY_VERDICT"))
        entry = json.loads(self.ledger.read_text().splitlines()[-1])
        self.assertTrue(entry["response_artifact"])
        self.assertEqual(entry["response_fingerprint"], self.mod.sha256(payload))
        recovered = self.mod.read_persisted_response(self.cache, entry)
        self.assertEqual(recovered["response"], payload)
        self.assertEqual(recovered["question_answer_ids"], ["Q1"])
        self.assertEqual(stat.S_IMODE((self.cache / entry["response_artifact"]["relative_path"]).stat().st_mode), 0o600)

    def test_missing_or_corrupt_evidence_makes_a_valid_verdict_unusable(self):
        bundle = complete_bundle("evidence-state", "merge-gate")
        bundle["requested_output"] = {"schema_version": "codex-senior-consult-response/v2"}
        self.assertEqual(self.invoke(bundle, payload=v2_response("merge-gate")).returncode, 0)
        entry = json.loads(self.ledger.read_text().splitlines()[-1])
        artifact = self.cache / entry["response_artifact"]["relative_path"]
        artifact.write_text('{"corrupt":true}')
        with self.assertRaisesRegex(self.mod.ConsultError, "VERDICT_EVIDENCE_UNUSABLE"):
            self.mod.read_persisted_response(self.cache, entry)
        status = self.parsed(subprocess.run(
            [sys.executable, str(SCRIPT), "--status", "--mission-id", "evidence-state",
             "--ledger", str(self.ledger), "--cache-dir", str(self.cache)],
            text=True, capture_output=True, timeout=10))
        self.assertEqual(status["usable_valid_verdicts"], 0)
        self.assertEqual(status["unusable_valid_verdicts"], 1)

    def test_historical_valid_verdict_without_payload_is_explicitly_unusable_and_not_replaceable(self):
        entry = {
            "execution_id": "historical-valid", "mission_id": "historical", "verdict": "changes_required",
            "status": "COMPLETED", "detailed_status": "VALID_ADVISORY_VERDICT", "cache": "MISS",
            "mode": "merge-gate", "model": "gpt-5.6-sol", "reasoning_effort": "medium",
            "snapshot": "s", "normalized_bundle_fingerprint": "b", "process_attempts": 1,
        }
        self.ledger.write_text(json.dumps(entry) + "\n")
        status = self.parsed(subprocess.run(
            [sys.executable, str(SCRIPT), "--status", "--mission-id", "historical",
             "--ledger", str(self.ledger), "--cache-dir", str(self.cache)],
            text=True, capture_output=True, timeout=10))
        self.assertEqual(status["last_operational_status"], "HISTORICAL_VALID_VERDICT_UNUSABLE")
        self.assertEqual(status["last_operational_reason"], "response payload not retained by the historical execution")
        self.assertEqual(status["usable_valid_verdicts"], 0)
        bundle = complete_bundle("historical", "merge-gate")
        bundle["requested_output"] = {"schema_version": "codex-senior-consult-response/v2"}
        out = self.parsed(self.invoke(bundle, payload=v2_response("merge-gate"),
                                      extra=["--replacement-for", "historical-valid", "--effort", "medium"]))
        self.assertEqual(out["status"], "REPLACEMENT_NOT_AUTHORIZED")
        self.assertEqual(self.counter.read_text(), "0")

    def test_persistence_write_failure_is_not_a_usable_verdict_or_a_retry(self):
        bundle = complete_bundle("persist-failure", "merge-gate")
        bundle["requested_output"] = {"schema_version": "codex-senior-consult-response/v2"}
        self.cache.mkdir()
        (self.cache / "responses").write_text("not a directory")
        out = self.parsed(self.invoke(bundle, payload=v2_response("merge-gate")))
        self.assertEqual((out["status"], out["detailed_status"]), ("NO_USABLE_VERDICT", "VERDICT_PERSISTENCE_FAILURE"))
        self.assertIsNone(out["verdict"])
        self.assertTrue(out["model_response_validated"])
        self.assertEqual(out["validated_model_verdict"], "accept")
        self.assertEqual(self.counter.read_text(), "1")

    def test_commit_never_appends_a_usable_ledger_entry_before_evidence(self):
        payload = v2_response("merge-gate")
        identity = {"snapshot": "s", "bundle": "b", "mode": "merge-gate", "model": "gpt-5.6-sol", "effort": "low"}
        args = self.mod.parse_args(["--mode", "merge-gate", "--mission-id", "atomic", "--bundle", "x"])
        entry = self.mod.make_entry(args, "e-1", identity, "COMPLETED", "VALID_ADVISORY_VERDICT",
                                    processes=1, turns=1, tools=0, verdict="accept", replacement_for=None)
        with mock.patch.object(self.mod, "secure_write", side_effect=OSError("write failed")), \
             mock.patch.object(self.mod, "append_ledger") as append:
            with self.assertRaises(OSError):
                self.mod.commit_usable_verdict(self.ledger, self.cache, entry, payload, identity, ["Q1"])
        append.assert_not_called()

    def test_ledger_append_failure_never_reports_a_committed_usable_verdict(self):
        payload = v2_response("merge-gate")
        identity = {"snapshot": "s", "bundle": "b", "mode": "merge-gate", "model": "gpt-5.6-sol", "effort": "low"}
        args = self.mod.parse_args(["--mode", "merge-gate", "--mission-id", "atomic", "--bundle", "x"])
        entry = self.mod.make_entry(args, "e-2", identity, "COMPLETED", "VALID_ADVISORY_VERDICT",
                                    processes=1, turns=1, tools=0, verdict="accept", replacement_for=None)
        with mock.patch.object(self.mod, "append_ledger", side_effect=OSError("append failed")):
            with self.assertRaises(OSError):
                self.mod.commit_usable_verdict(self.ledger, self.cache, entry, payload, identity, ["Q1"])
        self.assertFalse(self.ledger.exists())
        self.assertTrue(list((self.cache / "responses").glob("*.json")))

    def test_atomic_artifact_never_exposes_partial_json_to_concurrent_reader(self):
        artifact = self.cache / "responses" / ("a" * 64 + ".json")
        data = json.dumps({"payload": "x" * 500_000})
        observed = []
        stop = threading.Event()

        def reader():
            while not stop.is_set():
                if artifact.exists():
                    try:
                        json.loads(artifact.read_text())
                        observed.append("valid")
                    except json.JSONDecodeError:
                        observed.append("partial")
                time.sleep(0.001)

        thread = threading.Thread(target=reader)
        thread.start()
        self.mod.secure_write(artifact, data)
        time.sleep(0.02)
        stop.set(); thread.join(timeout=2)
        self.assertTrue(observed)
        self.assertNotIn("partial", observed)

    def test_interruption_before_atomic_rename_leaves_no_complete_artifact_or_temp_file(self):
        artifact = self.cache / "responses" / ("b" * 64 + ".json")
        with mock.patch.object(self.mod.os, "replace", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.mod.secure_write(artifact, '{"response":"complete"}')
        self.assertFalse(artifact.exists())
        self.assertEqual(list(artifact.parent.glob(f".{artifact.name}.*")), [])

    def test_duplicate_execution_id_is_rejected_and_sensitive_response_is_not_persisted(self):
        entry = {"execution_id": "duplicate", "mission_id": "dup"}
        self.mod.append_ledger(self.ledger, entry)
        with self.assertRaisesRegex(self.mod.ConsultError, "DUPLICATE_EXECUTION_REPLAY"):
            self.mod.append_ledger(self.ledger, entry)
        payload = v2_response("merge-gate")
        payload["summary"] = "token=sk-abcdefghijklmnopqrstuvwxyz123456"
        identity = {"snapshot": "s", "bundle": "b", "mode": "merge-gate", "model": "gpt-5.6-sol", "effort": "low"}
        with self.assertRaisesRegex(self.mod.ConsultError, "VERDICT_PERSISTENCE_FAILURE"):
            self.mod.persist_response_evidence(self.cache, payload, identity, ["Q1"])
        self.assertFalse((self.cache / "responses").exists())
        payload["summary"] = "see /home/ubuntu/private-review-note"
        with self.assertRaisesRegex(self.mod.ConsultError, "VERDICT_PERSISTENCE_FAILURE"):
            self.mod.persist_response_evidence(self.cache, payload, identity, ["Q1"])

    def test_v3_merge_gate_cli_persists_recoverable_mode_bound_artifact(self):
        bundle = complete_bundle(mode="merge-gate", questions=[{"id": "Q1", "text": "Safe?"}])
        bundle["requested_output"] = {"schema_version": "codex-senior-consult-response/v3"}
        proc = self.invoke(bundle, payload=v3_response("merge-gate"))
        out = self.parsed(proc)
        self.assertEqual((proc.returncode, out["detailed_status"]), (0, "VALID_ADVISORY_VERDICT"), out)
        artifact = self.cache / out["response_artifact"]["relative_path"]
        self.assertEqual(json.loads(artifact.read_text())["response"], v3_response("merge-gate"))


class V3ConstructionPreflightTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.repo = Path(self.temp.name)
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.email", "test@example.invalid"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "config", "user.name", "Test"], check=True)
        (self.repo / "README.md").write_text("fixture\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "README.md"], check=True)
        subprocess.run(["git", "-C", str(self.repo), "commit", "-qm", "fixture"], check=True)

    def tearDown(self):
        self.temp.cleanup()

    def test_legacy_cli_translation_has_no_independent_consult_path(self):
        legacy = ["--mode", "merge-gate", "--mission-id", "m", "--bundle", "b.json"]
        self.assertEqual(self.mod.translate_legacy_argv(legacy), ["consult", *legacy])
        self.assertEqual(self.mod.translate_legacy_argv(["preflight", *legacy]), ["preflight", *legacy])

    def test_build_bundle_for_every_mode_uses_null_and_rfc6901_metadata(self):
        for mode in self.mod.MODES:
            bundle = self.mod.build_bundle_skeleton("mission-1", mode, self.repo)
            self.assertEqual(bundle["mode"], mode)
            self.assertEqual(bundle["requested_output"]["schema_version"], "codex-senior-consult-response/v3")
            self.assertEqual(bundle["objective"], None)
            self.assertIn("/objective", bundle["caller_required"])
            self.assertTrue(all(pointer.startswith("/") for pointer in bundle["caller_required"]))
            self.assertNotIn("<CALLER_REQUIRED>", json.dumps(bundle))
            self.assertRegex(bundle["snapshot"]["repository_head"], r"^[0-9a-f]{40,64}$")

    def test_normalization_removes_valid_filled_pointer_and_never_hashes_pending_bundle(self):
        bundle = self.mod.build_bundle_skeleton("mission-1", "merge-gate", self.repo)
        bundle["objective"] = "Decide whether the fixture is internally consistent."
        result = self.mod.normalize_construction_bundle(bundle)
        self.assertNotIn("/objective", result["caller_required"])
        self.assertNotIn("normalized_bundle_fingerprint", result)
        bundle["objective"] = []
        invalid = self.mod.normalize_construction_bundle(bundle)
        diagnostic = next(d for d in invalid["diagnostics"] if d["path"] == "/objective")
        self.assertEqual((diagnostic["code"], diagnostic["state"]), ("CALLER_VALUE_INVALID", "invalid"))

    def test_pointer_integrity_and_deterministic_field_boundary(self):
        bundle = self.mod.build_bundle_skeleton("mission-1", "merge-gate", self.repo)
        bundle["caller_required"] += ["/objective", "/unknown", "/mode"]
        result = self.mod.normalize_construction_bundle(bundle)
        codes = {(d["code"], d["path"]) for d in result["diagnostics"]}
        self.assertIn(("CALLER_REQUIRED_DUPLICATE_PATH", "/objective"), codes)
        self.assertIn(("CALLER_REQUIRED_UNKNOWN_PATH", "/unknown"), codes)
        self.assertIn(("CALLER_REQUIRED_NON_NULL", "/mode"), codes)

    def test_preflight_distinguishes_null_and_suppresses_cascades_without_process(self):
        bundle = self.mod.build_bundle_skeleton("mission-1", "merge-gate", self.repo)
        with mock.patch.object(self.mod, "run_process", side_effect=AssertionError("model process consumed")):
            result = self.mod.preflight_bundle(bundle, mission_id="mission-1", mode="merge-gate")
        self.assertFalse(result["valid"])
        self.assertEqual(result["model_processes_consumed"], 0)
        diff_errors = [d for d in result["diagnostics"] if d["path"] == "/diff"]
        self.assertEqual(len(diff_errors), 1)
        self.assertEqual(diff_errors[0]["state"], "null")
        self.assertIn("expected", diff_errors[0])
        self.assertIn("remediation", diff_errors[0])

    def test_completed_bundle_preflights_and_strips_construction_metadata(self):
        bundle = self.mod.build_bundle_skeleton("mission-1", "merge-gate", self.repo)
        values = complete_bundle(mode="merge-gate")
        values["requested_output"] = {"schema_version": "codex-senior-consult-response/v3"}
        for pointer in list(bundle["caller_required"]):
            self.mod.assign_json_pointer(bundle, pointer, self.mod.resolve_json_pointer(values, pointer))
        result = self.mod.preflight_bundle(bundle, mission_id="mission-1", mode="merge-gate")
        self.assertTrue(result["valid"], result["diagnostics"])
        self.assertEqual(result["model_processes_consumed"], 0)
        self.assertNotIn("caller_required", result["payload"])
        self.assertRegex(result["normalized"]["bundle_fingerprint"], r"^[0-9a-f]{64}$")


class V3PrivacyTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_structural_privacy_accepts_metadata_and_digests(self):
        value = {"secrets_added": False, "secret_scope_behavior": "fail-closed",
                 "authentication_reviewed": True, "sha256": "a" * 64,
                 "repository_head": "b" * 40}
        self.assertEqual(self.mod.privacy_findings(value), [])

    def test_structural_privacy_rejects_credentials_without_echoing_values(self):
        secret = "sk-abcdefghijklmnopqrstuvwxyz123456"
        private = "-----BEGIN PRIVATE KEY-----"
        findings = self.mod.privacy_findings({"api_key": secret, "private_key": private,
                                             "auth_material": "QWxhZGRpbjpvcGVuIHNlc2FtZQ123456789"})
        self.assertEqual({f["path"] for f in findings}, {"/api_key", "/private_key", "/auth_material"})
        rendered = json.dumps(findings)
        self.assertNotIn(secret, rendered); self.assertNotIn(private, rendered)
        self.assertTrue(all(set(f) == {"path", "category"} for f in findings))

    def test_transport_classification_matrix_and_sanitize_first_evidence(self):
        cases = [
            ("", "unknown option --bad", 2, False, "CLI_ARGUMENT_FAILURE"),
            ('{"type":"error","error":{"code":"unauthorized","message":"token sk-abcdefghijklmnopqrstuvwxyz123456"}}', "", 1, False, "AUTHENTICATION_FAILURE"),
            ('{"type":"error","error":{"code":"model_not_found","message":"missing"}}', "", 1, False, "MODEL_UNAVAILABLE"),
            ('{"type":"error","error":{"code":"rate_limit_exceeded","message":"429"}}', "", 1, False, "QUOTA_OR_RATE_LIMIT"),
            ('{"type":"error","error":{"code":"invalid_json_schema","message":"bad"}}', "", 1, False, "SCHEMA_OR_REQUEST_REJECTION"),
            ('{"type":"error","error":{"code":"safety_policy","message":"blocked"}}', "", 1, False, "SAFETY_OR_POLICY_REJECTION"),
            ("", "connection reset", 75, False, "NETWORK_OR_SERVICE_FAILURE"),
            ("", "timeout", 124, True, "PROCESS_TIMEOUT"),
            ("", "", 9, False, "PROCESS_EXIT_WITHOUT_STRUCTURED_EVIDENCE"),
            ('{"type":"error","error":{"code":"novel_failure","message":"odd"}}', "", 1, False, "UNKNOWN_TRANSPORT_ERROR"),
        ]
        for stdout, stderr, code, timed_out, expected in cases:
            evidence = self.mod.parse_transport_evidence(stdout, stderr, code, timed_out)
            self.assertEqual(evidence["transport_category"], expected, evidence)
            self.assertNotIn("sk-abcdefghijklmnopqrstuvwxyz123456", json.dumps(evidence))

    def test_malformed_jsonl_is_counted_and_later_events_are_parsed(self):
        stdout = 'not-json\n{"type":"future.event"}\n{"type":"turn.failed","error":{"code":"network_error","message":"down"}}\n'
        evidence = self.mod.parse_transport_evidence(stdout, "", 1, False)
        self.assertEqual(evidence["malformed_jsonl_events"], 1)
        self.assertEqual(evidence["unknown_event_types"], 1)
        self.assertTrue(evidence["structured_transport_evidence"])


class V3ResponseCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = load_module()

    def test_v3_merge_gate_accept_truth_table_has_complete_field_paths(self):
        finding = {"id": "F1", "claim": "A blocker", "severity": "blocking",
                   "evidence": ["frozen evidence"], "reasoning_summary": "Prevents merge."}
        for safe in (False, True):
            for findings in ([], [finding]):
                for actions in ([], ["Fix before merge."]):
                    payload = v3_response("merge-gate")
                    payload.update(safe_to_merge=safe, blocking_findings=findings, required_actions=actions)
                    errors = self.mod.validate_response(payload, "m", "merge-gate", "model", "low", [{"id": "Q1"}], "a" * 40, allow_legacy=False, allow_historical=False)
                    self.assertEqual(not errors, safe and not findings and not actions, errors)
                    if not safe: self.assertTrue(any("/safe_to_merge" in error for error in errors), errors)
                    if findings: self.assertTrue(any("/blocking_findings" in error for error in errors), errors)
                    if actions: self.assertTrue(any("/required_actions" in error for error in errors), errors)

    def test_v3_is_mode_bound_and_observations_are_required_but_may_be_empty(self):
        payload = v3_response("merge-gate")
        self.assertEqual(self.mod.validate_response(payload, "m", "merge-gate", "model", "low", [{"id": "Q1"}], "a" * 40, allow_legacy=False, allow_historical=False), [])
        del payload["non_blocking_observations"]
        self.assertTrue(self.mod.validate_response(payload, "m", "merge-gate", "model", "low", [{"id": "Q1"}], "a" * 40, allow_legacy=False, allow_historical=False))
        self.assertTrue(self.mod.validate_response(v3_response("plan"), "m", "merge-gate", "model", "low", [{"id": "Q1"}], "a" * 40, allow_legacy=False, allow_historical=False))

    def test_v2_is_rejected_normally_and_accepted_only_as_historical(self):
        payload = v2_response("merge-gate")
        ordinary = self.mod.validate_response(payload, "m", "merge-gate", "model", "low", [{"id": "Q1"}], "a" * 40, allow_legacy=False, allow_historical=False)
        historical = self.mod.validate_response(payload, "m", "merge-gate", "model", "low", [{"id": "Q1"}], "a" * 40, allow_legacy=False, allow_historical=True)
        self.assertTrue(ordinary); self.assertEqual(historical, [])


if __name__ == "__main__":
    unittest.main()
