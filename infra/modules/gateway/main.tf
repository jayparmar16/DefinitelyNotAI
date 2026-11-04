# askwri-gateway: AgentCore Gateway exposing the five tool Lambdas as MCP tools.
# Who may call it: a Cognito client-credentials token (askwri-auth). What it may call:
# askwri-gateway-role, limited to invoking the five askwri-tool-* functions.

locals {
  scope = "askwri/tools"
  # MCP tool definitions. Property fields: name, type, description, required, items (arrays).
  tools = {
    search = {
      description = "Search WRI publications. Returns the most relevant passages with title, year, type, page, a link, a relevance score and why each matched. Use filters to narrow by year, type, topic, country or language; undated documents are included unless include_undated is false."
      properties = [
        { name = "query", type = "string", required = true, description = "What to look for, in any language." },
        { name = "k", type = "integer", description = "How many passages to return (default 8, at most 20)." },
        { name = "year_from", type = "integer", description = "Only documents from this year on." },
        { name = "year_to", type = "integer", description = "Only documents up to this year." },
        { name = "include_undated", type = "boolean", description = "Keep documents with no reliable date (default true)." },
        { name = "pub_type", type = "string", description = "Publication type, e.g. Report or Issue brief." },
        { name = "topic", type = "string", description = "One of WRI's topics (e.g. Cities, Climate, Forests) or a tag." },
        { name = "country", type = "string", description = "Country the document covers." },
        { name = "language", type = "string", description = "ISO 639-1 language of the document, e.g. en, es, pt." },
      ]
    }
    get_passage = {
      description = "Fetch one passage by chunk_id with its document's citation fields and the passages just before and after it, to check context before citing."
      properties = [
        { name = "chunk_id", type = "string", required = true, description = "The chunk_id from a search result." },
        { name = "neighbours", type = "integer", description = "Passages to include on each side (0-2, default 1)." },
      ]
    }
    coverage = {
      description = "Count WRI documents in the collection by topic, tag, country, year, pub_type or language, optionally within a topic or country. Use it for gap and coverage questions; counts describe the indexed collection only."
      properties = [
        { name = "dimension", type = "string", required = true, description = "One of topic, tag, country, year, pub_type, language." },
        { name = "topic", type = "string", description = "Only count documents on this topic or tag." },
        { name = "country", type = "string", description = "Only count documents covering this country." },
      ]
    }
    authors = {
      description = "List the public authors of the given documents, and each person with the documents they wrote."
      properties = [
        { name = "doc_ids", type = "array", required = true, description = "Document IDs from search results.", items = { type = "string" } },
      ]
    }
    translate = {
      description = "Machine-translate text, keeping every number and [n] citation marker. Returns numbers_preserved; never show a translation whose numbers_preserved is false."
      properties = [
        { name = "text", type = "string", required = true, description = "Text to translate." },
        { name = "target_language", type = "string", required = true, description = "ISO 639-1 code: en, es, pt, fr, id or hi." },
      ]
    }
  }
  # Gateway target name -> tool Lambda (the tool named get_passage runs askwri-tool-passage).
  lambda_for_tool = {
    search      = "search"
    get_passage = "passage"
    coverage    = "coverage"
    authors     = "authors"
    translate   = "translate"
  }
}

# --- Cognito: who may call the gateway ---

resource "aws_cognito_user_pool" "auth" {
  name = "askwri-auth"
}

resource "aws_cognito_user_pool_domain" "auth" {
  domain       = "askwri-${var.account_id}"
  user_pool_id = aws_cognito_user_pool.auth.id
}

resource "aws_cognito_resource_server" "askwri" {
  user_pool_id = aws_cognito_user_pool.auth.id
  identifier   = "askwri"
  name         = "AskWRI tools"
  scope {
    scope_name        = "tools"
    scope_description = "Call the AskWRI gateway tools"
  }
}

