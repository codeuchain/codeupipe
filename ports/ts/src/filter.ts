/**
 * Filter: The Processing Unit
 *
 * The Filter interface defines the contract for payload processors.
 * Each Filter takes a Payload in, processes it, and returns a
 * (potentially transformed) Payload out.
 *
 * Port of codeupipe/core/filter.py
 */

import type { Payload, PayloadData } from "./payload.js";

/**
 * Processing unit — takes a payload in, returns a transformed payload out.
 * All filters are async (Promise-based).
 */
export interface Filter<
  TIn extends PayloadData = PayloadData,
  TOut extends PayloadData = PayloadData,
> {
  call(payload: Payload<TIn>): Promise<Payload<TOut>>;
}
