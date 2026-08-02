# Codex Senior Consult — session dogfood retrospective

**Status:** completed retrospective; this document is provenance and follow-up guidance, not a merge authorization.

## Evidence boundary

This retrospective was reconstructed from the persisted mission ledger and sanitized artifacts under `/home/ubuntu/.hermes-worktrees/k8-overnight-2026-08-02/`, the published Hermes ledger at `arumihsnek/my-hermes-config@codex/hermes-mission-ledger`, the skill repository, and the preserved field-failure report `references/field-reports/2026-08-hermes-kanban.md`. Raw caller bundles, prompts, credentials, protected values, databases, and environment dumps are intentionally excluded.

Offline evidence is not live evidence. No provider was invoked during this retrospective. Historical provider claims remain historical: only the Codex/Luna route had live evidence in the mission; unproven routes remained inactive and non-routable.

## 1. Executive result

The skill performed its core safety function: frozen snapshots, strict validation, one-pass tool-free consultations, durable response artifacts, and fail-closed handling of malformed or transport-failed executions were preserved across K8, K9, and mission-control work. No unsafe verdict, secret disclosure, provider activation, or unauthorized merge was observed. The principal operational failure was in the caller: it initially treated a blocked K10 objective as a globally blocked mission. The K10 security decision itself was correct; `OBJECTIVE_BLOCKED != MISSION_BLOCKED`. The mission loop was subsequently corrected and reached `QUEUE_EXHAUSTED`.

One deterministic documentation defect is corrected in this branch: ordinary consultations are v3, while v1/v2 remain explicit historical compatibility. The K8 `status` anomaly is classified as a reproducibility/integration issue rather than a confirmed skill bug: the mission verified canonical responses directly while default lookup could not locate the corresponding cache evidence. The existing offline suite reproduces the underlying unusable-evidence states and keeps them fail-closed.

## 2. Execution inventory

The mission artifact set contains **55 distinct execution IDs**. The table below records every distinct ID found in persisted JSON/JSONL ledgers; ledger-only entries have `response schema = not recorded` because their canonical response payload was not present in that file. Fingerprints are recorded only where a persisted response artifact exposed one.

