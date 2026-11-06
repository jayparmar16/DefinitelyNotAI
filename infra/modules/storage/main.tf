# askwri-corpus-<account-id>: private, encrypted bucket for raw/ PDFs, text/ and eval/ files.

locals {
  bucket = "askwri-corpus-${var.account_id}"
  # Roles that may read or write objects. They are created in later phases; matching is by
  # ARN string, so listing them before they exist is fine.
  object_roles = [
    var.deployer_arn,
    "arn:aws:iam::${var.account_id}:role/askwri-ingest-role",
    "arn:aws:iam::${var.account_id}:role/askwri-tools-role",
    "arn:aws:iam::${var.account_id}:role/askwri-api-role",
    "arn:aws:iam::${var.account_id}:role/askwri-eval-role",
  ]
}

resource "aws_s3_bucket" "corpus" {
  bucket = local.bucket
}

resource "aws_s3_bucket_public_access_block" "corpus" {
  bucket                  = aws_s3_bucket.corpus.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  rule {
    object_ownership = "BucketOwnerEnforced"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

data "aws_iam_policy_document" "corpus" {
  statement {
    sid       = "DenyInsecureTransport"
    effect    = "Deny"
    actions   = ["s3:*"]
    resources = [aws_s3_bucket.corpus.arn, "${aws_s3_bucket.corpus.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "Bool"
      variable = "aws:SecureTransport"
      values   = ["false"]
    }
  }

  # Object access only for the listed roles. Bucket settings stay manageable by account
  # admins, so this policy can't lock anyone out of the bucket itself.
  statement {
    sid    = "DenyObjectAccessToOtherPrincipals"
    effect = "Deny"
    actions = [
      "s3:GetObject*",
      "s3:PutObject*",
      "s3:DeleteObject*",
      "s3:ListBucket*",
    ]
    resources = [aws_s3_bucket.corpus.arn, "${aws_s3_bucket.corpus.arn}/*"]
    principals {
      type        = "*"
      identifiers = ["*"]
    }
    condition {
      test     = "ArnNotLike"
      variable = "aws:PrincipalArn"
      values   = local.object_roles
    }
  }
}

resource "aws_s3_bucket_policy" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  policy = data.aws_iam_policy_document.corpus.json
  # The public access block must exist first, or a policy edit could briefly be public.
  depends_on = [aws_s3_bucket_public_access_block.corpus]
}

# The UI's PDF viewer downloads a stored PDF with a presigned link to draw the cited page and
# highlight the passage, so the browser needs CORS on object reads. Reads stay limited to
# presigned links: the bucket policy above still denies everyone but the listed roles.
resource "aws_s3_bucket_cors_configuration" "corpus" {
  bucket = aws_s3_bucket.corpus.id
  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.allowed_origins
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}
