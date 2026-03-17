/**
 * Hook: The Enhancement Layer
 *
 * Lifecycle hooks for pipeline execution. Implementations can
 * override any combination of before(), after(), and onError().
 *
 * Port of codeupipe/core/hook.py
 */

import type { Payload, PayloadData } from "./payload.js";
import type { Filter } from "./filter.js";

/**
 * Lifecycle hook for pipeline execution.
 * All methods are optional — override what you need.
 */
export interface Hook<T extends PayloadData = PayloadData> {
  before?(
    filter: Filter | null,
    payload: Payload<T>,
  ): Promise<void> | void;

  after?(
    filter: Filter | null,
    payload: Payload<T>,
  ): Promise<void> | void;

  onError?(
    filter: Filter | null,
    error: Error,
    payload: Payload<T>,
  ): Promise<void> | void;
}
