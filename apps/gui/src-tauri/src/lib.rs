mod commands;

use commands::intent::{execute_intent, get_system_stats, health_check, get_memory_history, stream_intent};

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
        ])
        .run(tauri::generate_context!())
        .expect("error while running Delentia Desk");
}
