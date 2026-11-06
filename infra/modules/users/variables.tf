variable "origins" {
  description = "Origins the UI runs on (hosted and local); sign-in returns to <origin>/."
  type        = list(string)
}
