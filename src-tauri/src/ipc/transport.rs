use super::{AppState, JsonRpcResponse, SidecarError};
use std::io::{BufRead, BufReader};
use tokio::process::ChildStdout;

// Maximum size of a single JSON-RPC frame (4 MiB).
const MAX_FRAME_SIZE: usize = 4 * 1024 * 1024;

/// Spawns the single stdout-reader task for the sidecar.
///
/// This task reads newline-delimited JSON-RPC responses from the
/// sidecar's stdout and dispatches them to pending requests by their
/// correlation ID. It is the *only* reader of the sidecar stdout stream
/// -- commands never read stdout independently.
pub async fn spawn_stdout_reader(
    stdout: ChildStdout,
    state: AppState,
) -> tokio::task::JoinHandle<()> {
    let reader = BufReader::new(stdout);
    let mut lines = reader.lines();

    tokio::spawn(async move {
        while let Some(line_result) = lines.next_line().await {
            let line = match line_result {
                Ok(l) => l,
                Err(e) => {
                    eprintln!("sidecar stdout read error: {e}");
                    break;
                }
            };

            if line.trim().is_empty() {
                continue;
            }

            // Enforce the 4 MiB frame limit.
            if line.len() > MAX_FRAME_SIZE {
                eprintln!("sidecar frame exceeds {MAX_FRAME_SIZE} bytes, discarding");
                continue;
            }

            let response: JsonRpcResponse = match serde_json::from_str(&line) {
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

            let mut state_guard = state.lock().await;
            state_guard.resolve(&id, result);
            // Guard is dropped here (end of scope).
        }

        eprintln!("sidecar stdout stream closed");
    })
}