resource "aws_cognito_user_pool_client" "gateway" {
  name                                 = "askwri-gateway-client"
  user_pool_id                         = aws_cognito_user_pool.auth.id
  generate_secret                      = true
  allowed_oauth_flows                  = ["client_credentials"]
  allowed_oauth_flows_user_pool_client = true
  allowed_oauth_scopes                 = [local.scope]
  supported_identity_providers         = ["COGNITO"]
  depends_on                           = [aws_cognito_resource_server.askwri]
}

resource "aws_secretsmanager_secret" "gateway_client" {
  name                    = "askwri/gateway-client"
  description             = "Cognito client credentials for askwri-gateway (agent and MCP clients)."
  recovery_window_in_days = 0 # shortcut: immediate delete on destroy, so a redeploy can reuse the name
}

resource "aws_secretsmanager_secret_version" "gateway_client" {
  secret_id = aws_secretsmanager_secret.gateway_client.id
  # Write-only: the secret value is not kept in this resource's state.
  secret_string_wo = jsonencode({
    client_id     = aws_cognito_user_pool_client.gateway.id
    client_secret = aws_cognito_user_pool_client.gateway.client_secret
    token_url     = "https://${aws_cognito_user_pool_domain.auth.domain}.auth.${var.region}.amazoncognito.com/oauth2/token"
    scope         = local.scope
  })
  secret_string_wo_version = 1
}

# --- The gateway and what it may call ---

data "aws_iam_policy_document" "gateway_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["bedrock-agentcore.amazonaws.com"]
    }
    condition {
      test     = "StringEquals"
      variable = "aws:SourceAccount"
      values   = [var.account_id]
    }
  }
}

resource "aws_iam_role" "gateway" {
  name               = "askwri-gateway-role"
  assume_role_policy = data.aws_iam_policy_document.gateway_assume.json
}

data "aws_iam_policy_document" "gateway" {
  statement {
    actions   = ["lambda:InvokeFunction"]
    resources = values(var.tool_function_arns)
  }
}

resource "aws_iam_role_policy" "gateway" {
  name   = "askwri-gateway-invoke-tools"
  role   = aws_iam_role.gateway.id
  policy = data.aws_iam_policy_document.gateway.json
}

resource "aws_bedrockagentcore_gateway" "askwri" {
  name            = "askwri-gateway"
  description     = "AskWRI tools over MCP: search, get_passage, coverage, authors, translate"
  role_arn        = aws_iam_role.gateway.arn
  protocol_type   = "MCP"
  authorizer_type = "CUSTOM_JWT"

  authorizer_configuration {
    custom_jwt_authorizer {
      discovery_url = "https://cognito-idp.${var.region}.amazonaws.com/${aws_cognito_user_pool.auth.id}/.well-known/openid-configuration"
      # Client-credentials tokens carry no audience claim, so the client ID is what's checked.
      allowed_clients = [aws_cognito_user_pool_client.gateway.id]
    }
  }

  depends_on = [aws_iam_role_policy.gateway]
}

resource "aws_bedrockagentcore_gateway_target" "tool" {
  for_each           = local.tools
  name               = replace(each.key, "_", "-")
  gateway_identifier = aws_bedrockagentcore_gateway.askwri.gateway_id
  # Target descriptions are capped at 200 characters; the full text is in the tool schema.
  description = "AskWRI ${each.key} tool (askwri-tool-${local.lambda_for_tool[each.key]})"

  credential_provider_configuration {
    gateway_iam_role {}
  }

  target_configuration {
    mcp {
      lambda {
        lambda_arn = var.tool_function_arns[local.lambda_for_tool[each.key]]
        tool_schema {
          inline_payload {
            name        = each.key
            description = each.value.description
            input_schema {
              type = "object"
              dynamic "property" {
                for_each = each.value.properties
                content {
                  name        = property.value.name
                  type        = property.value.type
                  description = property.value.description
                  required    = try(property.value.required, false)
                  dynamic "items" {
                    for_each = try([property.value.items], [])
                    content {
                      type = items.value.type
                    }
                  }
                }
              }
            }
          }
        }
      }
    }
  }
}
