# AskWRI handoff

The state of AskWRI at the end of the hackathon (5 November 2026), what is known to be
imperfect, and what to do next. Read the [README](../README.md) first, then
[PROJECT-OVERVIEW.md](PROJECT-OVERVIEW.md) for why things are the way they are.

## What is live

| What | Where |
|---|---|
| Web app (invite only) | https://d17gz0gh5g00t3.cloudfront.net |
| Admin page (`askwri-admins` group) | https://d17gz0gh5g00t3.cloudfront.net/admin/ |
| Code | branch `release-branch` (the full system: ingestion, agent, tools, API, UI, evaluation, infrastructure) |
| AWS | one team account, us-west-2; every resource named `askwri-*` and tagged `Project = AskWRI` (resource group `askwri-rg`) |
| Library | 577 of 580 kept publications loaded (3 skipped: a pitch deck whose image the model rejected, two tax forms that failed the audit) |
| Official evaluation run | `20261105-050756` (shown on the admin page) |

`release-branch` is what `main` should become; it has not been merged into `main` yet.

## How to operate it

| Task | How |
|---|---|
| Add a person or an admin | [REPRODUCE.md, step 8](REPRODUCE.md#8-add-people) |
| Add new WRI publications | Put the PDFs in a year folder and run the loader ([step 6](REPRODUCE.md#6-load-the-library)); it skips what is already loaded. Then rebuild links and republish the site (for the topic counts). |
| Change the agent, tools or API | Edit, run the tests, rebuild the package (`infra/build/*.sh`), `terraform plan -out=...`, review, apply |
| Change the website | `scripts/deploy-web.sh` |
| Check quality after a change | `eval/run_eval.py run`, then `judge` ([step 9](REPRODUCE.md#9-evaluate)). Keep experiments out of `eval/results/` in S3: the admin page shows the newest file there. |
| Watch cost and usage | Admin page → Cost and usage; CloudWatch dashboard (`terraform output quality_dashboard`) |
| Investigate one bad answer | Admin page → Highest-cost requests → review; or the trace in CloudWatch GenAI Observability |
| Before a demo | Set `db_min_capacity = 0.5` (Aurora otherwise pauses and takes 15–30 s to wake); ask one question to warm the agent; load demo chats with `/?demo=load` |

## Known issues

1. **Duplicate documents.** 45 titles are filed more than once (61 extra copies of 579): the
   same report under different file names with different hashes. Search then cites one copy or
   the other at random, source lists can show the same report twice, and the evaluation's
   recall swings between runs. Fix in the sort step (`askwri/ingest/`, owner: Jay), and in the
   meantime let the test set accept any copy.
2. **Occasional wrong declines.** One or two answerable test questions per run are declined
   although search ranks the right passage first (rerank 0.91–0.98). Which ones changes per run.
   Likely cause: the draft prompt's rule to mark passages that "only touch the topic in passing"
   as not answerable. Next step: test with and without that rule, and don't decline on the
   draft's verdict when the top passage scores very high.
3. **Faithfulness judge varies around its target.** 0.82 in the official run, 0.78 in a rerun.
   The judge is stricter than our claim check about paraphrase and sentences that combine
   passages.
4. **Evaluation metrics are optimistic in places.** Recall skips declined questions (about 85%
   if they count as misses) and precision assumes one correct report per question. Planned:
   count declines as misses, measure recall on raw search results, and judge precision with a
   model. See [evaluation-spec.md](evaluation-spec.md).
5. **Metadata gaps.** Authors and abstracts come from wri.org pages, matched for about a third
   of publications (authors for 187). Reading them from each PDF's front pages is the next step.
6. **Small evaluation set.** 30 questions, partly model-written. Add WRI's own questions in the
   same format (`eval/testset.jsonl`).
7. **Model choice for the agent's small tasks.** The agent uses Claude Haiku 4.5 because Haiku
   5.5 needed a Marketplace subscription the sandbox couldn't make (`small_model_id` in
   `infra/variables.tf`); ingestion uses Haiku 5.5.
8. **Ingestion runs from a laptop.** The loader is one resumable command, not yet an automated
   job when new PDFs arrive (an S3-triggered Lambda per PDF was designed but not built).

## Next steps, by value

1. Remove duplicate documents (sort step) and accept duplicates in the test set.
2. Fix the wrong declines (item 2) and re-run the evaluation.
3. Honest metrics: declines as misses, search-based recall, judged precision.
4. Automatic loading of new WRI publications.
5. Feedback buttons in the UI feeding the admin page, and WRI staff reviewing a sample.
6. Authors and abstracts from the PDFs.
7. Stream the answer text as it is written, to cut the perceived wait.
8. Access rules per user, if internal documents are added.

## Rules for working on it

- Work on a branch; changes reach `main` through a pull request ([AGENTS.md](../AGENTS.md)).
- One AWS account only, us-west-2. Always `terraform plan -out=...`, read it, then apply that plan.
- The repository is public: no account IDs, ARNs, secrets or personal emails in committed files.
  A commit hook blocks secrets; never bypass it.
- Don't rename the Cognito pools, domain or gateway: replacing them issues new IDs and secrets.
- Run `npm run lint` (type check) as well as the tests before publishing the website; the
  production build fails on type errors.

## Where the history is

- [tasks/](tasks/): one file per task with its goal, decisions and handoff notes.
- [askwri-solution-design.md](askwri-solution-design.md): the original design and plan.
- Git history on `release-branch`; the merge commits name the branches each part came from.
