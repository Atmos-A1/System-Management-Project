use crate::ipc::mod_::{AppState, JsonRpcRequest, SidecarError};
use serde::Deserialize;
use serde_json::Value;
use std::time::Duration;
use tauri::State;
use tokio::process::ChildStdin;
use tokio::sync::Mutex;

/// Command argument for fetching a metric.
#[derive(Debug, Deserialize)]
pub struct MetricArgs {
    pub method: String,
    #[serde(default)]
    pub params: Option<Value>,
}

/// Invoke a read-only metric on the Python sidecar via JSON-RPC.
///
/// This command:
/// 1. Registers a pending request with a correlation ID.
/// 2. Writes the JSON-RPC request to the sidecar's stdin asynchronously
///    (never blocking Tauri's async runtime).
/// 3. Awaits the matching response on the shared IPC state with a
///    10-second timeout.
/// 4. Returns the result or a controlled error.
#[tauri::command]
pub async fn invoke_metric(
    args: MetricArgs,
    ipc_state: State<'_, AppState>,
    stdin: State<'_, Mutex<ChildStdin>>,
) -> Result<Value, String> {
    // 1. Register pending request
    let (id, mut rx) = {
        let mut guard = ipc_state.lock().await;
        guard.register()
    };

    // 2. Build the request
    let request = JsonRpcRequest {
        jsonrpc: "2.0".to_string(),
        id: id.clone(),
        method: args.method,
        params: args.params,
    };
    let payload = serde_json::to_string(&request).map_err(|e| {
        format!("failed to serialize request: {e}")
    })?;

    // 3. Write to sidecar stdin (async, never blocks the runtime)
    {
        let mut stdin_guard = stdin.lock().await;
        stdin_guard
            .write_all(payload.as_bytes())
            .await
            .map_err(|e| format!("failed to write to sidecar: {e}"))?;
        stdin_guard
            .write_all(b"\n")
            .await
            .map_err(|e| format!("failed to write newline: {e}"))?;
        stdin_guard
            .flush()
            .await
            .map_err(|e| format!("failed to flush sidecar stdin: {e}"))?;
    }

    // 4. Await the response with a timeout
    let response = tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            match tokio::time::timeout(Duration::from_millis(50), &mut rx).await {
                Ok(result) => return result,
                Err(_) => continue, // timeout, keep polling
            }
        }
    })
    .await
    .map_err(|_| "request timed out".to_string())??;

    response.map_err(|e| format!("sidecar error: {e}"))
}
