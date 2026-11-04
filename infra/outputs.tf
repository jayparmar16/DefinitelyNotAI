output "corpus_bucket" {
  description = "Bucket for raw PDFs (raw/), extracted text (text/) and evaluation files (eval/)."
  value       = module.storage.corpus_bucket
}

output "db_cluster_identifier" {
  description = "Aurora cluster name, for the Data API and the console."
  value       = module.database.cluster_identifier
}
