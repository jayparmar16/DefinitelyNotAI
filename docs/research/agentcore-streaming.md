# Streaming agent events from AgentCore Runtime to the browser

Research for issue #34. Facts as of **2026-11-04**, region **us-west-2**. Sources are AWS docs,
AWS SDK source and AWS samples unless marked *community*.

## Recommendation

Use **one CloudFront distribution for both the UI and the API**, with a Python relay on a
**Lambda Function URL in `RESPONSE_STREAM` mode** behind it:

```
browser (static Next.js on CloudFront)
  POST /api/ask                              same origin, so no CORS
    -> CloudFront behavior /api/*            no caching; OAC signs the request
    -> Lambda Function URL                   AWS_IAM auth, RESPONSE_STREAM
    -> relay (Python 3.12 + Lambda Web Adapter layer, Starlette on uvicorn)
    -> boto3 bedrock-agentcore invoke_agent_runtime     SigV4, relay role only
    -> AgentCore Runtime entrypoint          async generator yields AgentEvent dicts
  <- text/event-stream, one `data: {AgentEvent}` frame per event, passed through unchanged
```

Why this path:

- It works in us-west-2 today. Each piece is generally available there, and the Terraform AWS
  provider (v6.71.0) has a resource for each one.
- Same origin means no CORS configuration anywhere.
- No sign-in. The browser never holds AWS credentials or a token.
- The relay is the one place to cap spend. Its reserved concurrency limits how many agent runs
  can happen at once.
- All the backend code is Python. Lambda can't stream from a Python handler natively, so the
  Lambda Web Adapter layer handles streaming, and the relay is a few lines of Starlette.

### Settings for a Deep research run of about 60 seconds

| Layer | Setting | Why |
| --- | --- | --- |
| Agent | Yield a `step` event at least every 20 s | CloudFront drops the connection if no bytes arrive for the origin response timeout |
| boto3 client | `Config(read_timeout=120, retries={"total_max_attempts": 1})` | The botocore default read timeout is 60 s. A retry would start a second agent run |
| Lambda | `timeout = 120`, `memory_size = 512`, `reserved_concurrent_executions = 5` | Room for 60 s runs. At most 5 runs at once; the 6th gets HTTP 429 |
| Function URL | `authorization_type = "AWS_IAM"`, `invoke_mode = "RESPONSE_STREAM"` | Only CloudFront (through OAC) can call it, and the response streams |
| CloudFront `/api/*` | Managed-CachingDisabled, Managed-AllViewerExceptHostHeader, all methods, `origin_read_timeout = 60` | Function URLs need their own Host header. 60 s is the most the Terraform docs allow without a quota request (the CloudFront quota page says 1-120 s) |
| Browser | Send the `x-amz-content-sha256` header (SHA-256 of the body) | OAC requires it on POST to a Function URL |
| AgentCore | Defaults | 15 min per synchronous request, 60 min per stream. 60 s fits easily |

### How the open demo URL is protected

1. **No bypass:** with `AWS_IAM` plus OAC, the Function URL rejects any request not signed by
   this CloudFront distribution. Only `/api/*` on the CloudFront domain reaches the relay.
2. **Hard cost cap:** reserved concurrency of 5 allows at most 5 agent runs at once. Further
   requests get HTTP 429. Setting reserved concurrency to 0 is the kill switch.
3. **Input checks in the relay:** question length (1-2,000 characters), `mode` is `quick` or
   `deep`, and `sessionId` is 33-256 characters (the AgentCore minimum is 33).
4. **Least privilege:** the relay role may call only `bedrock-agentcore:InvokeAgentRuntime`,
   only on `askwri-agent-runtime` and its `DEFAULT` endpoint. AWS checks both resources.
5. **Optional:** an AWS WAF web ACL on the distribution with a
   per-IP rate-based rule scoped to `/api/*`. The lowest limit is 10 requests per window, and
   the window is 1, 2, 5 or 10 minutes.

A shared-secret header from the browser adds nothing. Anyone can read it in DevTools, and OAC
already blocks direct calls.

**Fallback if OAC signing returns 403 on demo night:** set the Function URL to
`authorization_type = "NONE"`. Keep the CloudFront behavior, so the API stays same-origin, and
keep reserved concurrency. It is a one-line Terraform change. The cost: anyone who finds the
`lambda-url` hostname can call the relay directly, but still only 5 at a time.

