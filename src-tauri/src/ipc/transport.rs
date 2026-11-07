use std::sync::Arc;

use super::{AppState, JsonRpcResponse, SidecarError};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::process::{ChildStderr, ChildStdin, ChildStdout};

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
    child: Arc<Mutex<Option<tauri_plugin_shell::CommandChild>>>,
    events: tokio::sync::mpsc::Receiver<CommandEvent>,
}

/// Tokio development sidecar handle.
pub struct TokioSidecarHandle {
    child: Arc<Mutex<Option<tokio::process::Child>>>,
    stdin: Arc<Mutex<Option<ChildStdin>>>,
    stdout: Arc<Mutex<Option<ChildStdout>>>,
    stderr: Arc<Mutex<Option<ChildStderr>>>,
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
                child.write(bytes).await.map_err(|e| {
                    SidecarError::Transport(format!("failed to write to sidecar: {e}"))
                })?;
            }
            SidecarHandle::Tokio(h) => {
                let mut guard = h.stdin.lock().await;
                let stdin = guard
                    .as_mut()
                    .ok_or_else(|| SidecarError::Transport("sidecar already killed".into()))?;
                stdin
                    .write_all(bytes)
                    .await
                    .map_err(|e| SidecarError::Transport(format!("failed to write to sidecar: {e}")))?;
                stdin.flush().await.map_err(|e| {
                    SidecarError::Transport(format!("failed to flush sidecar stdin: {e}"))
                })?;
            }
        }
        Ok(())
    }

    /// Kill the sidecar process. Idempotent — no-op if already killed.
    pub fn kill(&self) -> Result<(), SidecarError> {
        match self {
            SidecarHandle::Tauri(h) => {
                let mut guard = h.child.lock().unwrap();
                if let Some(mut child) = guard.take() {
                    child.kill();
                }
            }
            SidecarHandle::Tokio(h) => {
                let mut guard = h.child.lock().unwrap();
                if let Some(mut child) = guard.take() {
                    child.start_kill();
                }
            }
        }
        Ok(())
    }

    /// Take the event receiver for Tauri stdout/stderr dispatch.
    /// Returns None for Tokio variant (uses direct handles instead).
    pub fn take_events(&mut self) -> Option<tokio::sync::mpsc::Receiver<CommandEvent>> {
        match self {
            SidecarHandle::Tauri(h) => Some(h.events),
            SidecarHandle::Tokio(_) => None,
        }
    }
}

/// Tauri event from the shell sidecar.
pub enum CommandEvent {
    Stdout(Vec<u8>),
    Stderr(Vec<u8>),
    Terminated(i32),
    Error(String),
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
    pub async fn flush(&mut self) {
        if !self.buffer.is_empty() {
            let line = std::mem::take(&mut self.buffer);
            if line.len() > MAX_FRAME_SIZE {
                eprintln!("sidecar frame exceeds {MAX_FRAME_SIZE} bytes, discarding");
                return;
            }
            if let Ok(line_str) = std::str::from_utf8(&line) {
                let line_str = line_str.trim_end();
                if !line_str.is_empty() {
                    let response: JsonRpcResponse = match serde_json::from_str(line_str) {
                        Ok(r) => r,
                        Err(e) => {
                            eprintln!("failed to parse sidecar response: {e}");
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
        eprintln!("sidecar stdout stream closed");
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
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
        let (state, id, rx) = setup_state_and_request().await;
        let mut reader = SidecarReader::new(state);

        let oversized = vec![b'a'; MAX_FRAME_SIZE + CHUNK_SIZE + 100];
        reader.feed_chunk(&oversized).await;

        assert!(rx.try_recv().is_err());
        assert!(reader.buffer.is_empty());
    }

    #[tokio::test]
    async fn test_feed_chunk_oversized_discarded_through_newline() {
        let (state, id, rx) = setup_state_and_request().await;
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
        let (state, id, rx) = setup_state_and_request().await;
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
        let (state, id1, rx1) = setup_state_and_request().await;
        let (_, id2, rx2) = setup_state_and_request().await;
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
        let (state, id, rx) = setup_state_and_request().await;
        let mut reader = SidecarReader::new(state);

        let oversized = vec![b'a'; MAX_FRAME_SIZE + CHUNK_SIZE + 1000];
        reader.feed_chunk(&oversized).await;

        assert!(reader.buffer.len() <= MAX_FRAME_SIZE + CHUNK_SIZE);
        assert!(rx.try_recv().is_err());
    }
}
