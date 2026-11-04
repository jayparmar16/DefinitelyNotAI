# DefinitelyNotAI

Hackathon project: **AskWRI**, an agentic research assistant for the World Resources Institute.
It answers questions and writes briefings from WRI's published research. Every claim cites a
WRI source (title, link, passage), and it says so when the corpus has no answer.

This file is the single source of instructions for every AI coding tool and every human.
Claude Code reads it through `CLAUDE.md`; Codex reads it directly.

## Stack

- AWS only: Amazon Bedrock (models, embeddings, rerank), Aurora PostgreSQL with pgvector (the
  search index; retrieval is our own code, not Bedrock Knowledge Bases), Bedrock AgentCore, S3.
  Lambda or ECS Fargate when compute is needed.
- Python 3.12+, managed with `uv`. Lint and format with `ruff`.
- TypeScript only for UI or infrastructure code.

## Workflow

Every change goes through these skills. Claude Code: `/name`. Codex: `$name`.

1. `setup`: once per machine, and whenever git, gh or aws fail with auth errors.
2. `claim-task`: before writing code. Creates the branch, the task file and a draft PR.
3. Do the work on that branch.
4. `handoff`: when you stop before the task is done.
5. `create-pr`: when the task is done. It runs `review` first.

`main` is protected: every change lands through a PR, and AI agents never merge.
Open draft PRs are the team's task board.

No AI attribution anywhere: no `Co-Authored-By` trailers in commits, no "Generated with"
lines in PR descriptions, no AI credit comments in code.

## Code rules

`review` checks every change against these rules. Write only the code the task needs.

- No code for needs the task doesn't have: no abstraction with one caller, no parameter,
  flag or config nobody sets, nothing "for later".
- Use the standard library, boto3, and features AWS already provides before adding
  code or dependencies. A new dependency needs a one-line reason in the PR.
- Merge no dead code, unused imports or commented-out code.
- Small functions whose names say what they do. Plain data (dataclasses, dicts) over class
  hierarchies.
- Fail loudly. Don't catch exceptions you can't handle.
- Test logic that can break silently (retrieval, citations, parsing). Don't test glue code.
- Mark a deliberate shortcut with `# shortcut: <what> - <why>` so it can be found later.

## Documentation rules

- Every module starts with a one- or two-line docstring saying what it's for.
- Every public function and class has a docstring: what it does, plus anything non-obvious
  (inputs, side effects, AWS resources it touches).
- Comments explain why, not what. Delete comments that only restate the code.
- When a change adds a command, env var, AWS resource or setup step, update this file or
  `README.md` in the same PR.

## Security

- No secrets in code or commits. Config comes from env vars and AWS profiles. gitleaks runs
  on every commit; never bypass it with `--no-verify`.
- This repo is public: refer to AWS resources by name, not full ARN or account ID.
- Least-privilege IAM roles. Private, encrypted S3 buckets.
- Corpus documents live in S3, not in git.

## Personal config stays local

Tracked and shared: `AGENTS.md`, `CLAUDE.md`, `.agents/skills/` (`.claude/skills` is a
symlink to it).

Ignored: the rest of `.claude/` and `.agents/`, plus `.codex/`, `.mcp.json`,
`CLAUDE.local.md`, `AGENTS.override.md`, editor folders, `.env*` and virtualenvs.
Personal settings, MCP servers and skills go in those files or in your home directory
(`~/.claude`, `~/.codex`, `~/.agents`). Change shared files only through a PR.

## Layout

```
.agents/skills/   shared skills: setup, claim-task, handoff, review, create-pr
docs/tasks/       one file per task: goal, done-when, latest handoff
scripts/setup.sh  machine checks used by the setup skill
```