### Check before building

- `aws lambda get-account-settings --region us-west-2`: reserved concurrency can only take
  what is left after 100 units stay unreserved, so the account limit must be at least 105. New
  accounts can have a lower limit. I couldn't run this check because this session has no AWS
  credentials.
- `bedrock-agentcore` must be **1.25.2 or later** (released 2026-10-30) for `iter_events`.
- The UI's `sessionId` must be at least 33 characters. `crypto.randomUUID()` gives 36.

### Known limits (demo shortcuts)

- **The Stop button stops the display, not the run.** Aborting the `fetch` closes the
  connection, but Lambda keeps running a streamed response and bills the full duration. The
  agent run also continues. Calling `StopRuntimeSession` from the relay would fix this; it is
  not needed for the demo.
- **SDK error events:** if the entrypoint raises an error, the SDK sends
  `{"error", "error_type", "message"}` as one more SSE event, which is not an `AgentEvent`.
  The browser client below turns it into a thrown error.
- **Local `next dev` has no `/api`:** keep the mock for local work, and test streaming against
  the CloudFront URL.

## Code sketch

### 1. Agent entrypoint: each `yield` becomes one SSE frame

```python
"""AskWRI agent entrypoint on AgentCore Runtime; streams AgentEvent dicts as they happen."""

from bedrock_agentcore.runtime import BedrockAgentCoreApp

app = BedrockAgentCoreApp()


@app.entrypoint
async def ask(payload):
    """Run one question in Quick or Deep mode, yielding step/source events, then one answer or decline."""
    question = payload.get("question")
    if not isinstance(question, str) or not question.strip():
        yield {
            "type": "decline",
            "decline": {"message": "Ask a question.", "searched": [], "related": []},
        }
        return
    yield {"type": "step", "id": "plan", "label": "Planning sub-questions", "status": "now"}
    async for event in research(payload):  # the agent loop, which yields AgentEvent dicts
        yield event


if __name__ == "__main__":
    app.run()
```

The SDK returns a `StreamingResponse` with `media_type="text/event-stream"` for an async
generator, and writes each yielded value as `data: <json.dumps(value)>\n\n`.

### 2. Relay: Lambda + Lambda Web Adapter, `relay.py`

```python
"""Streams AskWRI agent events from AgentCore Runtime to the browser as server-sent events."""

import json
import os

import boto3
from bedrock_agentcore.runtime.streaming import iter_events
from botocore.config import Config
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, StreamingResponse
from starlette.routing import Route

AGENT_RUNTIME_ARN = os.environ["AGENT_RUNTIME_ARN"]
# A retry would start a second agent run, and Deep research can go quiet for longer than the
# 60 s default read timeout.
agentcore = boto3.client(
    "bedrock-agentcore", config=Config(read_timeout=120, retries={"total_max_attempts": 1})
)


async def ask(request: Request):
    """Validate an AskRequest, invoke the agent, and relay its events as they arrive."""
    body = await request.json()
    question, session_id = body.get("question"), body.get("sessionId")
    if not (
        isinstance(question, str)
        and 0 < len(question) <= 2000
        and body.get("mode") in ("quick", "deep")
        and isinstance(session_id, str)
        and 33 <= len(session_id) <= 256
    ):
        return JSONResponse({"error": "invalid request"}, status_code=400)
    # Blocking here is fine: a Lambda environment serves one request at a time.
    response = agentcore.invoke_agent_runtime(
        agentRuntimeArn=AGENT_RUNTIME_ARN,
        runtimeSessionId=session_id,
        payload=json.dumps(body).encode(),
    )

    def frames():
        for event in iter_events(response):
            yield f"data: {json.dumps(event)}\n\n"

    return StreamingResponse(frames(), media_type="text/event-stream")


app = Starlette(routes=[Route("/api/ask", ask, methods=["POST"])])
```

`run.sh`, the function handler, copied from the LWA FastAPI zip example:

```bash
#!/bin/bash
PATH=$PATH:$LAMBDA_TASK_ROOT/bin \
    PYTHONPATH=$PYTHONPATH:/opt/python:$LAMBDA_RUNTIME_DIR \
    exec python -m uvicorn --port=$PORT relay:app
```