| execution_id | purpose / milestone | mode | snapshot or identity | protocol verdict | domain decision | safe_to_merge | schema | artifact / ledger |
|---|---|---|---|---|---|---|---|---|
| cdd655ee-993d-49c9-bda5-c18fd0b7447c | skill v3 repair/merge gate | merge-gate | 96eddbb… | accept | accepted repair | true | v3 | session artifact `cf06b108…` |
| c111f1d7-93a9-4654-a75a-4b018a1eb657 | K8 config-only | merge-gate | config 9acd789… | accept | config ready | true | v3 | `config-consult.json` |
| eae6ccf5-161c-4b9f-8821-2778cf9895d3 | K8 product initial | merge-gate | product 43978745… | changes_required | missing worker-policy enforcement | false | v3 | `product-consult.json` |
| 02d8dead-3306-4b42-b53a-4f3bfc1d0a61 | K8 product local candidate | merge-gate | 09597eb… | accept | local candidate ready | true | v3 | `product-v2-consult.json` |
| 675e9582-d6f0-48e9-80b1-a6bbb63defef | K8 cross-repo before publication | merge-gate | config + local product | changes_required | remote PR stale | false | v3 | `cross-consult.json` |
| 6c934799-bd0e-46bd-b9d9-a0d20cfdadbf | K8 product remote first attempt | merge-gate | remote product | no verdict | malformed response | not applicable | v3 | `product-remote-ledger.jsonl` |
| a969ecf1-61a5-430f-8ac3-07eeff6cd55c | K8 product remote exact head | merge-gate | remote 09597eb… | accept | remote product ready | true | v3 | `product-remote-ledger.jsonl` |
| 747e6a7b-9f41-4681-98f2-d9351b958c57 | K8 cross-repo remote exact heads | merge-gate | config + product remote | accept | sequential integration | true | v3 | `cross-remote-ledger.jsonl` |
| 0f3a3b3e-b562-43b1-b45c-1c407f064664 | K9 objective selection | plan | K9 baseline | continue | K9 selected | not applicable | v3 | `k9-durable-selection-ledger.jsonl` |
| 7f11f2b2-91cb-423d-bf52-2b85b83b0995 | K9 next-objective plan review | plan-review | K9 baseline | accept | plan accepted | true | v3 | `next-objective-selection-ledger.jsonl` |
| 36118993-eb6a-48cc-91eb-4b742e6ed0ca | K9 planner/specs local | merge-gate | local K9 slice | accept | publish slice | true | v3 | `k9-specs-ledger.jsonl` |
| 7217eaab-8309-4ab6-850c-7bed162d6d21 | K9 specs remote draft | merge-gate | PR #8 draft | changes_required | draft state | false | v3 | `k9-specs-remote-ledger.jsonl` |
| 5a72528e-3857-4def-8d48-908d98317d99 | K9 specs remote ready | merge-gate | PR #8 ready | accept | merge candidate | true | v3 | `k9-specs-ready-ledger.jsonl` |
| 625d7da8-d9b9-4fff-898a-0e4a5c6dfe7f | K9 frontier local | merge-gate | frontier candidate | accept | publish slice | true | v3 | `k9-frontier-ledger.jsonl` |
| c0e00b86-b084-4312-acfa-14fa8ce7fbae | K9 frontier remote draft | merge-gate | PR #7 draft | changes_required | draft state | false | v3 | `k9-frontier-remote-ledger.jsonl` |
| 94f1fd29-d243-4575-9cf6-8314b8b1593a | K9 frontier remote ready | merge-gate | PR #7 ready | accept | merge candidate | true | v3 | `k9-frontier-ready-ledger.jsonl` |
| 4b6d281f-54ce-40e7-9d7d-bee32ece5975 | K9 first slice fallback gate | merge-gate | c47fc8fb… | accept | isolated slice publish | true | v3 | `k9-publish-ledger.jsonl` |
| 233411ca-9db2-4436-b757-5b0ed940098b | K9 integrated-review attempt 1 | integrated-review | c47fc8fb… | no verdict | malformed response | not applicable | v3 | `k9-slice-ledger.jsonl` |
| 29b3034d-3e95-4fb2-8a2b-2958fa41120e | K9 integrated-review attempt 2 | integrated-review | c47fc8fb… | no verdict | malformed response | not applicable | v3 | `k9-slice-ledger.jsonl` |
| 5b68370e-61dd-4df2-ae96-473e2f183ccb | K9 PR #4 remote exact head | merge-gate | c47fc8fb… | accept | merge candidate | true | v3 | `k9-remote-ledger.jsonl` |
| f7f639a6-0cee-453a-8a0d-debcd4299209 | K9 CLI local | merge-gate | CLI candidate | accept | publish slice | true | v3 | `k9-cli-slice-ledger.jsonl` |
| c0f69587-a73e-42ae-a172-ed30b6604cc8 | K9 CLI publication | merge-gate | CLI publish candidate | accept | publication accepted | true | v3 | `k9-cli-publish-ledger.jsonl` |
| 25a34ddb-da88-446b-92b1-73f1742161c1 | K9 CLI remote draft | merge-gate | PR #6 draft | changes_required | draft state | false | v3 | `k9-cli-remote-ledger.jsonl` |
| 7cfee35e-384c-443a-80cc-31f5961d9f24 | K9 CLI remote ready | merge-gate | PR #6 ready | accept | merge candidate | true | v3 | `k9-cli-remote-ready-ledger.jsonl` |
| 18e8e725-25aa-4c1a-a9f1-0d157f872b8c | K9 importer/CLI durable local | merge-gate | importer candidate | accept | publish slice | true | v3 | `k9-durable-import/cli-consult.json` |
| bfd83296-a017-4b6f-afe3-ef06c398c705 | K9 importer/CLI remote | merge-gate | remote candidate | accept | merge candidate | true | v3 | `k9-durable-import/cli-remote-consult.json` |
| 7d5e824f-f8a5-40de-bb62-ddb90728e07d | K9 architecture initial | plan-review | durable contract | changes_required | revise contract | false | v3 | `architecture-ledger.jsonl` |
| 56765da1-95ca-4d08-baa9-08be5aadffbf | K9 architecture revised | plan-review | durable contract v2 | accept | contract approved | true | v3 | `architecture-ledger-v2.jsonl` |
| bbc2ec11-2f6c-4383-ab86-9695eecd244e | K9 schema initial | merge-gate | schema candidate | blocked | schema gate blocked | false | v3 | `schema-ledger.jsonl` |
| cd7b09f4-d3d5-4794-afeb-c9e3e06f14ad | K9 schema follow-up | merge-gate | schema candidate | accept | schema ready | true | v3 | `schema-ledger-v2.jsonl` |
| 21f779a9-df16-49d0-bf4c-f34664e80aab | K9 schema remote | merge-gate | remote schema | changes_required | remote correction | false | v3 | `schema-remote-ledger.jsonl` |
| 2d609079-608e-4c03-90b2-ef8fb3a5beb2 | K9 schema ready | merge-gate | ready schema | accept | merge candidate | true | v3 | `schema-ready-ledger.jsonl` |
| bf80d704-d4ba-4f1e-a459-e82423178229 | K9 contract document | merge-gate | contract doc | accept | publish contract | true | v3 | `contract-doc-ledger.jsonl` |
| e2591e88-cd0e-4cf5-8e08-e02e6235a370 | K9 contract ready | merge-gate | contract doc | accept | merge candidate | true | v3 | `contract-ready-ledger.jsonl` |
| 4cbe9aa5-7e49-423a-b4b3-e7bd05fac857 | K9 contract remote | merge-gate | remote contract | changes_required | remote correction | false | v3 | `contract-remote-ledger.jsonl` |
| 8affb156-56a6-4c9e-a908-e150370b49c3 | K9 importer local | merge-gate | importer candidate | accept | publish importer | true | v3 | `import-consult.json` |
| 33f348c0-18e0-4015-9e10-9f67ef5df71a | K9 importer remote | merge-gate | remote importer | accept | merge candidate | true | v3 | `import-remote-consult.json` |
| 78b04442-9df8-4c62-b066-2f4cbe7be697 | K9 activation local | merge-gate | activation candidate | accept | publish activation | true | v3 | `activation-consult.json` |
| 75380526-8176-42bf-a117-4a59b48d006d | K9 activation remote | merge-gate | remote activation | accept | merge candidate | true | v3 | `activation-remote-consult.json` |
| 50c676fb-f076-4233-a136-f62988a287e1 | K9 dogfood local | merge-gate | dogfood candidate | accept | publish dogfood | true | v3 | `dogfood-consult.json` |
| 3538f22b-a996-44f0-b585-4cfa0796f786 | K9 dogfood remote | merge-gate | remote dogfood | accept | merge candidate | true | v3 | `dogfood-remote-consult.json` |
| 3e499596-bbe6-49c5-bbb2-8ba706974770 | K9 final closure | final-review | main 9578c164… | accept | K9 closed | true | v3 | `final-consult.json` |
| fc9d016f-2d7f-4d03-b846-1affbccecd21 | mission-loop planning | plan | post-K9 queue | continue | pytest selected | not applicable | v3 | `planning-consult.json` |
| e4090a36-b07b-4fc6-9988-fcf8234f5439 | pytest implementation local | merge-gate | pytest candidate | accept | implementation ready | true | v3 | `pytest-implementation-consult.json` |
| b94327af-5302-4522-acb1-77422773656c | pytest remote exact head | merge-gate | PR #24 | accept | merge candidate | true | v3 | `pytest-remote-consult.json` |
| 834b8355-6048-4f58-b744-7bf83ec8c229 | K10 planning | plan | symlink objective | continue | K10 selected | not applicable | v3 | `symlink-planning-consult.json` |
| 7ef5869e-4691-4aeb-90d7-7012ecb00bef | K10 first plan review | plan-review | K10 plan v1 | changes_required | add provenance controls | false | v3 | `symlink-plan-review-consult.json` |
| 0d1353cd-d8f0-4b94-9a84-289e43fccf17 | K10 corrected plan review | plan-review | K10 plan v2 | accept | plan accepted | true | v3 | `symlink-plan-review-v2-consult.json` |
| 13726f5b-d5cc-426a-9382-bf8a617ab9b9 | K10 security/inventory gate | risk-audit | K10 inventory | blocked | evidence insufficient | false | v3 | `symlink-inventory-gate-consult.json` |
| 1add56b7-5794-44d0-8553-943ae880bd80 | K10 corrected approval gate | risk-audit | empty allowlist | continue | deny all entries | not applicable | v3 | `symlink-approval-gate-v2-consult.json` |
| 541b60ef-11ee-4ce2-a470-e5283288959b | mission-loop recovery planning | plan | post-K10 | continue | resume queue | not applicable | v3 | `recovery-planning-consult.json` |
| 90ce27ed-5722-4ba9-abb8-60784f79a33f | recovery plan review | plan-review | recovery plan | accept | recovery accepted | true | v3 | `recovery-plan-review-consult.json` |
| 5e2a8e29-e07c-44fd-8bc8-82d8dcb53cc0 | validation-debt planning | plan | audit objective | continue | audit selected | not applicable | v3 | `debt-audit-planning-consult.json` |
| d7539b11-09a0-4e6d-b9fa-90973a0a6204 | validation-debt plan review v1 | plan-review | audit plan v1 | changes_required | add row schema/taxonomy | false | v3 | `debt-audit-plan-review-consult.json` |
| ceb2b25e-a3d8-4146-9cca-53c24deceb0f | validation-debt plan review v2 | plan-review | audit plan v2 | accept | audit plan accepted | true | v3 | `debt-audit-plan-review-v2-consult.json` |
| fd303acc-979c-4103-b589-54d9b1cb77b7 | queue exhaustion review | plan | final queue | continue | `QUEUE_EXHAUSTED` in domain answer | not applicable | v3 | `queue-exhaustion-consult.json` |

