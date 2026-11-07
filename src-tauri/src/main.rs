use crate::commands::metrics::invoke_metric;
use crate::ipc::transport::{SidecarHandle, CHUNK_SIZE};
use crate::ipc::{AppState, IpcState};
use std::process::Stdio;
use std::sync::Arc;
use tauri::Manager;
use tauri_plugin_shell::process::CommandEvent;
use tauri_plugin_shell::ShellExt;
use tokio::io::{AsyncBufReadExt, AsyncReadExt};
use tokio::process::Command;
use tokio::sync::Mutex;

mod commands;
mod ipc;

fn spawn_dev_sidecar(src_dir: &str) -> SidecarHandle {
    let mut child = Command::new("python")
        .args(["-m", "panther.sidecar.server"])
        .env("PYTHONPATH", src_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true)
        .spawn()
        .expect("failed to spawn Python sidecar (dev fallback)");
    let stdin = child.stdin.take().expect("sidecar has no stdin");
    let stdout = child.stdout.take().expect("sidecar has no stdout");
    let stderr = child.stderr.take().expect("sidecar has no stderr");
    SidecarHandle::Tokio(crate::ipc::transport::TokioSidecarHandle {
        child: Arc::new(Mutex::new(Some(child))),
        stdin: Arc::new(Mutex::new(Some(stdin))),
        stdout: Arc::new(Mutex::new(Some(stdout))),
        stderr: Arc::new(Mutex::new(Some(stderr))),
    })
}

fn main() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .plugin(tauri_plugin_fs::init())
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_notification::init())
        .setup(|app| {
            // Tauri runs `setup` on the main thread outside the Tokio runtime
            // context. Both `tokio::spawn` and `tokio::process::Command::spawn`
            // (used by the dev fallback) require the thread-local runtime
            // context, so enter it for the duration of the setup hook.
            let runtime = tauri::async_runtime::handle();
            let _runtime_guard = runtime.inner().enter();

            // 1. Create shared IPC state (pending request registry).
            let ipc_state: AppState = Arc::new(Mutex::new(IpcState::new()));

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

            let sidecar_handle: SidecarHandle = match app
                .shell()
                .sidecar("panther-sidecar")
                .map(|cmd| cmd.env("PYTHONPATH", &src_dir))
                .and_then(|cmd| cmd.spawn())
            {
                Ok((events, child)) => SidecarHandle::Tauri(crate::ipc::transport::TauriSidecarHandle {
                    child: Arc::new(Mutex::new(Some(child))),
                    events: Arc::new(Mutex::new(Some(events))),
                }),
                Err(err) => {
                    if tauri::is_dev() {
                        eprintln!(
                            "[sidecar] bundled sidecar unavailable ({err}); falling back to `python -m panther.sidecar.server`"
                        );
                        spawn_dev_sidecar(&src_dir)
                    } else {
                        eprintln!("[sidecar] failed to spawn bundled sidecar: {err}");
                        return Err(format!("failed to spawn bundled sidecar: {err}").into());
                    }
                }
            };

            // 3. Manage IPC state and sidecar handle (only after successful spawn).
            app.manage(ipc_state.clone());
            let handle = Arc::new(sidecar_handle);
            app.manage(handle.clone());

            // 4. Read stderr diagnostics on a background task (source-agnostic).
            match &*handle {
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
            match &*handle {
                SidecarHandle::Tauri(h) => {
                    let events = h.events.clone();
                    let state = ipc_state_for_reader.clone();
                    tokio::spawn(async move {
                        let mut reader = crate::ipc::transport::SidecarReader::new(state);
                        loop {
                            let event = {
                                let mut guard = events.lock().await;
                                match guard.as_mut() {
                                    Some(rx) => rx.recv().await,
                                    None => None,
                                }
                            };
                            match event {
                                Some(CommandEvent::Stdout(payload)) => {
                                    reader.feed_chunk(&payload).await;
                                }
                                Some(CommandEvent::Stderr(payload)) => {
                                    eprintln!(
                                        "[sidecar stderr] {}",
                                        String::from_utf8_lossy(&payload)
                                    );
                                }
                                Some(CommandEvent::Terminated(payload)) => {
                                    eprintln!("[sidecar] exited with code {:?}, signal {:?}", payload.code, payload.signal);
                                    break;
                                }
                                Some(CommandEvent::Error(msg)) => {
                                    eprintln!("[sidecar] error: {msg}");
                                    break;
                                }
                                Some(_) => {
                                    // Non-exhaustive enum catch-all
                                    eprintln!("[sidecar] unexpected event");
                                }
                                None => break, // channel closed
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
                        let mut buf = [0u8; CHUNK_SIZE];
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
                        let _ = handle.kill().await;
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
