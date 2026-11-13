use crate::commands::metrics::invoke_metric;
use crate::ipc::transport::{SidecarHandle, CHUNK_SIZE};
use crate::ipc::{AppState, IpcState, SidecarRef};
use std::path::PathBuf;
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

/// Resolve the Python package root directory (the one containing `panther/`).
///
/// When running via `cargo run` from `src-tauri`, `std::env::current_dir()` returns
/// `<repo>/src-tauri`, but the Python package lives at `<repo>/src` (sibling of `src-tauri`).
/// This function finds it robustly by checking candidates in order:
/// 1. Walking up from `current_dir()` to find a directory containing
///    `src/panther/sidecar` (verifies the real package layout at runtime).
/// 2. `CARGO_MANIFEST_DIR/../src` (compile-time known, correct for dev runs
///    where the manifest dir is `<repo>/src-tauri`).
/// If neither is verified, it still returns candidate 2 and logs a diagnostic.
fn resolve_dev_src_dir() -> PathBuf {
    // Candidate 1: CARGO_MANIFEST_DIR/../src (compile-time known, correct for dev)
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let candidate1 = manifest_dir.join("../src");

    // Candidate 2: walk up from current_dir looking for src/panther/sidecar
    let mut candidate2 = None;
    if let Ok(cwd) = std::env::current_dir() {
        let mut dir = Some(cwd.as_path());
        while let Some(d) = dir {
            let check = d.join("src/panther/sidecar");
            if check.exists() {
                candidate2 = Some(d.join("src"));
                break;
            }
            dir = d.parent();
        }
    }

    // Prefer the runtime-verified cwd walk; fall back to the manifest-relative path.
    match candidate2 {
        Some(dir) => dir,
        None => {
            eprintln!(
                "[sidecar] could not locate Python package root via cwd walk; using CARGO_MANIFEST_DIR/../src = {}",
                candidate1.display()
            );
            candidate1
        }
    }
}

/// Kill the sidecar and fail any outstanding IPC requests.
/// Uses `tauri::async_runtime::spawn` because window event callbacks run on
/// the GTK main thread, outside any Tokio runtime context (`tokio::spawn`
/// panics there).
fn spawn_sidecar_cleanup(handle: SidecarRef, ipc_state: AppState) {
    tauri::async_runtime::spawn(async move {
        if let Some(h) = &*handle.lock().await {
            let _ = h.kill().await;
        }
        ipc_state.lock().await.resolve_all_not_running();
    });
}

