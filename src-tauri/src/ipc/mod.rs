use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::HashMap;
use std::sync::Arc;
use tokio::sync::Mutex;

/// A pending JSON-RPC request awaiting its response.
#[derive(Debug)]
struct PendingRequest {
    responder: tokio::sync::oneshot::Sender<Result<Value, SidecarError>>,
}

/// A JSON-RPC 2.0 request to send to the sidecar.
#[derive(Debug, Serialize)]
pub struct JsonRpcRequest {
    pub jsonrpc: String,
    pub id: String,
    pub method: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub params: Option<Value>,
}

/// A JSON-RPC 2.0 response received from the sidecar.
#[derive(Debug, Deserialize)]
struct JsonRpcResponse {
    id: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    result: Option<Value>,
    #[serde(skip_serializing_if = "Option::is_none")]
    error: Option<JsonRpcError>,
}

/// A JSON-RPC 2.0 error object.
#[derive(Debug, Deserialize)]
struct JsonRpcError {
    code: i64,
    message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    data: Option<Value>,
}

/// An error returned by the sidecar.
#[derive(Debug)]
pub enum SidecarError {
    Transport(String),
    MethodError { code: i64, message: String, data: Option<Value> },
    Timeout,
    NotRunning,
    InvalidResponse(String),
}

impl std::fmt::Display for SidecarError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            SidecarError::Transport(s) => write!(f, "sidecar transport error: {s}"),
            SidecarError::MethodError { code, message, data } => {
                write!(f, "sidecar returned error {code}: {message} (data: {data:?})")
            }
            SidecarError::Timeout => write!(f, "request timed out"),
            SidecarError::NotRunning => write!(f, "sidecar not running"),
            SidecarError::InvalidResponse(s) => write!(f, "invalid response: {s}"),
        }
    }
}

impl From<SidecarError> for String {
    fn from(e: SidecarError) -> Self {
        e.to_string()
    }
}

/// Shared IPC state: maps request IDs to pending responders.
///
/// All commands share this single `Arc<Mutex<>>` so that the one
/// stdout reader can dispatch responses to the correct pending request.
/// No command reads the sidecar stdout stream independently.
#[derive(Debug, Default)]
pub struct IpcState {
    pending: HashMap<String, PendingRequest>,
}

impl IpcState {
    pub fn new() -> Self {
        Self::default()
    }

    /// Register a pending request and return its correlation ID and receiver.
    pub fn register(
        &mut self,
    ) -> (
        String,
        tokio::sync::oneshot::Receiver<Result<Value, SidecarError>>,
    ) {
        let id = uuid::Uuid::new_v4().to_string();
        let (tx, rx) = tokio::sync::oneshot::channel();
        self.pending.insert(
            id.clone(),
            PendingRequest { responder: tx },
        );
        (id, rx)
    }

    /// Resolve a pending request by ID, called by the stdout reader.
    pub fn resolve(&mut self, id: &str, result: Result<Value, SidecarError>) {
        if let Some(pending) = self.pending.remove(id) {
            let _ = pending.responder.send(result);
        }
    }

    /// Resolve all pending requests with a NotRunning error.
    /// Called during application shutdown so no request is left hanging.
    pub fn resolve_all_not_running(&mut self) {
        let pending_ids: Vec<String> = self.pending.keys().cloned().collect();
        for id in pending_ids {
            self.resolve(&id, Err(SidecarError::NotRunning));
        }
    }
}

pub type AppState = Arc<Mutex<IpcState>>;

pub mod transport;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn pending_request_lifecycle() {
        let mut state = IpcState::new();
        let (id, _rx) = state.register();
        assert_eq!(state.pending.len(), 1);
        state.resolve(&id, Err(SidecarError::NotRunning));
        assert_eq!(state.pending.len(), 0);
    }
}
