# Hermes verification mission

You are verifying the native Hermes integration of `codex-senior-consult`. GitHub and the checked-out repository are the source of truth. Do not modify the consultation engine merely to make a test pass, do not write into Hermes session databases, and do not perform automatic model retries.

## Goal

Prove whether Hermes can discover the skill, invoke the caller-neutral CLI, preserve all fail-closed contracts, call Codex exactly once for a real consultation, consume the structured result correctly, and reuse the verified cache entry without another Codex process.

## Safety and cost rules

- Run every zero-model test before the real consultation.
- `preflight`, installer tests, `--help`, and invalid-bundle tests must consume zero Codex processes.
- Perform at most one real Codex process unless the first execution returns an explicit no-verdict protocol failure and the replacement contract is deliberately being tested. Do not test replacement in this mission.
- Never treat timeout, transport failure, malformed output, persistence failure, or non-zero exit status as a semantic verdict.
- Only `status: VALID_ADVISORY_VERDICT` is actionable.
- Do not expose credentials, private paths, full conversation history, or unrelated repository content in the bundle or report.

## Phase 1 — inspect and preserve compatibility

1. Record the current branch and HEAD.
2. Inspect these files:
   - `SKILL.md`
   - `scripts/codex_senior_consult.py`
   - `integrations/hermes/SKILL.md`
   - `install/install.sh`
   - `tests/test_installers.py`
3. Confirm that the original root `SKILL.md`, `agents/openai.yaml`, and consultation engine were not changed by the Hermes integration commit range.
4. Run the existing test suite and the installer tests. Record exact commands and exit codes.

Completion criterion: all existing tests pass, or every failure is classified with evidence before continuing.

## Phase 2 — isolated installation smoke test

Use a fresh temporary directory and install both callers without touching the real homes:

```bash
TMP_ROOT="$(mktemp -d)"
bash install/install.sh \
  --client both \
  --hermes-home "$TMP_ROOT/hermes" \
  --codex-home "$TMP_ROOT/codex" \
  --bin-dir "$TMP_ROOT/bin"
```

Verify:

- the CLI exists and is executable;
- the Codex installation contains the original root `SKILL.md` unchanged;
- the Hermes installation contains `integrations/hermes/SKILL.md` as its `SKILL.md`;
- both installations contain the shared script and contracts;
- `"$TMP_ROOT/bin/codex-senior-consult" --help` succeeds;
- an invalid preflight returns structured JSON, non-zero exit status, and `model_processes_consumed: 0`;
- no `codex` child process is created during invalid preflight.

Also run `--dry-run` against a second empty temporary root and prove that it creates no files.

Completion criterion: installation and zero-model behavior are deterministic and isolated.

## Phase 3 — real Hermes installation and discovery

Install only the Hermes frontend into the configured user locations:

```bash
bash install/install-hermes.sh
```

Confirm that the selected bin directory is in the environment used by Hermes. Start a fresh Hermes session so the skill index is rebuilt. In that fresh session, verify that `codex-senior-consult` is listed or can be explicitly loaded and that its frontmatter is accepted.

Completion criterion: a new Hermes session discovers the native Hermes skill without relying on the Codex skill directory.

## Phase 4 — bounded real consultation

Construct one complete sanitized v1 input bundle requesting response v3. Use a dedicated mission ID such as:

```text
hermes-native-e2e-<UTC timestamp>
```

The question should be narrow and objectively answerable from the supplied evidence, for example whether the additive installer design preserves the original Codex caller contract. Include exact relevant excerpts, test results, current HEAD, and fingerprints. Do not grant workspace access.

Run:

```bash
codex-senior-consult preflight \
  --mission-id "$MISSION_ID" \
  --mode integrated-review \
  --bundle "$BUNDLE"
```

Proceed only if preflight is valid and reports zero model processes. Then run exactly one consultation with an outer Hermes terminal timeout greater than the wrapper timeout:

```bash
codex-senior-consult consult \
  --mission-id "$MISSION_ID" \
  --mode integrated-review \
  --bundle "$BUNDLE" \
  --model gpt-5.6-sol \
  --effort low \
  --timeout 180
```

Capture stdout, stderr, and exit code separately. Parse stdout as JSON even if the exit code is non-zero. Classify the result exclusively by the wrapper's canonical `status`.

Completion criterion: either one `VALID_ADVISORY_VERDICT` is persisted and verified, or the exact fail-closed no-verdict state is reported without inventing a semantic verdict.

## Phase 5 — cache and status

If and only if Phase 4 returned `VALID_ADVISORY_VERDICT`, invoke the identical consultation again without `--refresh` or `--no-cache`. Prove from the returned metrics and ledger that it is a cache hit and creates zero additional Codex processes.

Run `status` for the mission and verify consistency among:

- process attempts;
- valid and usable verdicts;
- cache hits;
- observed model turns;
- tool calls;
- protocol failures;
- last operational state.

Completion criterion: the second invocation reuses verified evidence and the ledger remains coherent.

## Final report

Return a concise gate report with:

- branch and HEAD;
- files inspected;
- commands and exit codes;
- test counts;
- installation paths;
- Hermes discovery evidence;
- preflight status and process count;
- real consultation status, execution ID, verdict if usable, and artifact identity;
- cache-hit evidence;
- ledger/status summary;
- regressions or contract deviations;
- final gate: `PASS`, `PASS_WITH_LIMITATIONS`, or `FAIL`.

Do not claim PASS unless the original Codex flow remains unchanged, Hermes discovers its own frontend, the zero-model gates consume zero processes, the real result is classified correctly, and any usable verdict is persisted and reverified.