Additional persisted historical field-failure evidence, outside the 55-ID mission ledger inventory: transport failure `a98e52f9-d731-416e-a8ca-d0ce5a01b081` and its one permitted replacement `d1be8efd-5e1c-45da-aa4c-cd29c614a59a`; earlier malformed prefixes `bd8805ba…`, `cd9d40e…`, `a0967a4c…`, `2e5d0159…`, `5d6bee53…`, `a11746a2…`; and replacement activity reported for the config v2/v4/v6 field cases. Exact full IDs for those historical prefixes are not recorded in the current mission ledger. They are counted separately below, not silently merged into the 55.

## 3. Quantitative metrics

### Mission artifact inventory

| metric | observed |
|---|---:|
| distinct persisted execution IDs | 55 |
| valid semantic responses | 52 |
| protocol failures with no verdict | 3 |
| process attempts represented by those IDs | 55 |
| accept | 33 |
| continue | 7 |
| changes_required | 10 |
| blocked | 2 |
| malformed/transport/no-verdict entries in the 55 | 3 (malformed; transport not present in this mission ledger) |
| replacements | 0 in this mission ledger |
| cache hits | 0 in this mission ledger |
| observed model turns | 52 valid entries plus 3 failed attempts with no turn where recorded; exact total not consistently recorded in ledger-only rows |

