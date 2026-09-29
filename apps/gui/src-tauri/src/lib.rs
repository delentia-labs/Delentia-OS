mod commands;

use commands::intent::{execute_intent, get_system_stats, health_check, get_memory_history, stream_intent};
use commands::ollama::{check_ollama_status, list_ollama_models, pull_ollama_model, run_ollama_inference, delete_ollama_model};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            execute_intent,
            get_system_stats,
            health_check,
            get_memory_history,
            stream_intent,
            check_ollama_status,
            list_ollama_models,
            pull_ollama_model,
            run_ollama_inference,
            delete_ollama_model,
        ])
        .run(tauri::generate_context!())
        .expect("error while running Delentia Desk");
}
