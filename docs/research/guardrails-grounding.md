# Bedrock Guardrails grounding check for cited answers

Research for issue #35. Facts are as of **2026-11-04** and come from the AWS Bedrock User
Guide, API reference, service quotas, pricing page and the botocore 1.43.123 service model
pinned in `uv.lock`. Nothing here was measured live: this session had no AWS credentials.

## Recommendation

**Use it as a second layer that checks each sentence, after our deterministic citation check.**

1. Our deterministic check runs first and stays the only check on markers and verbatim quotes.
2. Make one `ApplyGuardrail` call for each sentence that survives it, all in parallel (a thread
   pool). Each call gets:
   - that sentence's cited passages, one `grounding_source` block per passage
   - the user question as `query`, cut to 1,000 characters
   - the sentence with its `[n]` markers stripped, as `guard_content`
3. Drop a sentence when its GROUNDING score is **below 0.7**, AWS's suggested starting point
   for Standard tier. Then reuse the existing "too little survives" decline.
4. Configure the guardrail as follows:
   - **Standard tier**, using guardrail profile `us.guardrail.v1:0`.
   - **GROUNDING filter only**, with action `NONE`. Relevance stays off when checking one
     sentence at a time: a sentence that only sets context can be grounded yet not answer the
     question by itself.
   - Call with `outputScope="FULL"` so the score comes back even when it passes.
   - Compare the score against a constant in our code. That makes tuning a one-line change and
     needs no guardrail update.
5. Calibrate before the demo. Log scores for about 10 real answers. If faithful paraphrases
   score below 0.7, lower the threshold to 0.5.
6. Budget for a typical answer (6 sentences, 6 passages, 1–2 citations per sentence):
   - about 18 text units, so about **$0.002 per answer** (worst case about $0.004)
   - wall time of about one call, because the calls run in parallel. AWS publishes no latency
     figure, so measure it from `guardrailProcessingLatency`.
7. If the guardrail or its IAM permissions aren't ready in time, or calls are slow, ship with
   the deterministic check alone. The layer only adds checks, so nothing else depends on it.

Why one call per sentence rather than one per answer: a call returns **one** grounding score for
everything it guards. A single call for the whole answer can't say which sentence failed. It
also can't catch a sentence whose citation points at the wrong passage, because all passages
are merged into one source.

## How to call it standalone

You need a guardrail resource first. `ApplyGuardrail` takes `guardrailIdentifier`,
`guardrailVersion` (a number or `DRAFT`), `source` and `content`, plus an optional
`outputScope` ([ApplyGuardrail API][apply-api]). The inline-check API `InvokeGuardrailChecks`
only offers content filters, prompt attack and sensitive information. It has **no grounding
check** (botocore service model).

Create the guardrail once in us-west-2, from the console or with boto3's `bedrock` client.
`CreateGuardrail` requires `name`, `blockedInputMessaging` and `blockedOutputsMessaging`
([grounding guide][cg]):

```python
bedrock.create_guardrail(
    name="askwri-grounding",
    blockedInputMessaging="Blocked.",
    blockedOutputsMessaging="Blocked.",
    contextualGroundingPolicyConfig={
        "filtersConfig": [
            {"type": "GROUNDING", "threshold": 0.7, "action": "NONE", "enabled": True}
        ],
        "tierConfig": {"tierName": "STANDARD"},
    },
    crossRegionConfig={"guardrailProfileIdentifier": "us.guardrail.v1:0"},
)
```

The pinned botocore 1.43.123 already has `tierConfig` on the grounding policy.

Then make one call per sentence:

```python
content = [{"text": {"text": p, "qualifiers": ["grounding_source"]}} for p in cited_passages]
content += [
    {"text": {"text": question[:1000], "qualifiers": ["query"]}},
    {"text": {"text": sentence_without_markers, "qualifiers": ["guard_content"]}},
]
resp = runtime.apply_guardrail(
    guardrailIdentifier=guardrail_id,
    guardrailVersion="DRAFT",
    source="OUTPUT",
    content=content,
    outputScope="FULL",
)
filters = resp["assessments"][0]["contextualGroundingPolicy"]["filters"]
score = next(f["score"] for f in filters if f["type"] == "GROUNDING")
```

How the qualifiers work ([grounding guide][cg]):

- Blocks qualified `grounding_source` or `query` are used only by the grounding check.
- A block that is unqualified or qualified `guard_content` is "the content to be guarded",
  which stands in for the model response.
