//! Tap: Observation Point
//!
//! A Tap is a non-modifying observation point in the pipeline.
//! It receives the payload for inspection but never modifies it.
//!
//! Port of codeupipe/core/tap.py

use crate::payload::Payload;

/// Non-modifying observation point — inspect the payload without changing it.
pub trait Tap: Send + Sync {
    /// Observe the payload. Must not modify it.
    fn observe(&self, payload: &Payload);

    /// Name of this tap (for state tracking).
    fn name(&self) -> &str {
        std::any::type_name::<Self>()
    }
}
