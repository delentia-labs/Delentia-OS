variable "postgres_password" {
  description = "PostgreSQL password for the delentia user (min 24 chars)"
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.postgres_password) >= 24
    error_message = "PostgreSQL password must be at least 24 characters."
  }
}

variable "delentia_api_key" {
  description = "Delentia Gateway API key (min 32 chars)"
  type        = string
  sensitive   = true
  validation {
    condition     = length(var.delentia_api_key) >= 32
    error_message = "API key must be at least 32 characters."
  }
}

variable "delentia_version" {
  description = "Delentia service image tag"
  type        = string
  default     = "2.0"
}
