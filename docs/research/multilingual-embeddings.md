# Multilingual embeddings and keyword search on Bedrock

Which embedding model and Postgres text search let questions in Spanish, Portuguese, French, Hindi or Indonesian find AskWRI's English passages (issue #33).

As of 2026-11-04. The facts come from AWS documentation and pricing data for US West (Oregon), Cohere documentation and PostgreSQL documentation, all listed under [Sources](#sources). Nothing was run against a live account, because no AWS credentials were available for this research.

## Recommendation

1. **Embed with Cohere Embed v4 at 1,024 dimensions.** From us-west-2, call it through the US inference profile `us.cohere.embed-v4:0`.
   - AWS says it covers over 100 languages, "delivers leading multilingual capabilities and shows notable improvements over Embed 3 across the key benchmarks". AWS describes Titan Text Embeddings V2 as "optimized for English" and says cross-language queries "will return sub-optimal results".
   - With `output_dimension: 1024`, the `vector(1024)` column and the HNSW cosine index from #12 stay as they are.
   - Its input limit, about 128K tokens, holds every chunk. Embed Multilingual v3 doesn't: it takes 512 tokens (about 2,048 characters) per text, while `Chunk.indexed_text` is the title › section address plus up to 2,000 characters of passage. Embed Multilingual v3 truncates at the end by default, so the ends of the longest chunks would drop out of their vectors without any error.
   - It costs $0.12 per million tokens and takes 96 texts per request.
   - **It needs a full re-embed.** Titan and Cohere vectors can't be compared, so every chunk is embedded again with `input_type: "search_document"`, and queries use `"search_query"`. Scaling up the chunk samples in PR #21 gives roughly 24,000–36,000 chunks and 6–9 million tokens: about $1 and fewer than 400 requests.
2. **Translate the question to English before keyword search, and keep #12's `english` tsvector.** The agent already writes the query for `search_passages()`. The tool description says the query must be in English, so the agent (the `answerer` role, Claude Sonnet 5.5) translates as it writes the call. This needs no extra model call and no schema change. The same English string goes to all three stages: it is embedded for meaning search, parsed with `english` for keyword search, and sent to the reranker.
3. **Keep Amazon Rerank 1.0.** After step 2 it only compares English queries with English passages. AWS publishes no language list for it. If a non-English query ever has to reach the reranker, switch the `reranker` role to Cohere Rerank 3.5 (`cohere.rerank-v3-5:0`). It uses the same Rerank API, runs in us-west-2, is documented for non-English languages, and costs $2.00 instead of $1.00 per 1,000 queries.
4. **Fallback if the re-embed can't land before the demo:** keep Titan V2 and still do step 2. Both searches then compare English with English, so questions in the five languages still work. What the multilingual model adds is meaning search that still works when a query isn't fully translated, such as a local programme name or a question passed straight to search.

### One-time setup before the first Cohere call

- Cohere models are sold through AWS Marketplace. The first call in the account starts the subscription. The identity making that call needs `aws-marketplace:Subscribe`, `aws-marketplace:Unsubscribe` and `aws-marketplace:ViewSubscriptions`, and setup can take up to 15 minutes. Make that first call from an admin identity well before the demo. Then run `aws bedrock get-foundation-model-availability --model-id cohere.embed-v4:0` and check that `agreementAvailability.status` is `AVAILABLE`. Do the same for Cohere Rerank 3.5 if you switch to it.
- The ingest and tools roles need `bedrock:InvokeModel` on the `us.cohere.embed-v4:0` inference profile in us-west-2. They also need it on the `cohere.embed-v4:0` foundation model in each Region the profile routes to: us-east-1, us-east-2 and us-west-2.

### What changes in #12 and #19

- In the registry (`askwri/models.py`), set `"embedder": "us.cohere.embed-v4:0"`. Both issues name Titan V2 in their acceptance criteria today.
- Index request body, with up to 96 texts per call:

  ```json
  {"texts": ["<indexed_text>", "..."], "input_type": "search_document", "output_dimension": 1024}
  ```

- Query request body:

  ```json
  {"texts": ["<English query>"], "input_type": "search_query", "output_dimension": 1024}
  ```

- Response when `embedding_types` is left out: `{"id": ..., "embeddings": [[1024 floats], ...], "response_type": "embeddings_floats", "texts": [...]}`. AWS's own sample code passes `embedding_types: ["float"]` and reads `embeddings` as a map keyed by type. So check `response_type` and raise on any other value.
- #19's single SQL statement stays the same; its text parameter is now English. One thing to check while building it: `plainto_tsquery` puts AND (`&`) between every remaining word. A whole question therefore only matches chunks that contain all of its words, and that holds in English too. An OR query ranks candidates better, for example `to_tsquery('simple', replace(plainto_tsquery('english', :q)::text, ' & ', ' | '))`. Re-parsing with `simple` leaves the already-stemmed lexemes unchanged. This sketch is mine, not from the docs, so test it on the cluster.

## Facts

### Embedding models on Bedrock, called from us-west-2

| | Titan Text Embeddings V2 | Cohere Embed Multilingual v3 | Cohere Embed v4 |
|---|---|---|---|
| Model ID | `amazon.titan-embed-text-v2:0` | `cohere.embed-multilingual-v3` | `cohere.embed-v4:0` |
| From us-west-2 | In-Region | In-Region | Not in-Region. US profile `us.cohere.embed-v4:0` (routes to us-east-1, us-east-2, us-west-2) or global profile `global.cohere.embed-v4:0` |
| Languages | "English (100+ languages in preview)". "Optimized for English … Cross-language queries … will return sub-optimal results" | "100+ languages for cross-lingual search and classification". Cohere's list includes es, pt, fr, hi and id | "Over 100 languages". "Leading multilingual capabilities and … notable improvements over Embed 3" |
| Dimensions | 1,024 (default), 512, 256 | 1,024 | 256, 512, 1,024, 1,536 (default) |
| Input limit | 8,192 tokens or 50,000 characters; one text per request | 512 tokens (about 2,048 characters) per text; up to 96 texts per request | About 128K tokens per input; up to 96 texts per request; about 20 MB per request |
| Over-long input | Not reached at our chunk sizes | `truncate`: `NONE` (error), `START`, `END` (default) | `truncate`: `NONE` (error), `LEFT`, `RIGHT` |
| Queries vs documents | Same call for both | `input_type`: `search_query` or `search_document` | Same as v3 |
| On-demand price, Oregon | $0.02 per 1M input tokens ($0.01 batch) | $0.10 per 1M input tokens | $0.12 per 1M input tokens |
| Sold through AWS Marketplace | No | Yes | Yes |
| Launched; lifecycle | 2024-04-30; Active | 2023-11-02; Active | 2025-04-15; Active |

InvokeModel request and response bodies:

- **Titan V2.** Request: `{"inputText": str, "dimensions": 1024|512|256, "normalize": bool (default true), "embeddingTypes": ["float"|"binary"]}`. Response: `{"embedding": [floats], "inputTextTokenCount": int, "embeddingsByType": {"float": [...]}}`.
- **Embed Multilingual v3.** Request: `{"texts": [str], "input_type": "search_document|search_query|classification|clustering", "truncate": "NONE|START|END", "embedding_types": [...]}`. Response: `{"embeddings": [[1024 floats]], "id": str, "response_type": "embeddings_floats", "texts": [str]}`.
- **Embed v4.** Request: `{"input_type": ..., "texts": [str], "embedding_types": ["float"|"int8"|"uint8"|"binary"|"ubinary"], "output_dimension": 256|512|1024|1536, "max_tokens": int, "truncate": "NONE|LEFT|RIGHT"}`. It also accepts `images` or interleaved `inputs` instead of `texts`. When one embedding type is requested, the response is `{"id", "embeddings": [[...]], "response_type": "embeddings_floats", "texts"}`. When several are requested, it is `{"embeddings": {"float": [[...]], "int8": [[...]]}, "response_type": "embeddings_by_type", ...}`.

Ruled out:

- Amazon Nova Multimodal Embeddings (`amazon.nova-2-multimodal-embeddings-v1:0`). Its model card lists only us-east-1 and GovCloud, with no cross-Region profile.
- Cohere Embed 5. Cohere lists it on its own API, SageMaker and other clouds. It is not in Bedrock's model list.

### Keyword search with non-English questions over English text

| Option | What it does | What it means for #19 |
|---|---|---|
| **Translate first (recommended)** | The agent writes the query in English. Keyword search uses the `english` tsvector and `plainto_tsquery('english', …)` as #12 and #19 already specify | No schema or SQL change. Stemming and stop words work the same as for English questions |
| `simple` configuration | Lower-cases each token and keeps it: no stemming, no stop words | A Spanish question shares only names, acronyms and numbers with English text, and only where the English stemmer leaves them unchanged. A `simple` tsquery against the `english` tsvector misses stemmed words, so this needs a second generated `simple` tsvector with its own GIN index. That is a schema change in #12, though no re-embed. If `simple` replaced `english`, English questions would lose stemming |
| One configuration per language | `to_tsquery('spanish', …)` and so on. PostgreSQL 18 ships `spanish`, `portuguese`, `french`, `hindi` (since 14) and `indonesian` (since 12) | Spanish words get Spanish stems, which never appear in an English tsvector. This only helps when the passages are in that language, and it needs the language of each question detected. No use for this corpus |
| Leave the question untranslated | `plainto_tsquery('english', <Spanish question>)` | No error is raised. The query ANDs Spanish words that never occur, so the keyword list comes back empty and the fusion falls back to vector search alone, with nothing to show that it happened |

- `infra/modules/database/main.tf` on `askwri-infra-backend` pins Aurora PostgreSQL 18.6. The configurations above are PostgreSQL built-ins.
- `db/schema.sql` on `askwri-infra-backend` builds its tsvector with `simple`, while #12 specifies `english`. #27 decides which one stays. This note recommends `english` together with translating first.

### Translating the query

- **Agent, when it writes the tool call (recommended).** This needs no extra call, because the `answerer` writes the search query anyway.
- **Amazon Translate `TranslateText`.** It covers es, pt, fr, hi and id to en, and `SourceLanguageCode: "auto"` detects the language (detection may be charged). It costs $15 per million characters, so a 100-character question costs $0.0015. It's only needed if something other than the agent sends raw non-English text to search.
- **Claude Haiku 5.5 (the `labeler` role) through `call_claude`.** This also works, at the cost of one more model call per search.

### Reranking

| | Amazon Rerank 1.0 | Cohere Rerank 3.5 |
|---|---|---|
| Model ID | `amazon.rerank-v1:0` | `cohere.rerank-v3-5:0` |
| us-west-2 | In-Region (not offered in us-east-1) | In-Region |
| Languages | Not documented by AWS: the reranking docs, the Rerank API launch post and the pricing page give no language list | Cohere: "Supports English and the same non-English languages as embed-multilingual-v3.0". AWS: "over 100 languages" |
| Price, Oregon | $1.00 per 1,000 queries | $2.00 per 1,000 queries |
| What counts as a query | Up to 100 document chunks, so 25 candidates count as one query | Same |
| Context | Not documented | 4K tokens for the query and document together; longer documents are chunked automatically |

Both go through the same Rerank API: `bedrock-agent-runtime` `rerank` with `queries`, `sources` and `rerankingConfiguration.bedrockRerankingConfiguration` (`modelConfiguration.modelArn`, `numberOfResults`). Switching models changes only the model ARN.

## Open checks

- **No live test.** This research had no AWS credentials. A 10-minute check once someone has them: embed one English passage, the same question in the five languages, and an unrelated English passage, using both Titan V2 and Embed v4. For each model, check that every translated question is closer to the matching passage than to the unrelated one. At the same time, confirm the Embed v4 response shape.
- **OR query.** Confirm the OR tsquery sketch above against the real `chunks` table.

## Sources

AWS, Amazon Bedrock:

- [Amazon Titan Text Embeddings models](https://docs.aws.amazon.com/bedrock/latest/userguide/titan-embedding-models.html): limits, language list, the "optimized for English" and cross-language wording
- [Titan Embeddings request and response](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-titan-embed-text.html)
- [Model card: Titan Text Embeddings V2](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-titan-text-embeddings-v2.html): Regions, lifecycle
- [Model card: Cohere Embed Multilingual](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-cohere-embed-multilingual.html): "cross-lingual search", Regions, 512-token context
- [Cohere Embed v3 request and response](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v3.html)
- [Model card: Cohere Embed v4](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-cohere-embed-v4.html): inference profiles and their destination Regions
- [Cohere Embed v4 request and response](https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-embed-v4.html)
- [Embed v4 on Bedrock announcement, 2025-10-02](https://aws.amazon.com/about-aws/whats-new/2025/10/coheres-embed-v4-multimodal-embeddings-bedrock/): "over 100 languages"
- [AWS ML blog: Cohere Embed 4 in Amazon Bedrock](https://aws.amazon.com/blogs/machine-learning/powering-enterprise-search-with-the-cohere-embed-4-multimodal-embeddings-model-in-amazon-bedrock/): "leading multilingual capabilities", improvements over Embed 3
- [Model card: Amazon Nova Multimodal Embeddings](https://docs.aws.amazon.com/bedrock/latest/userguide/model-card-amazon-amazon-nova-multimodal-embeddings.html)
- [Models at a glance](https://docs.aws.amazon.com/bedrock/latest/userguide/model-cards.html)
- [Amazon Bedrock pricing](https://aws.amazon.com/bedrock/pricing/): prices read for US West (Oregon) from the page's own price data
- [Request access to models](https://docs.aws.amazon.com/bedrock/latest/userguide/model-access.html): Marketplace subscription on first call
- [Prerequisites for inference profiles](https://docs.aws.amazon.com/bedrock/latest/userguide/inference-profiles-prereq.html): IAM on the profile and on the model in each destination Region
- [Supported Regions and models for reranking](https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-supported.html)
- [Use a reranker model](https://docs.aws.amazon.com/bedrock/latest/userguide/rerank-use.html)
- [AWS ML blog: Cohere Rerank 3.5 in Amazon Bedrock](https://aws.amazon.com/blogs/machine-learning/cohere-rerank-3-5-is-now-available-in-amazon-bedrock-through-rerank-api/)

AWS, Amazon Translate:

- [Supported languages](https://docs.aws.amazon.com/translate/latest/dg/what-is-languages.html)
- [Pricing](https://aws.amazon.com/translate/pricing/)

Cohere:

- [Models](https://docs.cohere.com/docs/models): Embed v4 dimensions and context, Rerank 3.5 languages
- [Embed](https://docs.cohere.com/docs/cohere-embed)
- [Supported languages](https://docs.cohere.com/docs/supported-languages)
- [Rerank](https://docs.cohere.com/docs/rerank)

PostgreSQL:

- [Controlling text search](https://www.postgresql.org/docs/current/textsearch-controls.html): `plainto_tsquery` uses AND, ranking, `setweight`
- [Dictionaries](https://www.postgresql.org/docs/current/textsearch-dictionaries.html): `simple` and Snowball
- [Text search introduction](https://www.postgresql.org/docs/current/textsearch-intro.html): configurations, `default_text_search_config`
- Release notes [12](https://www.postgresql.org/docs/release/12.0/) (Indonesian stemming) and [14](https://www.postgresql.org/docs/release/14.0/) (Hindi stemming)
- [`snowball_create.pl` on REL_18_STABLE](https://github.com/postgres/postgres/blob/REL_18_STABLE/src/backend/snowball/snowball_create.pl): the languages built into PostgreSQL 18