The separate preserved field-failure report adds 2 transport failures, 6 malformed-response events, 4 bundle-construction rejections, and replacements in the original transport/config-v2/v4/v6 cases. Those are process-history metrics, not additional valid semantic verdicts. No cache hit was observed in the available artifacts. No timeout was identified as a completed session event; timeouts remain a supported failure class and an unobserved metric for this session.

### Distribution and gate economy

The 55-ID inventory contains 22 explicitly labelled `merge-gate` entries, 3 `plan-review` entries, 2 `integrated-review` entries, 1 `plan` entry, and 27 ledger-only entries whose mode field was not recorded. By milestone, the inventory is: K8 8 IDs including one malformed remote attempt; K9 25 IDs including two malformed integrated-review attempts; mission-loop/pytest 3 IDs; K10 5 IDs; recovery/debt/queue 7 IDs; and the skill repair gate 1 ID. The group totals are an artifact classification and are not a substitute for the missing mode fields.

The observed policy was mostly justified:

- planning gates selected among real objectives;
- plan reviews were used for lifecycle, security, migration, recovery, or multi-slice plans;
- local implementation gates were invalidated by new snapshots;
- remote exact-head gates added materially new publication, draft/ready, CI, and mergeability evidence;
- cross-repo gates were needed where compatibility did not follow from either repository alone;
- final closure gates were used only at K9 and queue-exhaustion boundaries.

Potentially redundant work was concentrated in the two malformed K9 integrated-review attempts and some remote rechecks whose main new premise was PR state. The safe minimum policy for future callers is: one planning gate when choosing among real objectives, one optional risk-triggered plan review, one implementation gate per candidate snapshot, a remote exact-head gate only when remote state is material, a cross-repo gate only when joint compatibility is not locally deducible, and a closure gate only at a milestone boundary. This is guidance, not a runtime-budget change.

## 4. Incidents and classifications

### INC-001 — protocol verdict versus domain decision

**Classification:** `CALLER_ORCHESTRATION_DEFECT`; **state:** observed; **priority:** P1; **status:** backlog.

For `fd303acc-979c-4103-b589-54d9b1cb77b7`, the persisted v3 JSON has top-level `response.verdict = "continue"`. Its mode-specific `question_answers` contains the queue decision, and the persisted response `summary`/answer states `QUEUE_EXHAUSTED`. The ledger therefore recorded a domain outcome as `plan verdict`. The protocol verdict was `continue`; the domain decision was `QUEUE_EXHAUSTED`.

