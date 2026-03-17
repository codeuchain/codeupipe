//! codeupipe-core — Rust port
//!
//! Core pipeline primitives: Payload, Filter, StreamFilter, Pipeline,
//! Valve, Tap, State, Hook.
//!
//! Zero external dependencies. WASM-compatible.
//!
//! Python is for prototypes + backend.
//! TypeScript is for web + browser.
//! Rust is for WASM + desktop.
//! Go is for cloud infrastructure.

mod payload;
mod state;
mod filter;
mod stream_filter;
mod tap;
mod hook;
mod valve;
mod pipeline;

pub use payload::{Payload, MutablePayload};
pub use state::State;
pub use filter::Filter;
pub use stream_filter::StreamFilter;
pub use tap::Tap;
pub use hook::Hook;
pub use valve::Valve;
pub use pipeline::Pipeline;
