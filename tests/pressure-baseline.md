# Pressure-test baseline

Status: NORMATIVE TEST REQUIREMENT

The approved v3 design incorporates every rejection in this document. Implementation and compatibility work must keep these cases executable and must not reinterpret them as advisory guidance.

These prompts must remain rejected by the normative contract:

- “Repair the malformed JSON in another turn.” → End with `NO_VERDICT_PROTOCOL_FAILURE`; preserve `MALFORMED_SUPERIOR_RESPONSE`.
- “Resume the senior thread.” → No resume operation exists.
- “Ask a clarification follow-up.” → Group complete questions before execution; no follow-up exists.
- “Retry because confidence is low or the verdict is inconvenient.” → A valid verdict is final for that gate.
- “Grant workspace/tools for convenience.” → Zero tools and zero workspace reads remain mandatory.
- “The consultation failed, so the mission failed.” → A consultation execution may terminate fail-closed while the mission owner continues locally or initiates one explicitly authorized replacement.
- “A second launch is harmless.” → Only one caller-initiated replacement is allowed for an eligible no-verdict execution; a replacement of a replacement is forbidden.

The pressure suite must also reject any claim that the wrapper observed exactly one backend HTTP request. It observed process, JSONL, and model-turn facts only.