The current v3 contract is mode-specific and does not expose a generic top-level `domain_decision` field. The caller had to interpret a question answer/summary. That creates a real flattening risk, but it is not yet an inequívoco skill defect because v3 deliberately leaves domain payloads mode-specific. Proposed regression fixture: assert that `continue + QUEUE_EXHAUSTED` preserves both values, and that a caller cannot overwrite `verdict` with the domain decision. A future schema change should be considered only with a focused design gate.

### INC-002 — K8 status evidence unavailable through default lookup

**Classification:** `ERGONOMIC_LIMITATION` / `NEEDS REPRODUCTION`; **state:** observed mission symptom, mechanism not proven; **priority:** P1; **status:** open.

The K8 mission log records that direct persisted v3 responses for product and cross gates were independently parsed and intact, while default `--status` reported the last verdict but marked referenced evidence unusable. The skill implementation explains the semantics: `status` resolves the ledger and cache directory supplied to that invocation; `evidence_state` returns `VERDICT_EVIDENCE_UNUSABLE` when the referenced artifact is absent, unreadable, corrupt, or identity-mismatched. The mission used isolated homes/cache roots, so a cache-root or execution-home mismatch is plausible but not proven. No code fix is justified from the current evidence.

The offline test `test_missing_or_corrupt_evidence_makes_a_valid_verdict_unusable` reproduces the safety property: a valid verdict whose artifact is corrupt becomes `usable_valid_verdicts=0`, `unusable_valid_verdicts=1`, and is not treated as actionable. The specific K8 multi-home lookup path still needs a fixture that preserves the canonical artifact in one root and invokes status against another root. Acceptance for a future fix: status must name the supplied ledger/cache identity and distinguish “response valid, evidence unavailable” from “no execution found”; it must never silently downgrade a directly verified artifact.

### INC-003 — v3/v2 documentation contradiction

**Classification:** `SKILL_DOCUMENTATION_DEFECT`; **state:** closed during session; **priority:** P1; **fix:** this branch changes `SKILL.md` to label v2 historical and `references/examples.md` to label the v2 example historical; a documentation consistency test was added.

Code, contracts, examples, and CLI compatibility flags establish v3 as the ordinary generated flow. V1/v2 remain explicit compatibility paths. Runtime behavior was not changed.

### INC-004 — gate taxonomy not always machine-explicit

**Classification:** `ERGONOMIC_LIMITATION`; **state:** observed/inferred; **priority:** P2; **status:** backlog.

The workflow distinguished planning, plan review, architecture/security, implementation, remote exact-head, cross-repository, closure, and queue review, but ledger-only mode fields were not consistently retained. The skill did not make an unsafe decision. A future documentation change should map existing modes to these use cases before adding modes.

### INC-005 — consultation frequency in multi-slice missions

**Classification:** `FUTURE_PRESSURE_TEST`; **state:** observed with quantitative inventory; **priority:** P2; **status:** backlog.

K9 required repeated exact-head gates because snapshots, draft/ready state, and remote heads changed. Some malformed attempts and bundle repairs were avoidable through better local construction. No evidence supports weakening exact-head gates. Future pressure fixtures should compare one candidate with local, remote, cross-repo, and closure evidence and measure which rechecks add a new premise.

### INC-006 — blocked objective was treated as blocked mission

**Classification:** `CALLER_ORCHESTRATION_DEFECT`; **state:** closed in mission control; **priority:** P1.

K10 correctly kept the symlink allowlist empty because neither redistribution authority nor non-sensitive-content authority was proven. The first loop stopped globally. Recovery published the blocked K10 evidence and resumed planning for independent work. The invariant is explicit: `OBJECTIVE_BLOCKED != MISSION_BLOCKED`.

### INC-007 — transport and malformed response handling

**Classification:** `EXPECTED_FAIL_CLOSED_BEHAVIOR` with `SKILL_DOCUMENTATION_DEFECT` follow-up; **state:** observed.

Transport failures and malformed responses produced no verdict, no automatic repair, and at most the explicitly permitted replacement. The field report separately identified weakly actionable transport diagnostics and contradiction messages; these are backlog items, not evidence of unsafe behavior.

### INC-008 — lexical privacy false positive

**Classification:** `SKILL_DEFECT`; **state:** observed in preserved field report; **status:** not corrected in this retrospective.

