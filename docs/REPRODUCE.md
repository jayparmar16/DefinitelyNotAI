# Reproduce AskWRI from an empty AWS account

Every step to stand up the whole system: infrastructure, the library, the website, accounts,
evaluation and demo chats. Run the commands from the repository root unless a step says
otherwise. Everything goes into **one AWS account in us-west-2**.

Expect about an hour of setup plus the library load (several hours for ~700 PDFs, mostly model
calls for labels and figures; it can be stopped and resumed).

## 0. What you need

- An AWS account where you can create IAM roles, and **Bedrock model access** in us-west-2 for:
  Claude Sonnet 5.5 and Claude Haiku (through their `global.` inference profiles), Cohere Embed
  v4 (`us.cohere.embed-v4:0`) and Amazon Rerank 1.0. Model IDs are Terraform variables
  (`infra/variables.tf`), so you can swap them.
- Tools: AWS CLI v2, Terraform 1.11+, Python 3.12 with [uv](https://docs.astral.sh/uv/),
  Node 22+, git.
- WRI's PDFs, in folders whose names start with the publication year (`2024_publications/`,
  `2025/` ...). An undated document takes its folder's year.

```sh
git clone https://github.com/jayparmar16/DefinitelyNotAI.git && cd DefinitelyNotAI
git switch release-branch
uv sync
(cd web && npm install)
uv run pytest && (cd web && npm test && npm run lint)    # everything should pass before you deploy
```

## 1. Point at your account

```sh
export AWS_PROFILE=<your profile> AWS_REGION=us-west-2 AWS_DEFAULT_REGION=us-west-2
export TF_VAR_team_account_id=$(aws sts get-caller-identity --query Account --output text)
```

Terraform refuses any other account than `TF_VAR_team_account_id`. Temporary credentials
expire: on `ExpiredToken`, refresh them and run the step again. Never commit the account ID,
ARNs or secrets; `infra/backend.hcl` and `infra/terraform.tfvars` are gitignored.

## 2. Terraform state and settings (once)

```sh
infra/bootstrap/create-state-bucket.sh                     # S3 state bucket; writes infra/backend.hcl
cp infra/terraform.tfvars.example infra/terraform.tfvars   # set team and owner (tag values)
```

Optional settings in `terraform.tfvars` (defaults in `infra/variables.tf`): `db_min_capacity`
(0 lets Aurora pause when idle; 0.5 keeps it awake for demos), `api_max_concurrency` (15),
`relevance_threshold` (0.01), `grounding_threshold` (0.5), and the model IDs.

## 3. Build the packages

```sh
infra/build/tools.sh     # build/tools.zip: the six tool Lambdas
infra/build/agent.sh     # build/agent.zip: the agent for AgentCore Runtime (no Docker)
infra/build/api.sh       # build/api.zip: the API Lambda
```

Rebuild the package you changed before every plan.

## 4. Deploy the infrastructure

```sh
cd infra
terraform init -backend-config=backend.hcl
terraform plan -out=plan.tfplan        # read it: what is added, changed, destroyed
terraform apply plan.tfplan
cd ..
```

This creates: the VPC and endpoints, the private corpus bucket, Aurora PostgreSQL Serverless v2
with pgvector and the Data API, the tool Lambdas, Cognito for the gateway, AgentCore Gateway,
the agent on AgentCore Runtime with Memory and a Guardrail, the API Lambda with its query log
in DynamoDB, the Cognito user pool for people, the website bucket and CloudFront, the
evaluation resources and a CloudWatch dashboard. Everything is tagged `Project = AskWRI` and
listed in the resource group `askwri-rg`.

## 5. Create the tables

```sh
uv run python db/apply_schema.py       # tables, views, indexes, database users; safe to rerun
```

## 6. Load the library

```sh
export CORPUS_BUCKET=$(terraform -chdir=infra output -raw corpus_bucket)
uv run python -m askwri.ingest.load path/to/2024_publications path/to/2025_publications path/to/2026_publications
```

