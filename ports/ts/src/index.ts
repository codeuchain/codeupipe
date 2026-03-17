/**
 * codeupipe-ts — TypeScript core library
 *
 * Port of the 8 core primitives from codeupipe (Python).
 * Zero dependencies. Same mental model, same API shape.
 *
 * Python is for prototypes + backend pipelines.
 * TypeScript is for web + browser pipelines.
 * Rust is for WASM + desktop.
 * Go is for cloud infrastructure.
 */

export { Payload, MutablePayload, type PayloadData } from "./payload.js";
export { type Filter } from "./filter.js";
export { type StreamFilter } from "./stream_filter.js";
export { type Tap } from "./tap.js";
export { type Hook } from "./hook.js";
export { State } from "./state.js";
export { Valve } from "./valve.js";
export { Pipeline } from "./pipeline.js";
