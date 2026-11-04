# DefinitelyNotAI

AskWRI: a research assistant that answers questions from World Resources Institute
publications, with a citation for every claim. Built on Amazon Bedrock and AgentCore for an
AWS hackathon.

## Get started

1. Install [Claude Code](https://docs.claude.com/en/docs/claude-code) or [Codex](https://developers.openai.com/codex).
   Either works, and teammates can mix them.
2. Clone the repo and open your AI tool in it:

   ```sh
   git clone https://github.com/jayparmar16/DefinitelyNotAI.git
   cd DefinitelyNotAI
   claude        # or: codex
   ```

3. Type **`/setup`** (Claude Code) or **`$setup`** (Codex) and do what it says until
   every line says PASS.

## Every task

| When you want to | Claude Code | Codex |
|---|---|---|
| Start a task | `/claim-task` | `$claim-task` |
| Stop before it's done | `/handoff` | `$handoff` |
| Check your code | `/review` | `$review` |
| Finish and open a PR | `/create-pr` | `$create-pr` |

You can also just say it in plain words, e.g. "claim a task for PDF ingestion" or "open a PR".

## Ingest PDFs locally

The ingestion pipeline (spec: issue #2) turns WRI PDFs into audited, citable chunks.

```sh
uv sync                                   # install Python dependencies
uv run pytest                             # run the tests
uv run python -m askwri.ingest path/to/report.pdf --out chunks/
```

For each PDF the command writes one `.txt` file per chunk, plus the `.metadata.json` sidecar
that Bedrock Knowledge Bases reads, under `chunks/<doc_id>/`. Before anything is written,
the citation audit checks every chunk against the PDF's own text layer:

- **Blocked:** a chunk that is empty, garbled, or has words that aren't on its page. Nothing
  is written for that PDF, and the command exits with an error.
- **Not quotable:** a chunk whose words are all on its page, but in a different order (for
  example diagram labels). It is written with `quotable: false`, so answers can cite its
  page but never quote it word for word.

## Deploy to AWS

Everything deploys with Terraform into **one team sandbox account** in us-west-2, following
[the solution design](docs/askwri-solution-design.md) ("AWS deployment layout"). Teammates'
sandboxes are for local experiments only: Terraform refuses any account other than
`TF_VAR_team_account_id`. Needs Terraform 1.11+ (`brew install hashicorp/tap/terraform`).

```sh
export AWS_PROFILE=<team sandbox profile> AWS_REGION=us-west-2
export TF_VAR_team_account_id=$(aws sts get-caller-identity --query Account --output text)

infra/bootstrap/create-state-bucket.sh        # once: S3 state bucket, writes infra/backend.hcl
cp infra/terraform.tfvars.example infra/terraform.tfvars   # once: set the Team and Owner tags
cd infra && terraform init -backend-config=backend.hcl
terraform plan -out=plan.tfplan && terraform apply plan.tfplan
cd .. && uv run python db/apply_schema.py     # tables, indexes and database users
```

`backend.hcl` and `terraform.tfvars` hold account-specific values and are gitignored; never
commit the account ID or ARNs. Sandbox credentials expire: on `ExpiredToken`, refresh them
before planning again.

`db/apply_schema.py` uses the RDS Data API, so it also runs from CloudShell without VPC access.
It is safe to rerun.

| Resource | Name | Notes |
|---|---|---|
| VPC | `askwri-vpc` (10.20.0.0/16) | Private subnets `askwri-app-a/b` and `askwri-db-a/b`; no internet route, no NAT |
| VPC endpoints | `askwri-vpce-*` | S3 (gateway), bedrock-runtime, bedrock-agent-runtime, secretsmanager, logs |
| Security groups | `askwri-sg-lambda`, `askwri-sg-db`, `askwri-sg-endpoints` | Only Lambda to Aurora (5432) and Lambda to endpoints/S3 (443) |
| Corpus bucket | `askwri-corpus-<account-id>` | `raw/` PDFs, `text/`, `eval/`; private, encrypted, TLS only; objects readable only by the deploy role and the askwri-* roles |
| Database | `askwri-db` | Aurora PostgreSQL 18 Serverless v2 with pgvector; Data API on; pauses after an hour idle (resume takes 15 s or more; set `db_min_capacity = 0.5` for demos) |
| Secret | `askwri/db` | Master credentials, used only by the Data API. Lambdas sign in with IAM database auth as `askwri_ingest` or `askwri_tools` |
| Resource group | `askwri-rg` | Lists every resource tagged `Project = AskWRI` |

Interface endpoints and Aurora bill by the hour. After the event, tear everything down with
`cd infra && terraform destroy`, then check that `askwri-rg` is empty.

## Chat UI (`web/`)

A Next.js app built from the AskWRI design system (WRI Design System colors and spacing): one
search box with a Deep research toggle, answers with `[n]` citation markers, source cards, a
side panel with the report or the source at its cited page, and the helpful decline. It builds
to static files for S3 + CloudFront. Needs Node 22+.

```sh
cd web
npm install
npm run dev        # http://localhost:3000
npm test           # citation, export and mock-data checks (Node's built-in test runner)
npm run lint       # type check
npm run build      # static site in web/out/
```

**Mock agent.** Until the API exists (runbook phase 5), the UI talks to a mock in
`web/src/mock/` and shows a "Mock data" badge. Its titles, authors and figures are
placeholders, not real WRI publications. Questions about transport (buses, transit, BRT) get a
cited answer, or a streamed report with Deep research on; anything else gets the decline;
"Now make it in Spanish" after a report reuses it, machine-translated. Everything goes through
the contract in `web/src/lib/agent.ts`.

**Real agent.** Put the API's URL and key in `web/.env.local` (gitignored) and restart
`npm run dev`; the "Mock data" badge disappears:

```sh
NEXT_PUBLIC_ASKWRI_API_URL=<terraform output api_url>
NEXT_PUBLIC_ASKWRI_API_KEY=<value of the askwri/api-key secret>
```

Get them with `terraform -chdir=infra output -raw api_url` and
`aws secretsmanager get-secret-value --secret-id askwri/api-key --query SecretString --output text`.
The API allows browser calls from `http://localhost:3000` only (Terraform `allowed_origins`).
Without the URL the UI uses the mock; delete `web/src/mock/` when it is no longer wanted.

## The rules

- `main` is protected, so every change goes in through a pull request.
- Write only the code the task needs. `review` flags anything extra.
- Commits that contain secrets are blocked.
- Your own AI tool settings stay on your machine (git ignores them).

The full rules for people and agents are in [AGENTS.md](AGENTS.md).

## FAQ

**`/setup` shows FAIL lines.**
Each FAIL line prints its fix. Your AI runs the fixes it can. Logins you have to run
yourself (in Claude Code, type the command with a `!` in front, e.g.
`! gh auth refresh --scopes repo,workflow`). Then run `/setup` again.

**Push fails with "Permission denied" or 403.**
You aren't a collaborator yet. Send your GitHub username to the repo owner (jayparmar16).

**Push to `main` fails with "protected branch".**
That's expected: work goes on a branch. Move your commits to a new branch, then reset your
local `main`:
`git switch -c my-task && git branch -f main origin/main`

**How do I see who's working on what?**
Each open draft PR is a task someone has claimed. Run `gh pr list` or open the Pull
requests tab.

**How do I take over a task someone handed off?**
Run `/claim-task` and name the PR. Their notes are under "Handoff" in
`docs/tasks/<branch>.md`.

**My commit was blocked by "Detect hardcoded secrets".**
Take the secret out of the file. Put it in `.env` (ignored by git) or your AWS profile, then
commit again. If it was already pushed, rotate it. Don't use `--no-verify`.

**My commit failed with "files were modified by this hook".**
ruff fixed the formatting for you. Run `git add` on those files and commit again.

**"check for added large files" failed.**
Documents and data go in S3, not git.

**`/create-pr` stopped because review found "hard" issues.**
Ask your AI to fix them, then run `/create-pr` again. If you think a finding is wrong, say
why and tell it to go ahead.

**`main` changed while I was working.**
`/create-pr` merges the latest `main` into your branch. If there are conflicts, it works
through them with you.

**How does my PR get merged?**
A teammate (or you) reads it on GitHub and clicks Merge. AI agents never merge.

**Can I change my own Claude or Codex settings, MCP servers, or add personal skills?**
Yes. Put them in `CLAUDE.local.md`, `AGENTS.override.md`, `.claude/settings*.json`,
`.mcp.json`, `.codex/`, or your home folder (`~/.claude`, `~/.codex`). Git ignores all of
these. Changes to the shared skills or `AGENTS.md` go through a PR.

**AWS says "Unable to locate credentials" or "ExpiredToken".**
Sandbox credentials expire. Run `aws sso login`, or export fresh sandbox credentials, then
run `/setup` again.

**Bedrock says a model isn't available in my region.**
Use the model's cross-region inference profile ID (it starts with `us.`, `eu.` or
`global.`) instead of the plain model ID.

**I'm on Windows and the skills don't show up in Claude Code.**
`.claude/skills` is a symlink, which Windows only creates if Developer Mode is on. Turn on
Developer Mode, run `git config --global core.symlinks true`, and clone again. Or use WSL.