Dependency: `bedrock-agentcore>=1.25.2`. It already depends on `boto3`, `starlette` and
`uvicorn`, and the agent uses it too. Package Linux wheels into the zip (for example with
`uv pip install --target build --python-platform ...`), since `pydantic-core` is compiled.

### 3. Terraform (essentials only)

```hcl
resource "aws_lambda_function" "api" {
  function_name                  = "askwri-api"
  role                           = aws_iam_role.api.arn # InvokeAgentRuntime on the runtime + its DEFAULT endpoint
  runtime                        = "python3.12"
  architectures                  = ["arm64"]
  handler                        = "run.sh"
  filename                       = "build/askwri-api.zip"
  timeout                        = 120
  memory_size                    = 512
  reserved_concurrent_executions = 5
  layers                         = [var.lwa_layer_arn] # LambdaAdapterLayerArm64 version 30; ARN in the LWA README
  environment {
    variables = {
      AWS_LAMBDA_EXEC_WRAPPER = "/opt/bootstrap"
      AWS_LWA_INVOKE_MODE     = "response_stream"
      PORT                    = "8000"
      AGENT_RUNTIME_ARN       = var.agent_runtime_arn
    }
  }
}

resource "aws_lambda_function_url" "api" {
  function_name      = aws_lambda_function.api.function_name
  authorization_type = "AWS_IAM"
  invoke_mode        = "RESPONSE_STREAM"
}

# OAC needs both permissions.
resource "aws_lambda_permission" "cloudfront_url" {
  statement_id           = "AllowCloudFrontInvokeFunctionUrl"
  action                 = "lambda:InvokeFunctionUrl"
  function_name          = aws_lambda_function.api.function_name
  principal              = "cloudfront.amazonaws.com"
  source_arn             = aws_cloudfront_distribution.cdn.arn
  function_url_auth_type = "AWS_IAM"
}

resource "aws_lambda_permission" "cloudfront_invoke" {
  statement_id             = "AllowCloudFrontInvokeFunction"
  action                   = "lambda:InvokeFunction"
  function_name            = aws_lambda_function.api.function_name
  principal                = "cloudfront.amazonaws.com"
  source_arn               = aws_cloudfront_distribution.cdn.arn
  invoked_via_function_url = true
}

resource "aws_cloudfront_origin_access_control" "api" {
  name                              = "askwri-api"
  origin_access_control_origin_type = "lambda"
  signing_behavior                  = "always"
  signing_protocol                  = "sigv4"
}

# Add to the existing askwri-cdn distribution, next to the S3 origin:
#   origin {
#     origin_id                = "askwri-api"
#     domain_name              = trimsuffix(trimprefix(aws_lambda_function_url.api.function_url, "https://"), "/")
#     origin_access_control_id = aws_cloudfront_origin_access_control.api.id
#     custom_origin_config {
#       http_port              = 80
#       https_port             = 443
#       origin_protocol_policy = "https-only"
#       origin_ssl_protocols   = ["TLSv1.2"]
#       origin_read_timeout    = 60
#     }
#   }
#   ordered_cache_behavior {
#     path_pattern             = "/api/*"
#     target_origin_id         = "askwri-api"
#     viewer_protocol_policy   = "redirect-to-https"
#     allowed_methods          = ["GET", "HEAD", "OPTIONS", "PUT", "POST", "PATCH", "DELETE"]
#     cached_methods           = ["GET", "HEAD"]
#     cache_policy_id          = <Managed-CachingDisabled>
#     origin_request_policy_id = <Managed-AllViewerExceptHostHeader>
#   }
```

### 4. Browser: `ask()` in `web/src/lib/agent.ts`

```ts
async function* ask(request: AskRequest, signal: AbortSignal): AsyncIterable<AgentEvent> {
  const body = JSON.stringify(request);
  // CloudFront OAC signs POSTs to a Function URL only if the client sends the body hash.
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(body));
  const hash = Array.from(new Uint8Array(digest), (b) => b.toString(16).padStart(2, "0")).join("");
  const res = await fetch("/api/ask", {
    method: "POST",
    headers: { "content-type": "application/json", "x-amz-content-sha256": hash },
    body,
    signal,
  });
  if (!res.ok || !res.body) throw new Error(`Agent request failed: ${res.status}`);

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) return;
    buffer += value;
    const frames = buffer.split("\n\n");
    buffer = frames.pop() ?? "";
    for (const frame of frames) {
      if (!frame.startsWith("data: ")) continue;
      const event = JSON.parse(frame.slice(6));
      if ("error" in event) throw new Error(event.message); // SDK error event, not an AgentEvent
      yield event as AgentEvent;
    }
  }
}
```

