# Ingestion 5: chart, map and image chunks

Owner: jayparmar16
Status: in-review
Issue: #7 (spec: #2)

## Goal

Answers that live only in figures become findable. Each informative picture (chart, map,
diagram) is rendered to a PNG and becomes its own chunk: the caption as content, a vision-model
description for search. The description is never quoted. Decorative pictures cost nothing.

## Done when

- [x] Picture regions under 2% of the page are skipped before any model call.
- [x] Caption pairing: nearest caption or `Figure N` / `Map N` / `Box N` heading on the same
      page. A captioned picture is informative; an uncaptioned one above the size limit gets a
      cheap decorative-or-informative check (`labeler`) first.
- [x] Each informative picture becomes a `chart` or `image` chunk: caption, `vision`
      description, figure number, PNG; not quotable; the audit checks the caption only.
- [x] Text inside a picture's region goes to the vision prompt and leaves the text chunks.
- [x] A scanned page (one picture covering most of a page, no text layer) is not described.
- [x] The PNG is uploaded to `figures/` in the corpus bucket and its key is `figure_key`.
- [x] PyMuPDF's picture placeholder text never reaches a text chunk.
- [x] A model refusal or error fails the document loudly.
- [x] The PR reports a live run on 3 chart-heavy reports.

## Handoff

None yet.
