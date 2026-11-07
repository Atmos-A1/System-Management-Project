use crate::commands::metrics::invoke_metric;
use crate::ipc::{AppState, IpcState};
use crate::ipc::transport::{
    CommandEvent, SidecarHandle, TauriSidecarHandle, TokioSidecarHandle,
};
use std::process::Stdio;
use std::sync::Arc;
use tauri::Manager;
use tauri_plugin_shell::ShellExt;
use tokio::io::{AsyncBufReadExt, AsyncReadExt};
use tokio::process::Command;
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

            let handle: SidecarHandle = match app.shell().sidecar("panther-sidecar") {
                Ok(mut sidecar_cmd) => {
                    sidecar_cmd = sidecar_cmd.env("PYTHONPATH", &src_dir);
                    let (events, child) = sidecar_cmd
                        .spawn()
                        .expect("failed to spawn Python sidecar");
                    SidecarHandle::Tauri(TauriSidecarHandle {
                        child: Arc::new(Mutex::new(Some(child))),
                        events,
                    })
                }
                Err(_) => {
                    // Dev mode: no bundled binary; spawn python -m directly.
                    eprintln!(
                        "[sidecar] bundled binary not found; falling back to `python -m panther.sidecar.server`"
                    );
                    let mut child = Command::new("python")
                        .args(["-m", "panther.sidecar.server"])
                        .env("PYTHONPATH", &src_dir)
                        .stdin(Stdio::piped())
                        .stdout(Stdio::piped())
                        .stderr(Stdio::piped())
                        .spawn()
                        .expect("failed to spawn Python sidecar");
                    let stdin = child.stdin.take().expect("sidecar has no stdin");
                    let stdout = child.stdout.take().expect("sidecar has no stdout");
                    let stderr = child.stderr.take().expect("sidecar has no stderr");
                    SidecarHandle::Tokio(TokioSidecarHandle {
                        child: Arc::new(Mutex::new(Some(child))),
                        stdin: Arc::new(Mutex::new(Some(stdin))),
                        stdout: Arc::new(Mutex::new(Some(stdout))),
                        stderr: Arc::new(Mutex::new(Some(stderr))),
                    })
                }
            };

            // 3. Manage the sidecar handle so commands can write requests.
            app.manage(handle.clone());

            // 4. Read stderr diagnostics on a background task (source-agnostic).
            match &handle {
                SidecarHandle::Tauri(_) => {
                    // Stderr handled by the events consumer below.
                }
                SidecarHandle::Tokio(h) => {
                    let stderr = h.stderr.clone();
                    tokio::spawn(async move {
                        let reader =
                            tokio::io::BufReader::new(stderr.lock().await.take().expect("sidecar has no stderr"));
                        let mut lines = reader.lines();
                        while let Ok(Some(line)) = lines.next_line().await {
                            eprintln!("[sidecar stderr] {line}");
                        }
                    });
                }
            }

            // 5. Spawn the single stdout reader task (source-agnostic byte parsing).
            let ipc_state_for_reader = ipc_state.clone();
            match &handle {
                SidecarHandle::Tauri(h) => {
                    let mut events = h.events;
                    let state = ipc_state_for_reader.clone();
                    tokio::spawn(async move {
                        let mut reader = crate::ipc::transport::SidecarReader::new(state);
                        while let Some(event) = events.recv().await {
                            match event {
                                CommandEvent::Stdout(payload) => {
                                    reader.feed_chunk(&payload).await;
                                }
                                CommandEvent::Stderr(payload) => {
                                    eprintln!(
                                        "[sidecar stderr] {}",
                                        String::from_utf8_lossy(&payload)
                                    );
                                }
                                CommandEvent::Terminated(code) => {
                                    eprintln!("[sidecar] exited with code {code}");
                                    break;
                                }
                                CommandEvent::Error(msg) => {
                                    eprintln!("[sidecar] error: {msg}");
                                    break;
                                }
                            }
                        }
                        reader.flush().await;
                    });
                }
                SidecarHandle::Tokio(h) => {
                    let stdout = h.stdout.clone();
                    let state = ipc_state_for_reader.clone();
                    tokio::spawn(async move {
                        let mut reader = crate::ipc::transport::SidecarReader::new(state);
                        let stdout_handle =
                            stdout.lock().await.take().expect("sidecar has no stdout");
                        let mut stdout_reader = tokio::io::BufReader::new(stdout_handle);
                        let mut buf = [0u8; crate::ipc::transport::CHUNK_SIZE];
                        loop {
                            let n = match stdout_reader.read(&mut buf).await {
                                Ok(0) => break, // EOF
                                Ok(n) => n,
                                Err(e) => {
                                    eprintln!("sidecar stdout read error: {e}");
                                    break;
                                }
                            };
                            reader.feed_chunk(&buf[..n]).await;
                        }
                        reader.flush().await;
                    });
                }
            }

            // 6. Register shutdown handler: kill sidecar process and resolve pending IPC requests.
            let handle_for_shutdown = handle.clone();
            let ipc_state_for_shutdown = ipc_state.clone();
            let window = app
                .get_webview_window("main")
                .expect("main window not found");
            window.on_window_event(move |event| {
                if matches!(event, tauri::WindowEvent::Destroyed) {
                    let handle = handle_for_shutdown.clone();
                    let ipc_state = ipc_state_for_shutdown.clone();
                    tokio::spawn(async move {
                        handle.kill();
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