`crypto.subtle` needs a secure context. The CloudFront URL is HTTPS and `localhost` also
counts as secure, so both work.

## Options compared

| Option | Streams to browser | Time limit | Python | CORS | Abuse control | Verdict |
| --- | --- | --- | --- | --- | --- | --- |
| **A. CloudFront `/api/*` → Function URL (OAC) → LWA relay** | Yes | Lambda up to 15 min; CloudFront 30 s default (60 s set) **between packets** | Yes, via LWA | None (same origin) | OAC + reserved concurrency (+ WAF) | **Use this** |
| B. Browser → Function URL directly (`NONE` auth) | Yes | Lambda up to 15 min | Yes, via LWA | Function URL `cors` block (`AllowOrigins` = CloudFront domain) | Reserved concurrency only; URL is public | Fallback |
| C. API Gateway REST API, `STREAM` transfer mode → Lambda | Yes (REST only) | 15 min stream; idle 5 min Regional, 30 s edge | Lambda must stream (LWA or Node) | Needed unless behind CloudFront | Usage plans, stage throttling, WAF | Works, but more resources than A for a demo |
| D. API Gateway HTTP API → Lambda | **No** | 30 s max integration timeout | Yes | Built-in | Throttling | Rejected: 60 s Deep research can't finish, nothing streams |
| E. API Gateway WebSocket → Lambda | Yes (push via `@connections`) | 29 s integration timeout, so an async worker is needed; 10 min idle, 2 h max | Yes | N/A | Throttling | Rejected: 3 routes, async worker and 128 KB message cap |
| F. Browser → AgentCore Runtime directly, Cognito JWT | Yes (SSE) | 15 min sync, 60 min stream | N/A (no relay) | Not documented; an AWS sample does it from CloudFront | None you control (account quotas: 1,000 TPS, 25 new sessions/s) | Rejected for a no-sign-in demo; the natural path once WRI adds auth |
| G. Lambda Web Function or Node.js `streamifyResponse` relay | Yes, natively | - | **No**: Web Functions are Node.js only | - | Endpoint RPS limits | Rejected: backend is Python |

Notes on F: the runtime accepts either IAM SigV4 or JWT, not both, so the team's boto3 tests
would need a separate runtime version. A token needs a sign-in, or a demo password shipped in
the bundle, which makes it public. Cognito identity pool guest credentials with SigV4 from the
browser avoid sign-in, but anyone can get them, there is still no throttle, and no doc covers
CORS for SigV4 headers on that endpoint.

## Facts and sources

### AgentCore Runtime entrypoint (Python `bedrock-agentcore` SDK)

- An entrypoint that is an async generator streams. AWS's example yields each event from
  `agent.stream_async(...)` ([Stream agent responses][ac-stream]).
- SDK source v1.25.3 (`runtime/app.py`): when the handler returns a generator or async
  generator, the SDK returns `StreamingResponse(..., media_type="text/event-stream")`.
  `_convert_to_sse` writes `f"data: {json_string}\n\n"`. An exception mid-stream yields
  `{"error", "error_type", "message"}` as a final event ([app.py][sdk-app]).
- HTTP contract: `POST /invocations` (JSON in, JSON or `text/event-stream` out), `GET /ping`
  (`Healthy` / `HealthyBusy`), host `0.0.0.0`, port 8080, ARM64 container. An optional `/ws`
  WebSocket path is also available ([HTTP protocol contract][ac-http]).
- Best practice: check that the prompt field is a `str` before passing it to the framework. A
  non-string value with a `toolUse` block can run a tool directly ([Invoke an agent][ac-invoke]).

### `InvokeAgentRuntime` through boto3

