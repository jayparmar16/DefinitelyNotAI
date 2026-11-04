# Fallback labels from the labeler model

Owner: jayparmar16
Status: in-review
Issue: #9 (spec: #2)

## Goal

Documents with no wri.org page (most RFPs and newsletters), and pages that give no usable
topic, still get labels. The `labeler` model reads the first pages and fills them in, and the
topic can only be one of WRI's 11 topics or `none`.

## Done when

- [x] When no wri.org page is found, the `labeler` role reads the first pages and returns, as
      structured output: title, date, document type, main topic, countries and a short summary.
- [x] The main topic must be one of Business, Cities, Climate, Economics, Energy, Equity,
      Finance, Food, Forests, Freshwater, Ocean, or `none`; any other value is rejected.
- [x] RFPs also get country and deadline.
- [x] The catalog row records the label source as `model`.
- [x] Tests use the fake model client.
- [x] Before falling back to the model, the title in the suggested-citation block is retried
      against the wri.org page found through the DOI (documents whose metadata title is
      unusable, such as "HIGHLIGHTS" or a file name).
- [x] Documents whose wri.org page gives no usable topic get their topic from the `labeler`,
      which must pick from the 11 topics or `none`.
- [x] Evidence on about 15 real documents is in the PR body.

## Notes

- RFPs get a `deadline`; their country goes in `countries` (no separate field). Every document the model labels
  also gets `doc_type`, `summary` and `topic_source` in the catalog row.
- A page that has labels but no usable topic keeps `label_source` = `wri.org`; the catalog's
  `topic_source` = `model` says the topic is the model's.
- No document in about 500 matched wri.org pages had an empty topic, so that path is covered by
  tests and by a live model call on two real pages, not by a real empty-topic page.

## Handoff

None yet.