- The grounding check needs all three parts.
- The check runs only on output.

What you need in IAM ([guardrail profile permissions][perm]):

- `bedrock:ApplyGuardrail` on the guardrail.
- `bedrock:ApplyGuardrail` on `guardrail-profile/us.guardrail.v1:0` in every destination
  Region. From us-west-2, the destinations are us-east-1, us-east-2 and us-west-2
  ([profiles][xr-support]).
- Requests may run in any of those Regions, but they stay within the US
  ([cross-Region][xr]).

## What it scores and how thresholds work

- **Grounding:** whether the response "is factually accurate based on the source and is
  grounded in the source. Any new information introduced in the response will be considered
  un-grounded." ([grounding guide][cg])
- **Relevance:** whether the response is relevant to the query. A grounded sentence that
  doesn't answer the question scores low ([grounding guide][cg]).
- **Scores** are 0 to 1. You can set thresholds from 0 to 0.99; 1 is invalid. Below the
  threshold counts as `detected`. AWS says 0.7 for both is "a reasonable starting point" for
  Standard tier ([grounding guide][cg]). The 2024 launch post used 0.85 for grounding and 0.5
  for relevance on Classic tier ([launch blog][blog]).
- **Filters** are configured separately as `GROUNDING` and `RELEVANCE`, each with action
  `BLOCK` or `NONE`. A disabled filter isn't evaluated or charged
  ([filter config][filter-cfg]).

## What the response says

For each assessment, `contextualGroundingPolicy.filters[]` holds `type`, `threshold`, `score`,
`action` (`BLOCKED` or `NONE`) and `detected` ([filter shape][filter]).

Other fields ([ApplyGuardrail API][apply-api]):

- `action` at the top level is `GUARDRAIL_INTERVENED` or `NONE`.
- `usage.contextualGroundingPolicyUnits` gives the billed units.
- `assessments[].invocationMetrics.guardrailProcessingLatency` gives the processing time.

By default only detected items come back; `outputScope="FULL"` also returns the ones that pass
([ApplyGuardrail guide][apply-guide]).

## Limits

| What | Limit | Source |
|---|---|---|
| Grounding source | 100,000 chars. 100 text units in us-west-2 and us-east-1; 50 in other Regions. Not adjustable. | [grounding guide][cg], [quotas][quotas] |
| Query | 1,000 chars (1 text unit), not adjustable | same |
| Content to guard | 5,000 chars (5 text units), not adjustable | same |
| Whole input per call | 106 text units | [quotas][quotas] |
| Grounding throughput | 106 text units/s, burst 106, each Region; adjustable | [quotas][quotas] |
| ApplyGuardrail rate | 100 requests/s in us-west-2; adjustable | [quotas][quotas] |

The 5,000-character cap on guarded content means a long briefing can't be checked in one call
anyway. The docs don't say whether input over a limit errors or gets truncated, so enforce the
limits in our code.

## Price

The contextual grounding check costs **$0.10 per 1,000 text units**, the same on both tiers.

- A text unit is up to 1,000 characters.
- Units are counted over "all the characters in the source, query, and model response"
  combined ([pricing][pricing]).

Worked numbers for a typical answer. Chunks are 400 to 2,000 characters
(`askwri/ingest/chunks.py`); assume 1,500. Sentences are about 200 characters and questions
about 150.