- Client `boto3.client("bedrock-agentcore")`. Parameters: `agentRuntimeArn` (or agent ID plus
  `accountId`), `runtimeSessionId`, `payload` (bytes), plus optional `qualifier`,
  `contentType` and `accept`. The response has `response` (a `StreamingBody`), `contentType`,
  `runtimeSessionId` and `statusCode` ([boto3 reference][boto3-invoke]).
- AWS's example checks `"text/event-stream" in response["contentType"]` and reads
  `response["response"].iter_lines(chunk_size=10)`, stripping `data: ` ([Invoke an agent][ac-invoke]).
- SDK v1.25.2+ adds `bedrock_agentcore.runtime.streaming.iter_events(response)`. Its docstring
  says `StreamingBody.iter_lines()` "reads in fixed size blocks and waits for each block to
  fill, so short events arrive together at the end". `iter_events` reads whatever bytes are
  available and yields each event's `data` parsed as JSON ([streaming.py][sdk-streaming]).
- `runtimeSessionId`: 33-256 characters. Payload up to 100,000,000 bytes. Errors: 400
  validation, 403 access denied, 424 container error, 429 throttling, 402 quota
  ([API reference][ac-api]).
- "If you plan on integrating your agent with OAuth, you can't use the AWS SDK to call
  `InvokeAgentRuntime`"; use HTTPS
  `POST https://bedrock-agentcore.<region>.amazonaws.com/runtimes/<url-encoded ARN>/invocations?qualifier=DEFAULT`
  with `Authorization: Bearer` ([OAuth][ac-oauth]).
- botocore defaults: `connect_timeout` 60 s, `read_timeout` 60 s. `total_max_attempts=1`
  means no retries ([botocore Config][botocore-config]).
- IAM: for `InvokeAgentRuntime`, "the identity-based policies attached to the calling principal
  must allow the action on both the agent runtime and agent endpoint resources"
  ([resource-based policies][ac-rbp]). AWS's example identity policy lists the runtime ARN and
  `<runtime ARN>/runtime-endpoint/DEFAULT` ([session endpoints][ac-session-endpoints]).

### AgentCore Runtime quotas ([quotas][ac-quotas])

| Quota | Value | Adjustable |
| --- | --- | --- |
| Request timeout (synchronous) | 15 minutes | No |
| Maximum payload (request/response) | 100 MB | No |
| Streaming chunk size | 10 MB | No |
| Streaming maximum duration (response streaming, WebSocket) | 60 minutes | No |
| Concurrent connections per session (incl. SSE streams) | 250 | No |
| Data plane API rate (InvokeAgentRuntime and others, per account) | 1,000 TPS | Yes |
| New session creation rate (per account) | 25 TPS | Yes |
| Active session workloads (us-west-2) | 5,000 | Yes |
| Idle session timeout | 15 minutes (`idleRuntimeSessionTimeout`) | Yes |
| Maximum session duration | 8 hours (`maxLifetime`) | Yes |

AgentCore Runtime (microVMs) and Memory are available in US West (Oregon)
([Regions][ac-regions]).

### Lambda response streaming and the Lambda Web Adapter

- "Lambda supports response streaming on Node.js managed runtimes. For other languages,
  including Python, you can use a custom runtime with a custom Runtime API integration to
  stream responses or use the Lambda Web Adapter." Streamed responses go up to 200 MB. The
  first 6 MB are uncapped, then the rate is capped at 2 MBps. Function URLs can't stream
  inside a VPC. "Streamed responses are not interrupted or stopped when the invoking client
  connection is broken", and you are billed for the full duration
  ([Lambda response streaming][lambda-rs]).
- Response streaming launched in US West (Oregon), among other regions
  ([2023 launch][lambda-rs-launch]).
- Lambda Web Functions, a newer offering, stream natively but "currently support Node.js
  runtimes only" ([Web Functions][lambda-web]).
- LWA, latest release v1.1.0 (2026-09-18), zip layer version 30
  (`LambdaAdapterLayerX86` / `LambdaAdapterLayerArm64`). To set it up: attach the layer, set
  `AWS_LAMBDA_EXEC_WRAPPER=/opt/bootstrap` and the handler to a startup script, and set
  `AWS_LWA_INVOKE_MODE=response_stream`. The port is `AWS_LWA_PORT`, falling back to `PORT`,
  default 8080. The readiness check is `GET /`, and any status from 100 to 499 counts as
  healthy ([LWA README][lwa]). The `fastapi-response-streaming-zip` example runs
  `python3.12` + `StreamingResponse` behind a Function URL with `InvokeMode: RESPONSE_STREAM`
  ([example][lwa-example]).
