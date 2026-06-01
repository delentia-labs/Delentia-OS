output "gateway_url" {
  description = "Delentia Gateway API URL"
  value       = "http://localhost:8000"
}

output "health_check_url" {
  description = "Health check endpoint"
  value       = "http://localhost:8000/health"
}

output "qdrant_url" {
  description = "Qdrant vector search URL"
  value       = "http://localhost:8003"
}

output "intent_loop_url" {
  description = "Intent Loop API URL"
  value       = "http://localhost:8001"
}