fn spawn_dev_sidecar(src_dir: &str) -> SidecarHandle {
    let mut child = Command::new("python")
        .args(["-m", "panther.sidecar.server"])
        .env("PYTHONPATH", src_dir)
        .env("PANTHER_PARENT_PID", std::process::id().to_string())
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("PYTHONUNBUFFERED", "1")
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
            let src_dir = resolve_dev_src_dir()
                .to_string_lossy()
                .to_string();

            // SidecarRef: Arc<Option<SidecarHandle>> — always managed, Some on success, None on failure.
            let sidecar_ref: SidecarRef = Arc::new(Mutex::new(None));

            let sidecar_result = app
                .shell()
                .sidecar("panther-sidecar")
                .map(|cmd| {
                    // The frozen sidecar is a PyInstaller onefile executable:
                    // a level-1 bootloader plus a level-2 child hosting the
                    // interpreter. Killing only the direct child leaves the
                    // grandchild running. `set_process_group` puts the whole
                    // tree in a job object (Windows) / process group (POSIX)
                    // so `send_kill()` terminates all of it.
                    cmd.set_process_group(true)
                        .env("PANTHER_PARENT_PID", std::process::id().to_string())
                        .env("PYTHONUTF8", "1")
                        .env("PYTHONIOENCODING", "utf-8")
                        .env("PYTHONUNBUFFERED", "1")
                })
                .and_then(|cmd| cmd.spawn());

            let sidecar_handle: SidecarHandle = match sidecar_result {
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
                        // In production, we still manage the ref as None so the app doesn't crash.
                        // Commands will return an honest "not running" error.
                        *sidecar_ref.lock().await = None;
                        // Still manage IPC state and ref so the app starts.
                        app.manage(ipc_state.clone());
                        app.manage(sidecar_ref.clone());
                        // Return Ok(()) so the app launches and surfaces the honest error via commands.
                        return Ok(());
                    }
                }
            };

            // Store the successful handle in the ref
            *sidecar_ref.lock().await = Some(sidecar_handle);

            // 3. Manage IPC state and sidecar ref (always managed, even if sidecar is None).
            app.manage(ipc_state.clone());
            app.manage(sidecar_ref.clone());

            // 4. Read stderr diagnostics on a background task (source-agnostic).
            let handle_for_stderr = sidecar_ref.clone();
            tokio::spawn(async move {
                let guard = handle_for_stderr.lock().await;
                if let Some(handle) = guard.as_ref() {
                    match handle {
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
                }
            });

            // 5. Spawn the single stdout reader task (source-agnostic byte parsing).
            let ipc_state_for_reader = ipc_state.clone();
            let handle_for_reader = sidecar_ref.clone();
            tokio::spawn(async move {
                let guard = handle_for_reader.lock().await;
                if let Some(handle) = guard.as_ref() {
                    match handle {
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
                                            // Take the child out of the handle so subsequent writes fail fast.
                                            let _ = h.child.lock().await.take();
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
                }
            });

            // 6. Register shutdown handler: kill sidecar process and resolve pending IPC requests.
            let handle_for_shutdown = sidecar_ref.clone();
            let ipc_state_for_shutdown = ipc_state.clone();
            let window = app
                .get_webview_window("main")
                .expect("main window not found");
            window.on_window_event(move |event| {
                if matches!(event, tauri::WindowEvent::Destroyed) {
                    spawn_sidecar_cleanup(handle_for_shutdown.clone(), ipc_state_for_shutdown.clone());
                }
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![invoke_metric])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ipc::{SidecarError, SidecarRef};

    #[test]
    fn dev_src_dir_points_at_python_package_root() {
        let src_dir = resolve_dev_src_dir();
        // The resolved path must contain panther/sidecar (the Python package)
        let sidecar_dir = src_dir.join("panther/sidecar");
        assert!(
            sidecar_dir.exists(),
            "resolved src_dir {:?} does not contain panther/sidecar",
            src_dir
        );
        // It must NOT be the src-tauri/src directory (which doesn't have panther/)
        let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
        let wrong_dir = manifest_dir.join("src");
        assert_ne!(
            src_dir, wrong_dir,
            "resolved src_dir incorrectly points at src-tauri/src"
        );
    }

    #[test]
    fn cleanup_runs_outside_tokio_runtime() {
        // Window event callbacks run on the GTK main thread, outside any Tokio
        // runtime. This test deliberately runs on a plain std thread with no
        // ambient runtime: `tokio::spawn` would panic here, `tauri::async_runtime::spawn` must not.
        // Build IPC state with two pending requests — no lock needed since we
        // populate it before wrapping in the mutex.
        let mut ipc = IpcState::new();
        let (_id1, rx1) = ipc.register();
        let (_id2, rx2) = ipc.register();
        let state: AppState = Arc::new(Mutex::new(ipc));

        // Build a SidecarRef with None (simulating sidecar not running).
        let handle: SidecarRef = Arc::new(Mutex::new(None));

        // Call the cleanup function directly — this test fn has no #[tokio::test],
        // so there is NO Tokio runtime. This would panic with tokio::spawn.
        spawn_sidecar_cleanup(handle, state);

        // Wait for the async tasks to complete by blocking on the receivers.
        // tokio::sync::oneshot::Receiver::blocking_recv() blocks until a value
        // or closed channel, and does not require a runtime.
        let r1 = rx1.blocking_recv().expect("channel closed");
        let r2 = rx2.blocking_recv().expect("channel closed");
        assert!(matches!(r1, Err(SidecarError::NotRunning)));
        assert!(matches!(r2, Err(SidecarError::NotRunning)));
    }
}
