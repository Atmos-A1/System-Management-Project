use crate::commands::metrics::invoke_metric;
use crate::ipc::mod_::{AppState, IpcState};
use crate::ipc::transport::spawn_stdout_reader;
use serde_json::Value;
use std::process::Stdio;
use std::sync::Arc;
use tauri::Manager;
use tokio::io::AsyncWriteExt;
use tokio::process::{Command, Child, ChildStdin};
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

            // 2. Determine the project source directory for PYTHONPATH.
            let project_dir = std::env::var("PANTHER_PROJECT_DIR")
                .unwrap_or_else(|_| {
                    std::env::current_dir()
                        .unwrap_or_default()
                        .to_string_lossy()
                        .to_string()
                });
            let src_dir = format!("{project_dir}/src");

            // 3. Spawn the Python sidecar process.
            let mut child = Command::new("python")
                .args(["-m", "panther.sidecar.server"])
                .env("PYTHONPATH", &src_dir)
                .env("PANTHER_PROJECT_DIR", &project_dir)
                .stdin(Stdio::piped())
                .stdout(Stdio::piped())
                .stderr(Stdio::piped())
                .spawn()
                .expect("failed to spawn Python sidecar");

            // 4. Take stdio handles from the child.
            let sidecar_stdin = child.stdin.take().expect("sidecar has no stdin");
            let sidecar_stdout = child.stdout.take().expect("sidecar has no stdout");
            let sidecar_stderr = child.stderr.take().expect("sidecar has no stderr");

            // 5. Manage the sidecar stdin writer so commands can write requests.
            app.manage(Mutex::new(sidecar_stdin));

            // 6. Manage the Child handle so the sidecar stays alive.
            app.manage(Mutex::new(Some(child)));

            // 7. Read stderr diagnostics on a background task.
            tokio::spawn(async move {
                use tokio::io::AsyncBufReadExt;
                let reader = tokio::io::BufReader::new(sidecar_stderr);
                let mut lines = reader.lines();
                while let Ok(Some(line)) = lines.next_line().await {
                    eprintln!("[sidecar stderr] {line}");
                }
            });

            // 8. Spawn the single stdout reader task.
            let ipc_state_for_reader = ipc_state.clone();
            tokio::spawn(async move {
                spawn_stdout_reader(sidecar_stdout, ipc_state_for_reader).await;
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![invoke_metric])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
