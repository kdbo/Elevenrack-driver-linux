// SPDX-License-Identifier: MIT
use crate::{
    files,
    midi::MidiService,
    protocol::{decode_7bit, safe_name, tfx},
};
use serde_json::{json, Value};
use std::{
    collections::HashSet,
    fs::{self, OpenOptions},
    io::Write,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, Ordering},
        Mutex,
    },
    time::{SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Emitter, Manager};
use tauri_plugin_dialog::DialogExt;
use tauri_plugin_opener::OpenerExt;

pub struct Host {
    pub root: PathBuf,
    settings: Mutex<Value>,
    log_lock: Mutex<()>,
    grants: Mutex<HashSet<PathBuf>>,
    pub logs: bool,
    pub frontend_ready: AtomicBool,
    pub frontend_errors: AtomicBool,
}
impl Host {
    pub fn new(root: PathBuf, logs: bool) -> Result<Self, String> {
        fs::create_dir_all(root.join("captures")).map_err(|e| e.to_string())?;
        fs::create_dir_all(root.join("logs")).map_err(|e| e.to_string())?;
        let path = root.join("settings.json");
        let settings = if path.exists() {
            serde_json::from_slice(&fs::read(path).map_err(|e| e.to_string())?)
                .map_err(|e| format!("Cannot read preview settings: {e}"))?
        } else {
            json!({})
        };
        if !settings.is_object() {
            return Err("Preview settings must be a JSON object".into());
        }
        Ok(Self {
            root,
            settings: Mutex::new(settings),
            log_lock: Mutex::new(()),
            grants: Mutex::new(HashSet::new()),
            logs,
            frontend_ready: AtomicBool::new(false),
            frontend_errors: AtomicBool::new(false),
        })
    }
    fn get(&self, key: &str, fallback: Value) -> Result<Value, String> {
        Ok(self
            .settings
            .lock()
            .map_err(|_| "Settings lock failed")?
            .get(key)
            .cloned()
            .unwrap_or(fallback))
    }
    fn set(&self, key: &str, value: Value) -> Result<Value, String> {
        let mut data = self.settings.lock().map_err(|_| "Settings lock failed")?;
        let mut updated = data.clone();
        updated[key] = value;
        let bytes = serde_json::to_vec_pretty(&updated).map_err(|e| e.to_string())?;
        if bytes.len() > 8 * 1024 * 1024 {
            return Err("Preview settings exceed size limit".into());
        }
        let temporary = self.root.join("settings.json.tmp");
        fs::write(&temporary, bytes).map_err(|e| e.to_string())?;
        fs::rename(temporary, self.root.join("settings.json")).map_err(|e| e.to_string())?;
        *data = updated;
        Ok(json!(true))
    }
    fn captures(&self) -> Result<PathBuf, String> {
        let custom = self.get("capturesDir", Value::Null)?;
        let path = custom
            .as_str()
            .map(PathBuf::from)
            .filter(|p| p.is_dir())
            .unwrap_or_else(|| self.root.join("captures"));
        fs::create_dir_all(&path).map_err(|e| e.to_string())?;
        path.canonicalize().map_err(|e| e.to_string())
    }
    fn grant(&self, path: PathBuf) -> Result<PathBuf, String> {
        let path = path.canonicalize().map_err(|e| e.to_string())?;
        self.grants
            .lock()
            .map_err(|_| "Path grant lock failed")?
            .insert(path.clone());
        Ok(path)
    }
    fn authorized(&self, path: &Path) -> Result<PathBuf, String> {
        let path = path.canonicalize().map_err(|e| e.to_string())?;
        if self
            .grants
            .lock()
            .map_err(|_| "Path grant lock failed")?
            .contains(&path)
        {
            Ok(path)
        } else {
            Err("Choose this file or folder in the native dialog first".into())
        }
    }
    pub fn log(&self, text: &str) -> Result<Value, String> {
        if text.starts_with("JS error:") || text.starts_with("JS rejection:") {
            self.frontend_errors.store(true, Ordering::SeqCst);
        }
        if self.logs {
            let _guard = self.log_lock.lock().map_err(|_| "Log lock failed")?;
            let mut log = OpenOptions::new()
                .create(true)
                .append(true)
                .open(self.root.join("logs/editor.log"))
                .map_err(|e| e.to_string())?;
            let now = SystemTime::now()
                .duration_since(UNIX_EPOCH)
                .map_err(|e| e.to_string())?
                .as_millis();
            writeln!(log, "{now} {}", text.chars().take(8192).collect::<String>())
                .map_err(|e| e.to_string())?;
        }
        Ok(json!(true))
    }
    pub fn call(
        &self,
        app: &AppHandle,
        midi: &MidiService,
        method: &str,
        args: &[Value],
    ) -> Result<Value, String> {
        let arg = |i: usize| args.get(i).cloned().unwrap_or(Value::Null);
        let string = |i: usize| -> Result<String, String> {
            arg(i)
                .as_str()
                .map(str::to_string)
                .ok_or_else(|| "Expected text argument".into())
        };
        let getter = match method {
            "getSavedMode" => Some(("selectedMode", Value::Null)),
            "getSavedPorts" => Some(("ports", json!({"inIndex":null,"outIndex":null}))),
            "getBankCache" => Some(("bankCache", json!({}))),
            "getToneKnobOrder" => Some(("toneKnobOrder", json!({}))),
            "getNumberDisplayMode" => Some(("numberDisplayMode", json!(0))),
            "getZoom" => Some(("zoomFactor", json!(1.0))),
            _ => None,
        };
        if let Some((key, fallback)) = getter {
            return self.get(key, fallback);
        }
        let setter = match method {
            "saveMode" => Some("selectedMode"),
            "savePorts" => Some("ports"),
            "saveBankCache" => Some("bankCache"),
            "saveToneKnobOrder" => Some("toneKnobOrder"),
            "saveNumberDisplayMode" => Some("numberDisplayMode"),
            _ => None,
        };
        if let Some(key) = setter {
            return self.set(key, arg(0));
        }
        match method {
            "getRuntimeInfo" => Ok(
                json!({"splash":app.get_webview_window("splash").is_some(),"smoke":std::env::args().any(|arg|arg=="--smoke-test"),"noMidi":std::env::args().any(|arg|arg=="--no-midi" || arg=="--smoke-test")}),
            ),
            "frontendReady" => {
                self.log(&format!("LAYOUT_AUDIT {}", arg(0)["layout"]))?;
                if arg(0)["layout"]["passed"].as_bool() != Some(true) {
                    return Err("Editor layout checks failed".into());
                }
                if arg(0)["sharedInit"].as_bool() != Some(true)
                    || arg(0)["body"].as_bool() != Some(true)
                {
                    return Err("Shared editor did not initialize".into());
                }
                self.frontend_ready.store(true, Ordering::SeqCst);
                self.log("TAURI_FRONTEND_READY")
            }
            "getStartupMode" => Ok(json!(3)),
            "getAppVersion" => Ok(json!(env!("CARGO_PKG_VERSION"))),
            "getBridgeStatus" => Ok(json!({"launched":true,"error":null,"native":true})),
            "restartBridge" => {
                midi.command("host".into(), json!({"cmd":"reset"}))?;
                Ok(json!({"launched":true,"error":null,"native":true}))
            }
            "quitApp" => {
                app.exit(0);
                Ok(Value::Null)
            }
            "midiDelay" => {
                let ms = arg(0)
                    .as_u64()
                    .filter(|ms| *ms <= 10_000)
                    .ok_or("Invalid MIDI delay")?;
                std::thread::sleep(std::time::Duration::from_millis(ms));
                Ok(json!(true))
            }
            "splashReady" => {
                if arg(0)["barVisible"].as_bool() != Some(true) {
                    return Err("Splash progress bar did not render".into());
                }
                self.log(&format!("SPLASH_PAINTED {}", arg(0)))?;
                let handle = app.clone();
                app.run_on_main_thread(move || {
                    if handle.get_webview_window("main").is_none() {
                        let config = &handle.config().app.windows[0];
                        match tauri::WebviewWindowBuilder::from_config(&handle, config)
                            .and_then(|b| b.build())
                        {
                            Ok(_) => {}
                            Err(error) => {
                                eprintln!("Cannot create editor: {error}");
                                handle.exit(1);
                            }
                        }
                    }
                })
                .map_err(|e| e.to_string())?;
                Ok(json!(true))
            }
            "splashProgress" | "splashShowGate" | "splashHideGate" | "splashChooseRack" => {
                app.emit_to("splash", method, args)
                    .map_err(|e| e.to_string())?;
                Ok(json!(true))
            }
            "splashRetry" => {
                app.emit_to("main", "startup-retry-click", ())
                    .map_err(|e| e.to_string())?;
                Ok(json!(true))
            }
            "splashChoice" => {
                app.emit_to("main", "rack-choice", arg(0))
                    .map_err(|e| e.to_string())?;
                Ok(json!(true))
            }
            "appReady" => {
                let window = app
                    .get_webview_window("main")
                    .ok_or("Editor window missing")?;
                if !window.is_decorated().map_err(|e| e.to_string())? {
                    return Err("Editor title bar is missing".into());
                }
                window.show().map_err(|e| e.to_string())?;
                self.log("EDITOR_SHOWN_WITH_TITLE_BAR")?;
                window.set_focus().map_err(|e| e.to_string())?;
                if let Some(splash) = app.get_webview_window("splash") {
                    splash.close().map_err(|e| e.to_string())?;
                }
                Ok(json!(true))
            }
            "checkAvidEditor" => Ok(json!(false)),
            "startWatchdog"
            | "stopWatchdog"
            | "setWin11UploadWarnDisabled"
            | "setWin11StartupAck" => Ok(json!(true)),
            "getMidiStackStatus" => {
                Ok(json!({"newStack":false,"permanentlyDisabled":false,"startupAck":true}))
            }
            "checkUpdates" => Ok(
                json!({"status":"unsupported","message":"Automatic release updates are disabled for this Tauri development build."}),
            ),
            "showUpdateOffer" => Ok(json!(false)),
            "getLogsEnabled" => Ok(json!(self.logs)),
            "getLogPath" => Ok(json!(self.root.join("logs/editor.log"))),
            "getLogsDir" => Ok(json!(self.root.join("logs"))),
            "logWrite" => self.log(&string(0)?),
            "setZoom" => {
                let factor = arg(0)
                    .as_f64()
                    .filter(|v| v.is_finite() && (0.6..=2.0).contains(v))
                    .ok_or("Zoom must be between 0.6 and 2.0")?;
                app.get_webview_window("main")
                    .ok_or("Window closed")?
                    .set_zoom(factor)
                    .map_err(|e| e.to_string())?;
                self.set("zoomFactor", json!(factor))
            }
            "getCapturesDir" => Ok(json!(self.captures()?)),
            "resetCapturesDir" => {
                self.set("capturesDir", Value::Null)?;
                Ok(json!({"ok":true,"dir":self.captures()?}))
            }
            "chooseCapturesDir" | "chooseExportDir" => {
                match app
                    .dialog()
                    .file()
                    .set_title("Choose folder")
                    .blocking_pick_folder()
                {
                    None => Ok(json!({"ok":false,"canceled":true})),
                    Some(path) => {
                        let path = self.grant(path.into_path().map_err(|e| e.to_string())?)?;
                        if method == "chooseCapturesDir" {
                            self.set("capturesDir", json!(path))?;
                        }
                        Ok(json!({"ok":true,"dir":path}))
                    }
                }
            }
            "chooseImportSource" => {
                match app
                    .dialog()
                    .file()
                    .set_title("Import bank XML or ZIP")
                    .add_filter("Bank XML or ZIP", &["xml", "zip"])
                    .blocking_pick_file()
                {
                    None => Ok(json!({"ok":false,"canceled":true})),
                    Some(path) => Ok(
                        json!({"ok":true,"path":self.grant(path.into_path().map_err(|e|e.to_string())?)?}),
                    ),
                }
            }
            "readImportBank" => files::read_bank(&self.authorized(Path::new(&string(0)?))?),
            "loadTfxDialog" => {
                match app
                    .dialog()
                    .file()
                    .set_title("Load TFX patch")
                    .add_filter("TFX patch", &["tfx"])
                    .blocking_pick_file()
                {
                    None => Ok(json!({"ok":false,"canceled":true})),
                    Some(path) => files::load_tfx(&path.into_path().map_err(|e| e.to_string())?),
                }
            }
            "saveTfx" => {
                let dir = self.captures()?;
                let name = safe_name(arg(0).as_str().unwrap_or("capture"), 32);
                let encoded: Vec<u8> = serde_json::from_value(arg(1)).map_err(|e| e.to_string())?;
                let data = tfx(&decode_7bit(&encoded)?)?;
                let mut filename = format!("{name}.tfx");
                let mut path = dir.join(&filename);
                if arg(2)["incrementIfExists"].as_bool().unwrap_or(false) {
                    let mut n = 2;
                    while path.exists() {
                        filename = format!("{name} ({n}).tfx");
                        path = dir.join(&filename);
                        n += 1;
                    }
                }
                if path.is_symlink() {
                    return Err("Refusing to overwrite a symbolic link".into());
                }
                fs::write(&path, data).map_err(|e| e.to_string())?;
                Ok(json!({"ok":true,"path":path,"filename":filename,"dir":dir}))
            }
            "exportBank" => {
                let folder = self.authorized(Path::new(&string(0)?))?;
                files::export_bank(
                    &folder,
                    &string(1)?,
                    arg(2).as_array().ok_or("Expected bank entries")?,
                )
            }
            "openUserManual" => {
                let path = app
                    .path()
                    .resource_dir()
                    .map_err(|e| e.to_string())?
                    .join("UserManual.txt");
                app.opener()
                    .open_path(path.to_string_lossy(), None::<&str>)
                    .map_err(|e| e.to_string())?;
                Ok(json!({"ok":true}))
            }
            "openPath" => {
                let path = PathBuf::from(string(0)?)
                    .canonicalize()
                    .map_err(|e| e.to_string())?;
                if !path.starts_with(self.root.canonicalize().map_err(|e| e.to_string())?)
                    && path != self.captures()?
                {
                    self.authorized(&path)?;
                }
                app.opener()
                    .open_path(path.to_string_lossy(), None::<&str>)
                    .map_err(|e| e.to_string())?;
                Ok(json!({"ok":true}))
            }
            "openExternal" => {
                let url = string(0)?;
                let parsed = tauri::Url::parse(&url).map_err(|e| e.to_string())?;
                if !["http", "https", "mailto"].contains(&parsed.scheme()) {
                    return Err("Unsupported link scheme".into());
                }
                app.opener()
                    .open_url(url, None::<&str>)
                    .map_err(|e| e.to_string())?;
                Ok(json!(true))
            }
            _ => Err(format!("Unknown native operation: {method}")),
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn preferences_are_atomic_and_reload_in_preview_directory() {
        let root = std::env::temp_dir().join(format!("eleven-tauri-store-{}", std::process::id()));
        let host = Host::new(root.clone(), false).unwrap();
        host.set("zoomFactor", json!(1.2)).unwrap();
        drop(host);
        let host = Host::new(root.clone(), false).unwrap();
        assert_eq!(host.get("zoomFactor", json!(1)), Ok(json!(1.2)));
        assert!(!root.join("settings.json.tmp").exists());
        fs::remove_dir_all(root).unwrap();
    }
}
