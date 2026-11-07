use std::sync::Arc;

use super::{AppState, JsonRpcResponse, SidecarError};
use tauri_plugin_shell::process::{CommandChild, CommandEvent};
use tokio::io::AsyncWriteExt;
use tokio::process::{ChildStderr, ChildStdin, ChildStdout};
use tokio::sync::Mutex;

// Maximum size of a single JSON-RPC frame (4 MiB).
const MAX_FRAME_SIZE: usize = 4 * 1024 * 1024;

// Fixed-size async read buffer; also the allowance above MAX_FRAME_SIZE
// before SidecarReader discards buffered data to prevent unbounded growth.
pub const CHUNK_SIZE: usize = 64 * 1024;

/// Concrete handle to a spawned sidecar process, supporting both Tauri
/// production sidecar and Tokio development fallback without forcing
/// incompatible process types into one binding.
pub enum SidecarHandle {
    Tauri(TauriSidecarHandle),
    Tokio(TokioSidecarHandle),
}

/// Tauri production sidecar handle.
///
/// `CommandChild::kill(self)` consumes the child, so ownership is held
/// behind `Mutex<Option<CommandChild>>` to allow at-most-once kill.
pub struct TauriSidecarHandle {
    pub child: Arc<Mutex<Option<CommandChild>>>,
    pub events: Arc<Mutex<Option<tokio::sync::mpsc::Receiver<CommandEvent>>>>,
}

/// Tokio development sidecar handle.
pub struct TokioSidecarHandle {
    pub child: Arc<Mutex<Option<tokio::process::Child>>>,
    pub stdin: Arc<Mutex<Option<ChildStdin>>>,
    pub stdout: Arc<Mutex<Option<ChildStdout>>>,
    pub stderr: Arc<Mutex<Option<ChildStderr>>>,
}

impl SidecarHandle {
    /// Write JSON-RPC request bytes to sidecar stdin.
    pub async fn write(&self, bytes: &[u8]) -> Result<(), SidecarError> {
        match self {
            SidecarHandle::Tauri(h) => {
                let mut guard = h.child.lock().await;
                let child = guard
                    .as_mut()
                    .ok_or_else(|| SidecarError::Transport("sidecar already killed".into()))?;
                child.write(bytes).map_err(|e| {
                    SidecarError::Transport(format!("failed to write to sidecar: {e}"))
                })?;
            }
            SidecarHandle::Tokio(h) => {
                let mut guard = h.stdin.lock().await;
                let stdin = guard
                    .as_mut()
                    .ok_or_else(|| SidecarError::Transport("sidecar already killed".into()))?;
                stdin.write_all(bytes).await.map_err(|e| {
                    SidecarError::Transport(format!("failed to write to sidecar: {e}"))
                })?;
                stdin.flush().await.map_err(|e| {
                    SidecarError::Transport(format!("failed to flush sidecar stdin: {e}"))
                })?;
            }
        }
        Ok(())
    }

    /// Kill the sidecar process. Idempotent — no-op if already killed.
    pub async fn kill(&self) -> Result<(), SidecarError> {
        match self {
            SidecarHandle::Tauri(h) => {
                let mut guard = h.child.lock().await;
                if let Some(child) = guard.take() {
                    let _ = child.kill().map_err(|e| {
                        SidecarError::Transport(format!("failed to kill sidecar: {e}"))
                    });
                }
            }
            SidecarHandle::Tokio(h) => {
                let mut guard = h.child.lock().await;
                if let Some(mut child) = guard.take() {
                    let _ = child.start_kill();
                }
            }
        }
        Ok(())
    }
}

/// SidecarReader accumulates byte chunks from any stdout source, splits
/// on newlines, enforces the 4 MiB frame limit, parses JSON-RPC 2.0
/// responses, and dispatches them to pending requests by correlation ID.
///
/// Source-agnostic: both Tauri `CommandEvent::Stdout` payloads and Tokio
/// `BufReader` lines are fed as `&[u8]` chunks.
pub struct SidecarReader {
    buffer: Vec<u8>,
    state: AppState,
}

impl SidecarReader {
    pub fn new(state: AppState) -> Self {
        Self {
            buffer: Vec::with_capacity(4096),
            state,
        }
    }

