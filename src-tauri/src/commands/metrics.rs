use crate::ipc::{AppState, JsonRpcRequest, SidecarError};
use serde::Deserialize;
use serde_json::Value;
use std::sync::Arc;
use std::time::Duration;
use tauri::State;

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
    stdin: State<'_, Arc<crate::ipc::transport::SidecarHandle>>,
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

    // 3. Serialize
    let payload = match serde_json::to_string(&request) {
        Ok(p) => p,
        Err(e) => {
            ipc_state.lock().await.cancel(&id);
            return Err(format!("failed to serialize request: {e}"));
        }
    };

    // 4. Write to sidecar stdin (async, never blocks the runtime)
    if let Err(e) = stdin.write(payload.as_bytes()).await {
        // Clean up pending entry on write error
        ipc_state.lock().await.cancel(&id);
        return Err(format!("failed to write to sidecar: {e}"));
    }

    // 5. Await response with 10s timeout
    let response = tokio::time::timeout(Duration::from_secs(10), async {
        loop {
            match tokio::time::timeout(Duration::from_millis(50), &mut rx).await {
                Ok(Ok(inner)) => return inner, // inner: Result<Value, SidecarError>
                Ok(Err(_)) => {
                    return Err(SidecarError::Transport(
                        "oneshot channel closed without response".into(),
                    ))
                }
                Err(_) => continue,
            }
        }
    })
    .await;

    match response {
        Ok(inner) => Ok(inner?), // SidecarError -> String via existing From impl
        Err(_) => {
            ipc_state.lock().await.cancel(&id);
            Err("request timed out".to_string())
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Guard the Tauri v2 contract: the frontend invoke.ts must pass the `args` wrapper
    /// because the Rust command parameter is named `args`.
    #[test]
    fn frontend_invoke_ts_wraps_payload_in_args() {
        let invoke_ts = include_str!("../../frontend/src/lib/invoke.ts");
        // Tauri v2 passes command arguments by name, so the JS payload must be { args: { ... } }
        assert!(
            invoke_ts.contains("invoke_metric"),
            "invoke.ts must call invoke(\"invoke_metric\", ...)"
        );
        assert!(
            invoke_ts.contains("args:"),
            "invoke.ts must wrap the payload in an `args:` key to match the Rust command parameter name (Tauri v2 contract)"
        );
        assert!(
            invoke_ts.contains("method:"),
            "invoke.ts must include the method field inside the args wrapper"
        );
    }

    /// Test that MetricArgs deserializes from the exact inner object shape the frontend builds.
    #[test]
    fn metric_args_deserializes_from_inner_object() {
        let json = r#"{"method":"system_monitor.get_cpu_percent","params":{}}"#;
        let args: MetricArgs =
            serde_json::from_str(json).expect("failed to deserialize MetricArgs");
        assert_eq!(args.method, "system_monitor.get_cpu_percent");
        assert_eq!(
            args.params,
            Some(serde_json::Value::Object(serde_json::Map::new()))
        );
    }

    /// Test that MetricArgs handles missing params (defaults to None).
    #[test]
    fn metric_args_deserializes_without_params() {
        let json = r#"{"method":"system_monitor.get_ram_usage"}"#;
        let args: MetricArgs =
            serde_json::from_str(json).expect("failed to deserialize MetricArgs");
        assert_eq!(args.method, "system_monitor.get_ram_usage");
        assert_eq!(args.params, None);
    }
}
