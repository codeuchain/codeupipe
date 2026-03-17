//! Filter: The Processing Unit
//!
//! The Filter trait defines the contract for payload processors.
//! Each Filter takes a Payload in, processes it, and returns a
//! (potentially transformed) Payload out.
//!
//! Port of codeupipe/core/filter.py

use crate::payload::Payload;

/// Processing unit — takes a payload in, returns a transformed payload out.
pub trait Filter: Send + Sync {
    /// Process the payload and return a transformed result.
    fn call(&self, payload: Payload) -> Result<Payload, Box<dyn std::error::Error + Send + Sync>>;

    /// Name of this filter (for state tracking).
    fn name(&self) -> &str {
        std::any::type_name::<Self>()
    }
}