| Approach | Units for each call | Calls | Units for each answer | Cost for each answer |
|---|---|---|---|---|
| One call per sentence, 1–2 cited passages each | 2–4 | 6 | ~18 | ~$0.0018 |
| The same, worst case (two 2,000-character passages, 1,000-character query) | 6 | 6 | 36 | $0.0036 |
| One call per sentence, all 6 passages each (don't do this) | 10 | 6 | 60 | $0.006 |
| One call for the whole answer | 11 | 1 | 11 | $0.0011 |

At about 18 units per answer, the 106-units-per-second quota allows about 5 checked answers per
second across the account. That is plenty for a demo.

## Latency

AWS publishes no latency figure. The grounding guide, pricing page, launch post and the
2026-10-20 Standard-tier announcement give none. Each response reports
`guardrailProcessingLatency`, so log it from the first call. Running the calls in parallel keeps
wall time to about the slowest single call. Standard tier routes through cross-Region inference;
whether that adds latency is not documented.

## Region and tiers

- us-west-2 supports Guardrails and safeguard tiers. It is also one of the 11 Regions with
  **Standard tier for contextual grounding** ([tiers][tiers]).
- Standard tier for grounding launched on 2026-10-20 ([what's new][whatsnew]). It requires
  cross-Region inference with a guardrail profile. If you set it in an unsupported Region, the
  request fails with a validation error ([tiers][tiers]).
- If you don't specify a tier, you get Classic. `UpdateGuardrail` without `tierConfig` resets
  the tier to Classic ([grounding guide][cg]).
- Classic tier supports English, French and Spanish. Standard tier supports many more
  languages, which matters if the corpus includes Portuguese WRI Brasil documents
  ([tiers][tiers]).

## One sentence at a time, or only the whole answer?

- **One call gives one grounding score and one relevance score.** The response has one filter
  for each type. AWS documents no scores for individual blocks or sentences.
- With multiple `grounding_source` blocks, the guardrail "combines and evaluates all the
  provided `grounding_source` values together". The same goes for multiple `query` blocks
  ([grounding guide][cg]).
- Within a single response, "if any one chunk is deemed relevant, the whole response is
  considered relevant" ([grounding guide][cg]). So a call for the whole answer would hide an
  off-topic sentence.
- There is no batch API, so a verdict for each sentence takes one call for each sentence, run in
  parallel.
- Passing only a sentence's cited passages also checks that the citation is right. A true
  sentence that cites the wrong chunk fails.
- One caveat, my inference: a sentence that leans on the one before it ("This doubled by 2030")
  is judged without that context and may score low. Include such sentences in the calibration
  set.

## Paraphrase, numbers and quotes

- **Paraphrase:**
  - Classic tier is strict. "Any information in the response that is not stated in the
    grounding source lowers the grounding score, including reasonable inferences and
    conversational phrasing."
  - Standard tier "returns more consistent scores for differently worded responses that have
    the same meaning" and handles reasoning ([grounding guide][cg]).
  - That is the reason to pick Standard tier for summarised research.
- **Numbers:** the only documented case is a figure attached to the wrong claim. A source
  says 23.99% is the late-payment charge; a response gives 23.99% as the credit-card
  transaction charge. AWS rates that response ungrounded ([grounding guide][cg]). Nothing
  covers rounding, unit conversion or derived figures ("nearly a quarter"). Test these during
  calibration.
- **Quotes:** nothing is documented. It is a semantic score, not a string match, so our
  deterministic check stays the only verbatim-quote check.
- **Accuracy claim:** AWS says it "filters over 75% hallucinated responses for RAG and
  summarization workloads", with no method or dataset given ([launch blog][blog]). Expect it to
  miss some.

## Sources

All read on 2026-11-04.

- [Contextual grounding check guide][cg]
- [ApplyGuardrail API reference][apply-api] and [ApplyGuardrail user guide][apply-guide]
- [GuardrailContextualGroundingFilter][filter] and [GuardrailContextualGroundingFilterConfig][filter-cfg]
- [Amazon Bedrock service quotas][quotas]
- [Amazon Bedrock pricing][pricing]
- [Safeguard tiers][tiers]
- [Cross-Region guardrail inference][xr], [guardrail profiles][xr-support] and [their IAM permissions][perm]
- [Standard tier for grounding announcement, 2026-10-20][whatsnew]
- [Grounding check launch blog, 2024][blog]
- botocore 1.43.123 service models for `bedrock` and `bedrock-runtime`, as pinned in `uv.lock`

[cg]: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-contextual-grounding-check.html
[apply-api]: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_ApplyGuardrail.html
[apply-guide]: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-use-independent-api.html
[filter]: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_runtime_GuardrailContextualGroundingFilter.html
[filter-cfg]: https://docs.aws.amazon.com/bedrock/latest/APIReference/API_GuardrailContextualGroundingFilterConfig.html
[quotas]: https://docs.aws.amazon.com/general/latest/gr/bedrock.html
[pricing]: https://aws.amazon.com/bedrock/pricing/
[tiers]: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-tiers.html
[xr]: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-cross-region.html
[xr-support]: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrails-cross-region-support.html
[perm]: https://docs.aws.amazon.com/bedrock/latest/userguide/guardrail-profiles-permissions.html
[whatsnew]: https://aws.amazon.com/about-aws/whats-new/2026/10/bedrock-guardrails-grounding-standard/
[blog]: https://aws.amazon.com/blogs/aws/guardrails-for-amazon-bedrock-can-now-detect-hallucinations-and-safeguard-apps-built-using-custom-or-third-party-fms/