The field report records a benign boolean metadata field being rejected solely because its key name looked sensitive. No protected value was exposed and the gate failed closed. A future focused test should allow safe typed metadata while retaining value/path/secret detection. This retrospective does not alter runtime privacy behavior.

### INC-009 — incomplete caller bundles

**Classification:** `CALLER_ORCHESTRATION_DEFECT` with `ERGONOMIC_LIMITATION`; **state:** observed.

Several early failures omitted required snapshot, diff, tests, or response fields and were rejected before process launch. The preflight worked; the caller construction path was manual and omission-prone. A reusable caller-side builder is backlog, not a reason to loosen preflight.

### INC-010 — merge-gate contradiction diagnostics

**Classification:** `SKILL_DOCUMENTATION_DEFECT`; **state:** observed; **status:** backlog.

Malformed merge-gate outputs were rejected with a generic consistency message. Future diagnostics should identify the conflicting field names without retaining raw prompts or protected content.

## 5. Strengths to preserve

- Exact snapshot binding prevented local accepted candidates from authorizing stale remote PR heads.
- A valid result required an atomically persisted and re-read canonical response artifact.
- Malformed, tool-bearing, timeout, and transport-failed runs did not become verdicts.
- The consultant remained tool-free and caller-neutral; workspace investigation stayed outside the senior process.
- Replacement rules were bounded and were not used to retry inconvenient valid verdicts.
- Security gates preserved empty symlink allowlists and inactive/non-routable providers.
- K8/K9 evidence kept offline, synthetic, and historical claims separate from live evidence.
- The queue-recovery correction preserved the security verdict while allowing independent work to proceed.

## 6. Status and domain-decision follow-up tests

No new senior consultation is needed to reproduce the status symptom. The existing suite provides deterministic coverage for missing/corrupt evidence and historical verdicts without a Codex process. The next focused additions, if implemented later, are:

1. fixture with a valid ledger and canonical artifact under cache root A, then status invoked against cache root B;
2. fixture with valid response read directly from A while status reports evidence unavailable from B;
3. queue-review fixture asserting separate protocol `verdict` and domain `decision` fields at the caller boundary.

Until those fixtures exist, the K8 root cause remains `Needs reproduction`, not a confirmed bug.

## 7. Tests run for this retrospective

Executed offline on the retrospective worktree:

```text
python3 -m unittest tests/test_codex_senior_consult.py
python3 -m py_compile scripts/codex_senior_consult.py tests/test_codex_senior_consult.py
git diff --check
```

Observed results: `89 tests` passed; `py_compile` passed; `git diff --check` passed after the final EOF correction. No Codex process, provider call, network test, credential read, or live script was used for these tests. The existing suite includes v3 schemas, v1/v2 compatibility, bundle/preflight, status, persistence, replacement, cache, transport, malformed-output, privacy, and pressure fixtures. No global pytest collection was run.

## 8. Backlog

### P0

None demonstrated in this session.

### P1

- Add an isolated multi-home `status` fixture and improve diagnostics if it reproduces the K8 lookup ambiguity.
- Preserve separate machine-readable protocol verdict and domain decision at caller boundaries; decide whether a future v3-compatible field is warranted.
- Retain fail-closed behavior for transport/malformed results while improving sanitized actionable diagnostics.

### P2

- Add a canonical caller bundle builder or stronger construction ergonomics without weakening preflight.
- Improve contradiction diagnostics to enumerate safe field names.
- Add a typed-metadata privacy regression for benign sensitive-looking names.
- Document the minimum-sufficient gate policy and mode mapping.
- Add pressure fixtures for remote-head movement and multi-slice gate economy.

## 9. Security and evidence statement

This document contains no secrets, tokens, cookies, keys, `auth.json`, protected values, raw prompts, unsanitized caller bundles, target contents, or real database dumps. No provider live calls were made for the retrospective. Provider calls, protected-value reads, worker spawns, network calls, and lifecycle mutations attributable to this retrospective are all zero. Historical live evidence is not upgraded by this document.

## 10. Provenance paths

- Mission artifacts: `/home/ubuntu/.hermes-worktrees/k8-overnight-2026-08-02/`
- Mission log: `/home/ubuntu/.hermes-worktrees/k8-overnight-2026-08-02/mission-log.md`
- Published ledger: `arumihsnek/my-hermes-config@codex/hermes-mission-ledger/kanban/mission-control/`
- Skill field report: `references/field-reports/2026-08-hermes-kanban.md`
- Skill repair response artifact fingerprint: `cf06b1084fde62d684b0736e4752edc68792f0200409d9bcef89700c607b6898`
