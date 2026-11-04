# Load the corpus into Aurora, creating AWS resources on the first run

Owner: jayparmar16
Status: in-review
Issue: #12 (and the demo cut of #11)

## Goal

One command that creates the AWS resources if they are missing, applies the #27 schema and
loads every kept PDF into Aurora with Cohere Embed v4 embeddings, for the 5 Nov demo.

## Done when

- [x] `scripts/run-pipeline.sh` creates the state bucket and runs Terraform when Aurora or the
      corpus bucket is missing, then applies the schema and runs the load.
- [x] The load sorts, ingests, uploads each PDF to S3, embeds with Cohere v4 and replaces each
      document's rows in one Data API transaction; reruns skip unchanged documents.
- [x] Tests cover chunk-to-row mapping and the replace and rollback behaviour.
- [x] A live run on 3 PDFs loads them, and a hybrid query with a year filter returns cited chunks.

## Notes

- Deferred until after the demo: #11's JSON Lines files, parse caching and run report.

## Handoff

None yet.
