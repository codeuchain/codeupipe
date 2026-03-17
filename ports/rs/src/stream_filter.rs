//! StreamFilter: Chunk-at-a-Time Processing
//!
//! A StreamFilter processes one Payload chunk and yields zero or more
//! output chunks. Enables filtering (drop), mapping (1→1), and
//! fan-out (1→N) at constant memory.
//!
//! Port of codeupipe/core/stream_filter.py

use crate::payload::Payload;

/// Streaming processing unit — receives one chunk, returns zero or more
/// output chunks.
pub trait StreamFilter: Send + Sync {
    /// Process a single chunk and return output chunks.
    fn stream(&self, chunk: Payload) -> Result<Vec<Payload>, Box<dyn std::error::Error + Send + Sync>>;

    /// Name of this stream filter (for state tracking).
    fn name(&self) -> &str {
        std::any::type_name::<Self>()
    }
}
