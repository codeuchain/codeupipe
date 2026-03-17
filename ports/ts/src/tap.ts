/**
 * Tap: Observation Point
 *
 * A Tap is a non-modifying observation point in the pipeline.
 * It receives the payload for inspection (logging, metrics, debugging)
 * but never modifies it.
 *
 * Port of codeupipe/core/tap.py
 */

import type { Payload, PayloadData } from "./payload.js";

/**
 * Non-modifying observation point — inspect the payload without changing it.
 * The pipeline calls observe() and discards the return value.
 */
export interface Tap<T extends PayloadData = PayloadData> {
  observe(payload: Payload<T>): Promise<void> | void;
}
