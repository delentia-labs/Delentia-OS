// Tauri entry point — delegates to lib.rs
#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

fn main() {
    delentia_gui_lib::run();
}
