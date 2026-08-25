# GLM 5.3 validation analysis

Status: validation-only compatibility PASS. Separate balanced/quality 120-case Coding Plan reports now satisfy the user-approved R5 online acceptance criterion; production eligibility remains false.

## Scope

- Provider: GLM OpenAI-compatible Responses at `https://open.bigmodel.cn/api/v1`.
- Credential: Coding Plan validation key, injected from macOS Keychain and never persisted; use was limited to this approved Codex developer task.
- Data: fixed synthetic prompts and tool results only; no market, portfolio, user, or Ditto research evidence.
- Adapter policy: `store=false`, hosted tracing disabled, function tools only, provider-local continuation identity.

## Observed paths

| Path | Result | Usage / evidence |
|---|---|---|
| Plain `run`, 64 output-token cap | Empty final text without an auth/protocol error | The reasoning model consumed the small output allowance before final text; this cap is not usable for acceptance. |
| Plain `run`, 1024 output-token cap | Exact `DITTO_GLM_53_OK` | 1 request; 36 input + 113 output = 149 tokens; about 6.1 seconds. |
| Apps → GLM → function tool → host result | PASS; exact tool/arguments and exact evidence ref | Canonical report: 16.572 seconds; 2 requests; 598 tokens; five checks true. |
| Approval interruption and local resume | PASS | Before approval: 1 interruption, 0 host calls, continuation provider `glm_agents`. After approval: exactly 1 host call, grounded final output, resumed usage 648 tokens. |
| Responses streaming | PASS | 4 text-delta events + 1 completed event; joined and final text both exact `GLM_STREAM_OK`; 1 request / 134 tokens. |

The content-addressed evidence for the canonical function-tool smoke is [glm-validation-smoke.json](glm-validation-smoke.json). Raw model responses and credentials are intentionally absent.

## Engineering conclusion

The Ditto adapter is compatible with GLM 5.3 for the four runtime semantics R5 needs: ordinary response, function-tool loop, approval interruption/resume, and streamed text. The first empty result was not a GLM endpoint failure; it was a request-budget error caused by `max_output_tokens=64`. The validation lane therefore fixes the output cap at 1024 and enforces 2 provider requests / 4096 total tokens for its tool smoke.

The implementation remains deliberately narrow: GLM is a thin provider wrapper over the existing Responses/Agents SDK bridge, while Apps owns endpoint selection, credential scope, A4 enablement, and the production prohibition. The host verifies both total-token and output-token usage against the fixed smoke budget. A second generic LLM gateway or duplicated GLM runtime would add abstraction without a second independent consumer and is not justified.

## What this does not prove

- Coding Plan has no auditable per-call USD price, so cost SLO is `not_evaluated`, never zero.
- The provider's [Codex guide](https://docs.bigmodel.cn/cn/coding-plan/tool/codex) supports `glm-5.3` through the `/api/v1` Responses endpoint, but its [Coding Plan FAQ](https://docs.bigmodel.cn/cn/coding-plan/faq) excludes standalone/self-built API integrations. This smoke must not become a reusable Ditto subscription path; single-user operation does not change that boundary.
- The frozen 120-case fixtures are now executed by an Apps-owned synthetic scenario harness. It withholds expected-action fields, exposes only the closed allowed function tools, executes and reconciles host calls, derives model-dependent actions/citations/factual tokens/abstention from the live output, and stores only an output hash. Deterministic replay, PIT and authorization assertions remain host-owned; copying Fake verdicts into a live report is still forbidden.
- This smoke alone cannot close Task 37. The separate authenticated balanced and quality reports do close it under A4 rev4: each runs all 120 frozen synthetic cases with approved provider controls/license-egress/model-revision/token-cap scope. Neither the smoke nor those reports authorize Coding Plan for standalone/production execution; production must replace the credential and reassess changed identities. In-code price/FX/USD budgets remain unnecessary; actual currency spend is reviewed in the BigModel console.
- A3 physical OCI sandbox acceptance is separate and has passed only for the recorded exact OrbStack scope.
