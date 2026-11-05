use crate::commands::metrics::invoke_metric;
use crate::ipc::mod_::{AppState, IpcState};
use crate::ipc::transport::spawn_stdout_reader;
use serde_json::Value;
use std::process::Stdio;
use std::sync::Arc;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tokio::io::AsyncWriteExt;
use tokio::process::{ChildStdin, Command};
use tokio::sync::Mutex;

mod commands;
mod ipc;

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            // 1. Create shared IPC state (pending request registry).
            let ipc_state: AppState = Arc::new(Mutex::new(IpcState::new()));
            app.manage(ipc_state.clone());

            // 2. Spawn the Python sidecar via Tauri's shell sidecar API.
            //    Production: sidecar binary is bundled via bundle.externalBin
            //    and looked up by name ("panther-sidecar").
            //    Development: no frozen binary exists yet, so fall back to
            //    spawning `python -m panther.sidecar.server` directly.
            let project_dir = std::env::current_dir()
                .unwrap_or_default()
                .to_string_lossy()
                .to_string();
            let src_dir = format!("{project_dir}/src");

            let (rx, mut child) = match app.shell().sidecar("panther-sidecar") {
                Ok(mut sidecar_cmd) => {
                    sidecar_cmd = sidecar_cmd.env("PYTHONPATH", &src_dir);
                    sidecar_cmd.spawn().expect("failed to spawn Python sidecar")
                }
                Err(_) => {
                    // Dev mode: no bundled binary; spawn python -m directly.
                    eprintln!(
                        "[sidecar] bundled binary not found; falling back to `python -m panther.sidecar.server`"
                    );
                    Command::new("python")
                        .args(["-m", "panther.sidecar.server"])
                        .env("PYTHONPATH", &src_dir)
                        .stdin(Stdio::piped())
                        .stdout(Stdio::piped())
                        .stderr(Stdio::piped())
                        .spawn()
                        .expect("failed to spawn Python sidecar")
                }
            };

            // 3. Take stdio handles from the sidecar child.
            let sidecar_stdin = child.stdin.take().expect("sidecar has no stdin");
            let sidecar_stdout = child.stdout.take().expect("sidecar has no stdout");
            let sidecar_stderr = child.stderr.take().expect("sidecar has no stderr");

            // 4. Manage the sidecar stdin writer so commands can write requests.
            app.manage(Mutex::new(sidecar_stdin));

            // 5. Manage the Child handle so the sidecar stays alive.
            let child_mutex = Mutex::new(Some(child));
            let child_mutex_for_shutdown = child_mutex.clone();
            app.manage(child_mutex);

            // 6. Read stderr diagnostics on a background task.
            tokio::spawn(async move {
                use tokio::io::AsyncBufReadExt;
                let reader = tokio::io::BufReader::new(sidecar_stderr);
                let mut lines = reader.lines();
                while let Ok(Some(line)) = lines.next_line().await {
                    eprintln!("[sidecar stderr] {line}");
                }
            });

            // 7. Spawn the single stdout reader task.
            let ipc_state_for_reader = ipc_state.clone();
            tokio::spawn(async move {
                spawn_stdout_reader(sidecar_stdout, ipc_state_for_reader).await;
            });

            // 8. Drop the exit receiver — we don't monitor sidecar exit in Stage 0.
            drop(rx);

            // 9. Register shutdown handler: kill sidecar process and resolve pending IPC requests.
            let ipc_state_for_shutdown = ipc_state.clone();
            app.on_window_event(move |event| {
                if matches!(event, tauri::WindowEvent::Destroyed(_)) {
                    let child_mutex = child_mutex_for_shutdown.clone();
                    let ipc_state = ipc_state_for_shutdown.clone();
                    tokio::spawn(async move {
                        // Kill the sidecar child process (dev fallback; no-op if already dead).
                        if let Ok(mut guard) = child_mutex.lock().await {
                            if let Some(mut child) = guard.take() {
                                let _ = child.start_kill();
                            }
                        }
                        // Resolve all pending IPC requests so no caller hangs forever.
                        ipc_state.lock().await.resolve_all_not_running();
                    });
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![invoke_metric])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
