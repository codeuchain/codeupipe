//! Hook: The Enhancement Layer
//!
//! Lifecycle hooks for pipeline execution. Implementations can
//! override any combination of before(), after(), and on_error().
//!
//! Port of codeupipe/core/hook.py

use crate::payload::Payload;

/// Lifecycle hook for pipeline execution.
/// All methods have default no-op implementations.
pub trait Hook: Send + Sync {
    /// Called before a filter executes, or before the pipeline starts.
    fn before(&self, _filter_name: Option<&str>, _payload: &Payload) {}

    /// Called after a filter executes, or after the pipeline ends.
    fn after(&self, _filter_name: Option<&str>, _payload: &Payload) {}

    /// Called when an error occurs.
    fn on_error(&self, _filter_name: Option<&str>, _error: &str, _payload: &Payload) {}
}