    /// Feed a raw byte chunk from any stdout source.
    ///
    /// Splits the accumulated buffer on newlines, enforces the frame
    /// limit per line, parses each line as JSON-RPC, and dispatches the
    /// result to `IpcState` by correlation ID.
    pub async fn feed_chunk(&mut self, chunk: &[u8]) {
        // Process the incoming chunk in fixed-size pieces so memory is
        // bounded regardless of how large a single chunk/payload is.
        for piece in chunk.chunks(CHUNK_SIZE) {
            // Enforce the buffer bound before appending this piece.
            while self.buffer.len() + piece.len() > MAX_FRAME_SIZE + CHUNK_SIZE {
                if let Some(nl) = self.buffer.iter().position(|b| *b == b'\n') {
                    self.buffer.drain(..=nl);
                    eprintln!("sidecar buffer exceeded frame limit, reset at newline");
                } else {
                    self.buffer.clear();
                    eprintln!("sidecar buffer exceeded frame limit without newline, cleared");
                    break;
                }
            }

            self.buffer.extend_from_slice(piece);

            // Process all complete frames now in the buffer.
            while let Some(newline_pos) = self.buffer.iter().position(|b| *b == b'\n') {
                let line = self.buffer.drain(..=newline_pos).collect::<Vec<u8>>();

                // Enforce the 4 MiB frame limit.
                if line.len() > MAX_FRAME_SIZE {
                    eprintln!("sidecar frame exceeds {MAX_FRAME_SIZE} bytes, discarding");
                    continue;
                }

                let line_str = match std::str::from_utf8(&line) {
                    Ok(s) => s.trim_end(),
                    Err(e) => {
                        eprintln!("failed to decode sidecar frame: {e}");
                        continue;
                    }
                };

                if line_str.is_empty() {
                    continue;
                }

                let response: JsonRpcResponse = match serde_json::from_str(line_str) {
                    Ok(r) => r,
                    Err(e) => {
                        eprintln!("failed to parse sidecar response: {e}");
                        continue;
                    }
                };

                let id = response.id.clone();
                let result = if let Some(err) = response.error {
                    Err(SidecarError::MethodError {
                        code: err.code,
                        message: err.message,
                        data: err.data,
                    })
                } else {
                    Ok(response.result.unwrap_or(serde_json::Value::Null))
                };

                let mut state_guard = self.state.lock().await;
                state_guard.resolve(&id, result);
            }
        }
    }

    /// Flush any remaining buffered bytes without a trailing newline.
    /// After flushing, fails all pending requests with NotRunning since
    /// the stdout stream has closed.
    pub async fn flush(&mut self) {
        if !self.buffer.is_empty() {
            let line = std::mem::take(&mut self.buffer);
            if line.len() > MAX_FRAME_SIZE {
                eprintln!("sidecar frame exceeds {MAX_FRAME_SIZE} bytes, discarding");
            } else if let Ok(line_str) = std::str::from_utf8(&line) {
                let line_str = line_str.trim_end();
                if !line_str.is_empty() {
                    let response: JsonRpcResponse = match serde_json::from_str(line_str) {
                        Ok(r) => r,
                        Err(e) => {
                            eprintln!("failed to parse sidecar response: {e}");
                            // Still need to fail pending requests
                            self.fail_all().await;
                            return;
                        }
                    };
                    let id = response.id.clone();
                    let result = if let Some(err) = response.error {
                        Err(SidecarError::MethodError {
                            code: err.code,
                            message: err.message,
                            data: err.data,
                        })
                    } else {
                        Ok(response.result.unwrap_or(serde_json::Value::Null))
                    };
                    let mut state_guard = self.state.lock().await;
                    state_guard.resolve(&id, result);
                }
            }
        }
        // Stdout stream closed - fail all remaining pending requests
        self.fail_all().await;
        eprintln!("sidecar stdout stream closed");
    }

