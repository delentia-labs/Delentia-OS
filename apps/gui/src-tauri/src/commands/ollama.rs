use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Emitter};

// ── Types ─────────────────────────────────────────────────────────────────────

#[derive(Debug, Serialize, Deserialize)]
pub struct OllamaModel {
    pub name: String,
    pub size: u64,
    pub modified_at: String,
    pub digest: String,
    pub details: Option<OllamaModelDetails>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OllamaModelDetails {
    pub family: Option<String>,
    pub parameter_size: Option<String>,
    pub quantization_level: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OllamaTagsResponse {
    pub models: Vec<OllamaModel>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OllamaStatus {
    pub running: bool,
    pub models: Vec<String>,
    pub model_count: usize,
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct OllamaPullProgress {
    pub status: String,
    pub completed: Option<u64>,
    pub total: Option<u64>,
    pub digest: Option<String>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OllamaGenerateRequest {
    pub model: String,
    pub prompt: String,
    pub stream: bool,
    pub options: Option<Value>,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct OllamaGenerateResponse {
    pub model: String,
    pub response: String,
    pub done: bool,
    pub total_duration: Option<u64>,
    pub eval_count: Option<u64>,
}

const OLLAMA_BASE: &str = "http://localhost:11434";

// ── Commands ──────────────────────────────────────────────────────────────────

/// Check if Ollama is running and list installed models.
/// Calls GET http://localhost:11434/api/tags
#[tauri::command]
pub async fn check_ollama_status() -> Result<OllamaStatus, String> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(3))
        .build()
        .map_err(|e| format!("Client build error: {e}"))?;

    let res = client
        .get(format!("{OLLAMA_BASE}/api/tags"))
        .send()
        .await;

    match res {
        Ok(r) if r.status().is_success() => {
            let data: OllamaTagsResponse = r
                .json()
                .await
                .map_err(|e| format!("Parse error: {e}"))?;
            let models: Vec<String> = data.models.iter().map(|m| m.name.clone()).collect();
            let count = models.len();
            Ok(OllamaStatus {
                running: true,
                models,
                model_count: count,
            })
        }
        _ => Ok(OllamaStatus {
            running: false,
            models: vec![],
            model_count: 0,
        }),
    }
}

/// List all installed Ollama models with full details.
/// Calls GET http://localhost:11434/api/tags
#[tauri::command]
pub async fn list_ollama_models() -> Result<Vec<OllamaModel>, String> {
    let client = Client::new();
    let res = client
        .get(format!("{OLLAMA_BASE}/api/tags"))
        .send()
        .await
        .map_err(|e| format!("Connection failed: {e}"))?;

    if !res.status().is_success() {
        return Err(format!("Ollama API returned {}", res.status()));
    }

    let data: OllamaTagsResponse = res
        .json()
        .await
        .map_err(|e| format!("Parse error: {e}"))?;

    Ok(data.models)
}

/// Pull an Ollama model — emits progress events to the frontend.
///
/// Events emitted on channel: `ollama-pull-progress`
///   payload: { status: string, completed?: number, total?: number }
///
/// Frontend listens with: `await listen('ollama-pull-progress', handler)`
#[tauri::command]
pub async fn pull_ollama_model(
    app: AppHandle,
    model_id: String,
) -> Result<String, String> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(600)) // 10 min for large models
        .build()
        .map_err(|e| format!("Client error: {e}"))?;

    // Emit starting event
    let _ = app.emit(
        "ollama-pull-progress",
        OllamaPullProgress {
            status: format!("Starting pull: {model_id}"),
            completed: None,
            total: None,
            digest: None,
        },
    );

    // POST /api/pull with stream: false (simpler for Tauri)
    let res = client
        .post(format!("{OLLAMA_BASE}/api/pull"))
        .json(&serde_json::json!({ "name": model_id, "stream": false }))
        .send()
        .await
        .map_err(|e| format!("Connection failed: {e}"))?;

    if !res.status().is_success() {
        let err = res.text().await.unwrap_or_default();
        let _ = app.emit(
            "ollama-pull-progress",
            OllamaPullProgress {
                status: format!("Error: {err}"),
                completed: None,
                total: None,
                digest: None,
            },
        );
        return Err(format!("Pull failed: {err}"));
    }

    let data: Value = res
        .json()
        .await
        .map_err(|e| format!("Parse error: {e}"))?;

    let final_status = data
        .get("status")
        .and_then(|s| s.as_str())
        .unwrap_or("success")
        .to_string();

    // Emit completion
    let _ = app.emit(
        "ollama-pull-progress",
        OllamaPullProgress {
            status: final_status.clone(),
            completed: None,
            total: None,
            digest: None,
        },
    );

    Ok(final_status)
}

/// Run inference on an Ollama model.
/// Calls POST http://localhost:11434/api/generate (stream: false)
///
/// Returns the generated text string.
#[tauri::command]
pub async fn run_ollama_inference(
    prompt: String,
    model: String,
    temperature: Option<f32>,
) -> Result<String, String> {
    let client = Client::builder()
        .timeout(std::time::Duration::from_secs(120))
        .build()
        .map_err(|e| format!("Client error: {e}"))?;

    let options = temperature.map(|t| serde_json::json!({ "temperature": t }));

    let req_body = OllamaGenerateRequest {
        model: model.clone(),
        prompt: prompt.clone(),
        stream: false,
        options,
    };

    let res = client
        .post(format!("{OLLAMA_BASE}/api/generate"))
        .json(&req_body)
        .send()
        .await
        .map_err(|e| format!("Connection failed: {e}"))?;

    if !res.status().is_success() {
        let err = res.text().await.unwrap_or_default();
        return Err(format!("Ollama generate error: {err}"));
    }

    let data: OllamaGenerateResponse = res
        .json()
        .await
        .map_err(|e| format!("Parse error: {e}"))?;

    Ok(data.response)
}

/// Delete an installed Ollama model.
/// Calls DELETE http://localhost:11434/api/delete
#[tauri::command]
pub async fn delete_ollama_model(model_name: String) -> Result<(), String> {
    let client = Client::new();
    let res = client
        .delete(format!("{OLLAMA_BASE}/api/delete"))
        .json(&serde_json::json!({ "name": model_name }))
        .send()
        .await
        .map_err(|e| format!("Connection failed: {e}"))?;

    if !res.status().is_success() {
        let err = res.text().await.unwrap_or_default();
        return Err(format!("Delete error: {err}"));
    }
    Ok(())
}
