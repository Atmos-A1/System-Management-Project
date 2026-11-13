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

    /// Cancel a pending request by ID without sending a response.
    /// Used when the request fails before a response can be received
    /// (e.g., serialization error, write error, or caller timeout).
    pub fn cancel(&mut self, id: &str) {
        self.pending.remove(id);
    }
}

pub type AppState = Arc<Mutex<IpcState>>;

/// Sidecar reference: always managed, `Some` when running, `None` when not available.
/// This allows the app to start even if the sidecar fails to spawn, and commands
/// return an honest "not running" error instead of silently failing.
///
/// A `std::sync::Mutex` is deliberate: this ref is set once during Tauri's
/// `setup` hook and read by async commands. `setup` is a synchronous closure,
/// so it cannot `.await`, and `blocking_lock()` would panic if `setup` ever ran
/// inside a runtime context. The critical section is a single move of a
/// short-lived handle, so no `.await` is ever held while the lock is held.
pub type SidecarRef =
    Arc<std::sync::Mutex<Option<crate::ipc::transport::SidecarHandle>>>;

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

    #[test]
    fn cancel_removes_pending_entry() {
        let mut state = IpcState::new();
        let (id, mut rx) = state.register();
        assert_eq!(state.pending.len(), 1);
        state.cancel(&id);
        assert_eq!(state.pending.len(), 0);
        // Receiver should be closed since sender was dropped
        assert!(rx.try_recv().is_err());
    }

    #[test]
    fn cancel_unknown_id_is_noop() {
        let mut state = IpcState::new();
        let (id, _rx) = state.register();
        assert_eq!(state.pending.len(), 1);
        state.cancel("unknown-id");
        assert_eq!(state.pending.len(), 1);
        state.cancel(&id);
        assert_eq!(state.pending.len(), 0);
    }

    #[test]
    fn resolve_all_not_running_fails_all_pending() {
        let mut state = IpcState::new();
        let (_id1, mut rx1) = state.register();
        let (_id2, mut rx2) = state.register();
        assert_eq!(state.pending.len(), 2);
        state.resolve_all_not_running();
        assert_eq!(state.pending.len(), 0);
        let r1 = rx1.try_recv().expect("channel closed");
        let r2 = rx2.try_recv().expect("channel closed");
        assert!(matches!(r1, Err(SidecarError::NotRunning)));
        assert!(matches!(r2, Err(SidecarError::NotRunning)));
    }

    #[test]
    fn resolve_after_cancel_is_noop() {
        let mut state = IpcState::new();
        let (id, _rx) = state.register();
        state.cancel(&id);
        // Resolve should not panic and should not send (no receiver)
        state.resolve(&id, Ok(serde_json::Value::Null));
        assert_eq!(state.pending.len(), 0);
    }

    #[test]
    fn resolve_unknown_id_is_noop() {
        let mut state = IpcState::new();
        state.resolve("unknown", Ok(serde_json::Value::Null));
        assert_eq!(state.pending.len(), 0);
    }

    #[test]
    fn resolve_all_not_running_idempotent() {
        let mut state = IpcState::new();
        let (_id, mut rx) = state.register();
        state.resolve_all_not_running();
        state.resolve_all_not_running(); // Second call should not panic
        assert_eq!(state.pending.len(), 0);
        let r = rx.try_recv().expect("channel closed");
        assert!(matches!(r, Err(SidecarError::NotRunning)));
    }
}
