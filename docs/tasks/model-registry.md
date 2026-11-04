# Model registry and Claude calls on Bedrock

Owner: jayparmar16
Status: in-review
Issue: #5

## Goal

Every model call goes through one registry by role, so swapping a model is a one-line change.
Claude is reached on Bedrock's `bedrock-runtime` endpoint through the global inference
profiles. A smoke command makes one real call per Claude role, which settles which Anthropic
SDK client signs the requests.

## Done when

- [x] Registry roles and IDs: `vision` and `answerer` = `global.anthropic.claude-sonnet-5-5`,
      `labeler` = `global.anthropic.claude-haiku-5-5`, `embedder` = `amazon.titan-embed-text-v2:0`,
      `reranker` = `amazon.rerank-v1:0`.
- [x] Claude is called through the official Anthropic SDK with IAM (SigV4) credentials from the
      AWS profile or task role, in us-west-2. The new dependency's reason goes in the PR.
- [x] Structured output is supported for label and summary calls, and images can be sent for
      vision calls.
- [x] Every response's stop reason is checked; a refusal or error raises an error naming the
      document.
- [x] A fake client can stand in at this seam for tests.
- [x] A smoke command makes one call per Claude role and reports success. The model IDs, region
      and command are documented in the README.

## Notes

- Smoke test (us-west-2, sandbox role): `anthropic.AnthropicBedrock` against `bedrock-runtime`
  with the `global.` profiles worked first try for all three Claude roles: an image to
  `vision` (red square read as "Red"), JSON Schema structured output via
  `output_config.format` to `labeler`, and a plain reply from `answerer`. Model access is
  granted in the sandbox account. `AnthropicBedrockMantle` was not tried: AWS lists these
  models on Mantle only in GovCloud, and the first client worked.
- No `thinking`, `effort` or `tool_choice` is sent: on these models thinking is on by default
  (adaptive) and forced `tool_choice` is rejected, so structured output uses
  `output_config.format`, not a forced tool call.
- Retries and timeouts are the SDK's defaults (2 retries on 429/5xx).

## Handoff

None yet.