For each PDF: sort (duplicates, older versions, document type), parse, cut passages with page
numbers, describe charts and maps (images go to `s3://$CORPUS_BUCKET/figures/`), audit,
label (wri.org, else the model), enrich, embed and load in one transaction (PDF to `raw/`).
Each document prints one line; failures print `SKIPPED` with the reason. Rerunning resumes;
`--reload` loads everything again after a pipeline change. Model replies are cached in
`.cache/ingest/`, so a rerun doesn't pay twice.

Do **not** use `scripts/run-pipeline.sh` in a shared account: it runs `terraform apply` without
a plan when it thinks resources are missing.

Then build the citation links between documents (they feed the citation map):

```sh
ASKWRI_SMALL_MODEL=global.anthropic.claude-haiku-4-5-20251001-v1:0 uv run python -m askwri.links
```

Check the load:

```sh
uv run python -m askwri.spaces      # searchable publications in total and per WRI topic
```

## 7. Publish the website

```sh
scripts/deploy-web.sh       # builds web/ against the API and Cognito, uploads, invalidates CloudFront
terraform -chdir=infra output -raw web_url
```

The script also writes `web/public/spaces.json` (publication counts per topic) from the
database.

## 8. Add people

AskWRI is invite only. Add each person, and add admins to `askwri-admins` for the admin page:

```sh
POOL=$(terraform -chdir=infra output -raw user_pool_id)
aws cognito-idp admin-create-user --user-pool-id "$POOL" --username person@example.org \
  --user-attributes Name=email,Value=person@example.org Name=email_verified,Value=true
aws cognito-idp admin-add-user-to-group --user-pool-id "$POOL" --username person@example.org \
  --group-name askwri-admins     # admins only
```

Cognito emails a temporary password; the first sign-in sets a new one.

## 9. Evaluate

```sh
export ASKWRI_API_URL=$(terraform -chdir=infra output -raw api_url)
uv run python -m eval.run_eval run --configuration "first deploy"   # 30 questions through the API
uv run python -m eval.run_eval judge <run id>                       # 5+ minutes later: AgentCore judges
```

`run` writes `eval/results/<run id>.json` and copies it to `s3://$CORPUS_BUCKET/eval/results/`.
The admin page shows the **newest** file in that folder as "Last run", so keep experiments
elsewhere (for example `eval/experiments/`). `judge` adds the AgentCore judge averages to the
same file. `--only F01,U02` runs a subset.

## 10. Demo chats (optional)

```sh
uv run python scripts/record_demo_chats.py > web/public/demo-chats.json   # asks each demo question on the API
scripts/deploy-web.sh
```

Open `<web url>/?demo=load` once in a signed-in browser: it replaces that browser's chats with
the recorded ones, titled by use case.

## 11. Check it works

1. Open the web URL, sign in, ask "How do cities protect people from extreme heat?". You should
   see the steps stream, then an answer with "n of n claims verified" and numbered citations;
   clicking one opens the PDF at its page.
2. Ask "How did WRI rank the world's best football stadiums for energy efficiency?". It should
   decline and show what it searched.
3. Open `/admin/` as an admin: the scorecard shows your evaluation run; Cost and usage fills in
   as questions are asked.
4. In CloudWatch, GenAI Observability shows the agent's traces.

## Cost and teardown

Aurora and the VPC interface endpoints bill by the hour; Aurora pauses when idle if
`db_min_capacity = 0`. Each answer costs about $0.05 in model calls. To remove everything:

```sh
cd infra && terraform plan -destroy -out=destroy.tfplan && terraform apply destroy.tfplan
```

Then check that the resource group `askwri-rg` is empty. The corpus bucket must be emptied
first if Terraform refuses to delete it.

## Where to look when something fails

| Symptom | Look at |
|---|---|
| `DatabaseResumingException` | Aurora was paused; wait 15–30 s and retry |
| The UI says it can't reach AskWRI | API Lambda `askwri-api` logs in CloudWatch |
| Answers fail or hang | AgentCore Runtime `askwri_agent` logs and GenAI Observability traces |
| A tool error in the steps | The tool Lambda's logs (`askwri-tool-*`) |
| A model "not available" error | Use the `global.`/`us.` inference profile ID and check model access |
| Admin page blank | Sign in with an `askwri-admins` account; try a window without ad blockers |

More detail on every module and setting: [developer-reference.md](developer-reference.md).