- Function URL CORS: `AllowOrigins`, `AllowMethods`, `AllowHeaders`, `ExposeHeaders`,
  `AllowCredentials`, `MaxAge`. For preflight requests, the URL's settings take precedence.
  On other requests, headers set by the function are duplicated, so configure CORS on the URL
  only. Reserved concurrency throttles a Function URL with HTTP 429; the maximum RPS is 10 x
  reserved concurrency, and 0 deactivates the URL ([Function URLs][lambda-urls]).
- You can reserve up to the account's unreserved concurrency minus 100. Reserved concurrency
  costs nothing ([reserved concurrency][lambda-concurrency]).

### CloudFront in front of a Function URL

- OAC for a Function URL origin needs `AuthType` `AWS_IAM`, plus `lambda:InvokeFunctionUrl`
  **and** `lambda:InvokeFunction` permissions for `cloudfront.amazonaws.com`, scoped to the
  distribution. "If you use PUT or POST methods with your Lambda function URL, your users must
  compute the SHA256 of the body and include the payload hash value of the request body in the
  `x-amz-content-sha256` header ... Lambda doesn't support unsigned payloads"
  ([OAC for Function URLs][cf-oac-lambda]).
- The origin response timeout covers both the wait for the first byte and "how long CloudFront
  waits after receiving a packet of a response from the origin and before receiving the next
  packet". The default is 30 s. CloudFront does not retry POST on timeout. "Response
  completion timeout" is an optional overall cap; if unset, there is none
  ([origin settings][cf-origin]). The quota page lists 1-120 s ([quotas][cf-quotas]). The
  Terraform docs say 60 s is the default upper limit ([Terraform][tf-cf]), so 60 is the safe
  setting.
- AWS's launch post: "You can progressively stream response payloads through Lambda function
  URLs, including as an Amazon CloudFront origin" ([blog][lambda-rs-blog]).
- *Community:* a spike PR ran three concurrent 90 s SSE streams through CloudFront and Function
  URLs with OAC, both behind LWA in response-streaming mode. Events arrived at most 1.0 s
  apart. Direct Function URL calls and POSTs without `x-amz-content-sha256` both returned 403,
  and every call failed until `lambda:InvokeFunction` was also granted ([PR][community-spike]).
  A community demo proxies AgentCore streams through a Node.js Lambda and computes the body
  hash in Lambda@Edge ([repo][community-agentcore-proxy]). This design computes the hash in the
  browser instead.

### API Gateway

- REST API response streaming: set the integration's transfer mode to `STREAM`. It works only
  with `HTTP_PROXY` / `AWS_PROXY` and "is only supported for REST APIs". Limits: up to 15
  minutes; idle timeout 5 min (Regional/private) or 30 s (edge-optimized); no endpoint
  caching, content encoding or VTL; first 10 MB uncapped, then 2 MB/s
  ([response streaming][apigw-stream]).
- For Lambda integrations, API Gateway calls `InvokeWithResponseStream`. The function must
  write a JSON metadata prelude, then 8 null bytes, then the payload
  ([Lambda streaming integration][apigw-stream-lambda]).
- HTTP API: maximum integration timeout 30 s, not adjustable ([HTTP API quotas][apigw-http]).
- WebSocket API: integration timeout 29 s, frame 32 KB, message 128 KB, idle timeout 10 min,
  maximum connection 2 h ([WebSocket quotas][apigw-ws]).
- Account throttle: 10,000 RPS, with a 5,000-request burst ([quotas][apigw-limits]).

### Browser calling AgentCore Runtime directly

- A JWT authorizer takes `discoveryUrl`, `allowedClients`, `allowedAudience`, `allowedScopes`
  and custom claims. "An AgentCore Runtime can support either IAM SigV4 or JWT Bearer Token
  based inbound auth, but not both simultaneously." The default Cognito token lifetime is 60
  minutes ([OAuth][ac-oauth]).
