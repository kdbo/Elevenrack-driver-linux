// SPDX-License-Identifier: MIT
mod files;
mod host;
mod midi;
mod protocol;
use serde_json::{json, Value};
use std::sync::{mpsc, Arc};
use tauri::{Emitter, Manager};

#[tauri::command]
async fn midi_command(
    state: tauri::State<'_, midi::MidiService>,
    session: String,
    message: Value,
) -> Result<Option<Value>, String> {
    let service = state.inner().clone();
    tauri::async_runtime::spawn_blocking(move || service.command(session, message))
        .await
        .map_err(|e| e.to_string())?
}
#[tauri::command]
async fn host_call(
    app: tauri::AppHandle,
    state: tauri::State<'_, Arc<host::Host>>,
    midi: tauri::State<'_, midi::MidiService>,
    method: String,
    args: Vec<Value>,
) -> Result<Value, String> {
    let host = state.inner().clone();
    let midi = midi.inner().clone();
    tauri::async_runtime::spawn_blocking(move || {
        let result = host.call(&app, &midi, &method, &args);
        if [
            "saveTfx",
            "loadTfxDialog",
            "readImportBank",
            "exportBank",
            "chooseImportSource",
            "chooseExportDir",
            "chooseCapturesDir",
            "resetCapturesDir",
            "openUserManual",
            "openPath",
        ]
        .contains(&method.as_str())
        {
            Ok(result.unwrap_or_else(|error| json!({"ok":false,"error":error})))
        } else {
            result
        }
    })
    .await
    .map_err(|e| e.to_string())?
}
fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.iter().any(|a| a == "--probe-midi") {
        match midi::probe_identity() {
            Ok(reply) => println!("{}", serde_json::to_string_pretty(&reply).unwrap()),
            Err(error) => {
                eprintln!("{error}");
                std::process::exit(1);
            }
        }
        return;
    }
    if args.iter().any(|a| a == "--list-midi") {
        match midi::list_ports() {
            Ok(ports) => println!("{}", serde_json::to_string_pretty(&ports).unwrap()),
            Err(error) => {
                eprintln!("{error}");
                std::process::exit(1);
            }
        }
        return;
    }
    let smoke = args.iter().any(|a| a == "--smoke-test");
    let disabled = smoke || args.iter().any(|a| a == "--no-midi");
    let logs = smoke || args.iter().any(|a| a == "--logs");
    let application = tauri::Builder::default()
        .plugin(tauri_plugin_single_instance::init(|app, _, _| {
            if let Some(window) = app.get_webview_window("main") {
                let _ = window.set_focus();
            }
        }))
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_opener::init())
        .setup(move |app| {
            let root = app.path().app_data_dir()?;
            let host = Arc::new(host::Host::new(root, logs).map_err(std::io::Error::other)?);
            app.manage(host);
            let (events, receiver) = mpsc::channel::<Value>();
            app.manage(midi::MidiService::start(events, disabled));
            let handle = app.handle().clone();
            std::thread::spawn(move || {
                for event in receiver {
                    let _ = handle.emit("native-midi", event);
                }
            });
            if smoke {
                let handle = app.handle().clone();
                std::thread::spawn(move || {
                    std::thread::sleep(std::time::Duration::from_secs(12));
                    let host = handle.state::<Arc<host::Host>>();
                    let passed = host
                        .frontend_ready
                        .load(std::sync::atomic::Ordering::SeqCst)
                        && !host
                            .frontend_errors
                            .load(std::sync::atomic::Ordering::SeqCst);
                    handle.exit(if passed { 0 } else { 1 });
                });
            }
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![host_call, midi_command])
        .build(tauri::generate_context!())
        .expect("Failed to start the Tauri editor");
    application.run(|_, _| {});
}
