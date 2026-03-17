/**
 * StreamFilter: Chunk-at-a-Time Processing
 *
 * A StreamFilter processes one Payload chunk and yields zero or more
 * output chunks via an async generator. Enables filtering (drop),
 * mapping (1→1), and fan-out (1→N) at constant memory.
 *
 * Port of codeupipe/core/stream_filter.py
 */

import type { Payload, PayloadData } from "./payload.js";

/**
 * Streaming processing unit — receives one chunk, yields zero or more
 * output chunks.
 *
 * Use for:
 * - Filtering: yield nothing to drop a chunk
 * - Mapping: yield one transformed chunk (same as a regular Filter)
 * - Fan-out: yield multiple chunks from one input
 * - Batching/windowing: accumulate internally, yield when ready
 */
export interface StreamFilter<
  TIn extends PayloadData = PayloadData,
  TOut extends PayloadData = PayloadData,
> {
  stream(chunk: Payload<TIn>): AsyncIterable<Payload<TOut>>;
}