- CORS: AWS's documented fix (CORS middleware plus an `OPTIONS /invocations` handler in
  `BedrockAgentCoreApp`) is for "local development or self-hosted deployment"
  ([troubleshooting][ac-cors]). The deployed endpoint's CORS behavior isn't documented. The
  AWS sample `sample-amazon-bedrock-agentcore-fullstack-webapp` serves React from
  S3/CloudFront and `fetch`es
  `https://bedrock-agentcore.${region}.amazonaws.com/runtimes/.../invocations` with
  `Authorization: Bearer` and the session-ID header ([sample][sample-fullstack]).

### AWS WAF

- Rate-based rules: the evaluation window is 60, 120, 300 or 600 s, and the lowest rate limit
  is 10 ([WAF][waf-rate]).

[ac-stream]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/response-streaming.html
[ac-http]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-http-protocol-contract.html
[ac-invoke]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-invoke-agent.html
[ac-api]: https://docs.aws.amazon.com/bedrock-agentcore/latest/APIReference/API_InvokeAgentRuntime.html
[ac-oauth]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-oauth.html
[ac-rbp]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/resource-based-policies.html
[ac-session-endpoints]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/runtime-session-endpoints.html
[ac-quotas]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/bedrock-agentcore-limits.html
[ac-regions]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/agentcore-regions.html
[ac-cors]: https://docs.aws.amazon.com/bedrock-agentcore/latest/devguide/browser-tool-troubleshooting.html
[sdk-app]: https://github.com/aws/bedrock-agentcore-sdk-python/blob/v1.25.3/src/bedrock_agentcore/runtime/app.py
[sdk-streaming]: https://github.com/aws/bedrock-agentcore-sdk-python/blob/v1.25.3/src/bedrock_agentcore/runtime/streaming.py
[boto3-invoke]: https://docs.aws.amazon.com/boto3/latest/reference/services/bedrock-agentcore/client/invoke_agent_runtime.html
[botocore-config]: https://docs.aws.amazon.com/botocore/latest/reference/config.html
[lambda-rs]: https://docs.aws.amazon.com/lambda/latest/dg/configuration-response-streaming.html
[lambda-rs-launch]: https://aws.amazon.com/about-aws/whats-new/2023/04/aws-lambda-response-payload-streaming/
[lambda-rs-blog]: https://aws.amazon.com/blogs/compute/introducing-aws-lambda-response-streaming/
[lambda-web]: https://docs.aws.amazon.com/lambda/latest/dg/web-functions.html
[lambda-urls]: https://docs.aws.amazon.com/lambda/latest/dg/urls-configuration.html
[lambda-concurrency]: https://docs.aws.amazon.com/lambda/latest/dg/configuration-concurrency.html
[lwa]: https://github.com/awslabs/aws-lambda-web-adapter
[lwa-example]: https://github.com/awslabs/aws-lambda-web-adapter/tree/main/examples/fastapi-response-streaming-zip
[cf-oac-lambda]: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/private-content-restricting-access-to-lambda.html
[cf-origin]: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/DownloadDistValuesOrigin.html
[cf-quotas]: https://docs.aws.amazon.com/AmazonCloudFront/latest/DeveloperGuide/cloudfront-limits.html
[tf-cf]: https://registry.terraform.io/providers/hashicorp/aws/latest/docs/resources/cloudfront_distribution
[apigw-stream]: https://docs.aws.amazon.com/apigateway/latest/developerguide/response-transfer-mode.html
[apigw-stream-lambda]: https://docs.aws.amazon.com/apigateway/latest/developerguide/response-transfer-mode-lambda.html
[apigw-http]: https://docs.aws.amazon.com/apigateway/latest/developerguide/http-api-quotas.html
[apigw-ws]: https://docs.aws.amazon.com/apigateway/latest/developerguide/apigateway-execution-service-websocket-limits-table.html
[apigw-limits]: https://docs.aws.amazon.com/apigateway/latest/developerguide/limits.html
[sample-fullstack]: https://github.com/aws-samples/sample-amazon-bedrock-agentcore-fullstack-webapp
[waf-rate]: https://docs.aws.amazon.com/waf/latest/developerguide/waf-rule-statement-type-rate-based-high-level-settings.html
[community-spike]: https://github.com/CodeMIT-s-r-o/SmartDoc-AI/pull/4
[community-agentcore-proxy]: https://github.com/msysh/agentcore-and-lambda-stream-response