    /// Resolve all pending requests with NotRunning error.
    /// Called when the sidecar process terminates or stdout closes.
    async fn fail_all(&mut self) {
        let mut state_guard = self.state.lock().await;
        state_guard.resolve_all_not_running();
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::ipc::IpcState;
    use tokio::sync::Mutex;

    async fn setup_state_and_request() -> (
        AppState,
        String,
        tokio::sync::oneshot::Receiver<Result<serde_json::Value, SidecarError>>,
    ) {
        let state: AppState = Arc::new(Mutex::new(IpcState::new()));
        let (id, rx) = state.lock().await.register();
        (state, id, rx)
    }

    fn valid_response(id: &str) -> Vec<u8> {
        let response = serde_json::json!({
            "jsonrpc": "2.0",
            "id": id,
            "result": {"cpu": 42.5}
        });
        format!("{response}\n").into_bytes()
    }

    #[tokio::test]
    async fn test_feed_chunk_valid_frame_resolves_request() {
        let (state, id, rx) = setup_state_and_request().await;
        let mut reader = SidecarReader::new(state);
        reader.feed_chunk(&valid_response(&id)).await;

        let result = rx.await.expect("channel closed");
        assert!(result.is_ok());
        assert_eq!(result.unwrap(), serde_json::json!({"cpu": 42.5}));
    }

    #[tokio::test]
    async fn test_feed_chunk_oversized_frame_cleared_without_newline() {
        let (state, _id, mut rx) = setup_state_and_request().await;
        let mut reader = SidecarReader::new(state);

        let oversized = vec![b'a'; MAX_FRAME_SIZE + CHUNK_SIZE + 100];
        reader.feed_chunk(&oversized).await;

        assert!(rx.try_recv().is_err());
        assert!(reader.buffer.len() <= CHUNK_SIZE);
        assert!(reader.buffer.len() < MAX_FRAME_SIZE);
    }

    #[tokio::test]
    async fn test_feed_chunk_oversized_discarded_through_newline() {
        let (state, id, mut rx) = setup_state_and_request().await;
        let mut reader = SidecarReader::new(state);

        let mut oversized = vec![b'a'; MAX_FRAME_SIZE + 100];
        oversized.push(b'\n');
        reader.feed_chunk(&oversized).await;

        assert!(rx.try_recv().is_err());
        assert!(reader.buffer.is_empty());

        reader.feed_chunk(&valid_response(&id)).await;
        let result = rx.await.expect("channel closed");
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_feed_chunk_split_across_chunks() {
        let (state, id, mut rx) = setup_state_and_request().await;
        let mut reader = SidecarReader::new(state);

        let full = valid_response(&id);
        let mid = full.len() / 2;

        reader.feed_chunk(&full[..mid]).await;
        assert!(rx.try_recv().is_err());

        reader.feed_chunk(&full[mid..]).await;
        let result = rx.await.expect("channel closed");
        assert!(result.is_ok());
    }

    #[tokio::test]
    async fn test_feed_chunk_multiple_frames_in_one_chunk() {
        let state: AppState = Arc::new(Mutex::new(IpcState::new()));
        let (id1, rx1) = state.lock().await.register();
        let (id2, rx2) = state.lock().await.register();
        let mut reader = SidecarReader::new(state);

        let mut combined = valid_response(&id1);
        combined.extend_from_slice(&valid_response(&id2));

        reader.feed_chunk(&combined).await;

        let r1 = rx1.await.expect("channel closed");
        let r2 = rx2.await.expect("channel closed");
        assert!(r1.is_ok());
        assert!(r2.is_ok());
    }

    #[tokio::test]
    async fn test_feed_chunk_oversized_buffer_bound() {
        let (state, _id, mut rx) = setup_state_and_request().await;
        let mut reader = SidecarReader::new(state);

        let oversized = vec![b'a'; MAX_FRAME_SIZE + CHUNK_SIZE + 1000];
        reader.feed_chunk(&oversized).await;

        assert!(reader.buffer.len() <= MAX_FRAME_SIZE + CHUNK_SIZE);
        assert!(rx.try_recv().is_err());
    }

    #[tokio::test]
    async fn test_flush_fails_pending_requests() {
        let state: AppState = Arc::new(Mutex::new(IpcState::new()));
        let (id1, rx1) = state.lock().await.register();
        let (id2, rx2) = state.lock().await.register();
        let mut reader = SidecarReader::new(state);

        // No data fed, just flush - should fail both pending requests
        reader.flush().await;

        let r1 = rx1.await.expect("channel closed");
        let r2 = rx2.await.expect("channel closed");
        assert!(matches!(r1, Err(SidecarError::NotRunning)));
        assert!(matches!(r2, Err(SidecarError::NotRunning)));
    }

    #[tokio::test]
    async fn test_flush_processes_buffer_then_fails_remaining() {
        let state: AppState = Arc::new(Mutex::new(IpcState::new()));
        let (id1, rx1) = state.lock().await.register();
        let (id2, rx2) = state.lock().await.register();
        let mut reader = SidecarReader::new(state);

        // Feed one valid response, then flush
        reader.feed_chunk(&valid_response(&id1)).await;
        reader.flush().await;

        // id1 should get the response, id2 should get NotRunning
        let r1 = rx1.await.expect("channel closed");
        let r2 = rx2.await.expect("channel closed");
        assert!(r1.is_ok());
        assert!(matches!(r2, Err(SidecarError::NotRunning)));
    }

    #[tokio::test]
    async fn test_late_response_after_flush_ignored() {
        let state: AppState = Arc::new(Mutex::new(IpcState::new()));
        let (id, rx) = state.lock().await.register();
        let mut reader = SidecarReader::new(state);

        // Flush first (fails pending)
        reader.flush().await;
        // Then feed a late response for the same ID
        reader.feed_chunk(&valid_response(&id)).await;

        // The late response should be ignored (channel already closed)
        let r = rx.await.expect("channel closed");
        assert!(matches!(r, Err(SidecarError::NotRunning)));
    }
}
