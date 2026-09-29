use reqwest::Client;
use serde::{Deserialize, Serialize};
use serde_json::Value;
use tauri::{AppHandle, Emitter};
use tokio_tungstenite::connect_async;
use tokio_tungstenite::tungstenite::Message as WsMessage;
use futures_util::{SinkExt, StreamExt};

#[derive(Debug, Serialize, Deserialize)]
pub struct IntentRequest {
    pub intent: String,
    pub mode: String,
}

#[derive(Debug, Serialize, Deserialize)]
pub struct HealthResponse {
    pub status: String,
    pub timestamp: String,
    pub version: String,
    pub service: String,
}

/// Execute an intent through the Delentia OS Gateway API.
/// Routes to POST /v1/kernel/execute with Bearer auth.
#[tauri::command]
pub async fn execute_intent(
    intent: String,
    api_key: String,
    gateway: String,
    mode: Option<String>,
) -> Result<Value, String> {
    let client = Client::new();
    let url = format!("{}/v1/kernel/execute", gateway.trim_end_matches('/'));
    let body = IntentRequest {
        intent,
        mode: mode.unwrap_or_else(|| "standard".to_string()),
    };

    let response = client
        .post(&url)
        .bearer_auth(&api_key)
        .header("X-Trace-Id", uuid_v4())
        .json(&body)
        .send()
        .await
        .map_err(|e| format!("Network error: {e}"))?;

    let status = response.status();
    let json: Value = response
        .json()
        .await
        .map_err(|e| format!("Parse error: {e}"))?;

    if !status.is_success() {
        return Err(format!("API error {status}: {json}"));
    }

    Ok(json)
}

/// Fetch live system stats — no auth required.
/// Routes to GET /delentia/system/stats
#[tauri::command]
pub async fn get_system_stats(gateway: String) -> Result<Value, String> {
    let client = Client::new();
    let url = format!("{}/delentia/system/stats", gateway.trim_end_matches('/'));

    let response = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Network error: {e}"))?;

    response
        .json::<Value>()
        .await
        .map_err(|e| format!("Parse error: {e}"))
}

/// Health check all Delentia OS ports.
/// Routes to GET /health
#[tauri::command]
pub async fn health_check(gateway: String) -> Result<HealthResponse, String> {
    let client = Client::new();
    let url = format!("{}/health", gateway.trim_end_matches('/'));

    let response = client
        .get(&url)
        .send()
        .await
        .map_err(|e| format!("Connection failed: {e}"))?;

    response
        .json::<HealthResponse>()
        .await
        .map_err(|e| format!("Parse error: {e}"))
}

/// Fetch memory delta history for the timeline viewer.
/// Routes to GET /v1/memory/history
#[tauri::command]
pub async fn get_memory_history(
    api_key: String,
    gateway: String,
    limit: Option<u32>,
) -> Result<Value, String> {
    let client = Client::new();
    let limit = limit.unwrap_or(50);
    let url = format!(
        "{}/v1/memory/history?limit={limit}",
        gateway.trim_end_matches('/')
    );

    let response = client
        .get(&url)
        .bearer_auth(&api_key)
        .header("X-Trace-Id", uuid_v4())
        .send()
        .await
        .map_err(|e| format!("Network error: {e}"))?;

    response
        .json::<Value>()
        .await
        .map_err(|e| format!("Parse error: {e}"))
}

/// Generate a simple UUID v4 string for X-Trace-Id headers.
fn uuid_v4() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let t = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .subsec_nanos();
    format!("trace-{:08x}-delentia", t)
}

/// Stream intent tokens via WebSocket — emits Tauri events to the frontend.
///
/// Events emitted on `channel`:
///   `{channel}:token`  — payload: { type: "token",  data: "<word>" }
///   `{channel}:fdia`   — payload: { type: "fdia",   data: FDIAScore }
///   `{channel}:done`   — payload: { type: "done",   data: {} }
///   `{channel}:error`  — payload: { type: "error",  data: "<message>" }
///
/// The frontend listens with: `await listen('<channel>:token', handler)`
#[tauri::command]
pub async fn stream_intent(
    app: AppHandle,
    intent: String,
    api_key: String,
    gateway: String,
    mode: Option<String>,
    channel: Option<String>,
) -> Result<(), String> {
    let mode = mode.unwrap_or_else(|| "standard".to_string());
    let channel = channel.unwrap_or_else(|| "kernel-stream".to_string());

    // Build WebSocket URL: replace http(s) with ws(s)
    let ws_base = gateway
        .trim_end_matches('/')
        .replace("https://", "wss://")
        .replace("http://", "ws://");
    let ws_url = if api_key.is_empty() {
        format!("{ws_base}/v1/kernel/stream")
    } else {
        format!("{ws_base}/v1/kernel/stream?token={api_key}")
    };

    let (mut ws_stream, _) = connect_async(&ws_url)
        .await
        .map_err(|e| format!("WS connect failed: {e}"))?;

    // Send the intent payload
    let payload = serde_json::json!({ "intent": intent, "mode": mode });
    ws_stream
        .send(WsMessage::Text(payload.to_string()))
        .await
        .map_err(|e| format!("WS send failed: {e}"))?;

    // Read messages and emit Tauri events
    while let Some(msg) = ws_stream.next().await {
        match msg {
            Ok(WsMessage::Text(text)) => {
                let event: Value = serde_json::from_str(&text)
                    .unwrap_or(serde_json::json!({ "type": "error", "data": text }));

                let ev_type = event["type"].as_str().unwrap_or("error");
                let event_name = format!("{}:{}", channel, ev_type);
                let _ = app.emit(&event_name, &event);

                if ev_type == "done" || ev_type == "error" {
                    break;
                }
            }
            Ok(WsMessage::Close(_)) => break,
            Err(e) => {
                let _ = app.emit(
                    &format!("{}:error", channel),
                    serde_json::json!({ "type": "error", "data": e.to_string() }),
                );
                break;
            }
            _ => {}
        }
    }

    Ok(())
}
