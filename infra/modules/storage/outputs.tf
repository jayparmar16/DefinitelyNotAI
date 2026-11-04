output "corpus_bucket" {
  description = "Name of the corpus bucket."
  value       = aws_s3_bucket.corpus.id
}
