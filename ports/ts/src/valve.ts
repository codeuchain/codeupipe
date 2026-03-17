/**
 * Valve: Conditional Flow Control
 *
 * A Valve wraps a Filter with a predicate — the inner filter only
 * executes when the predicate evaluates to true. Otherwise the payload
 * passes through unchanged.
 *
 * Port of codeupipe/core/valve.py
 */

import type { Payload, PayloadData } from "./payload.js";
import type { Filter } from "./filter.js";

/**
 * Conditional flow control — gates a Filter with a predicate.
 *
 * Conforms to the Filter interface so it can be used anywhere a
 * Filter is expected.
 */
export class Valve<
  TIn extends PayloadData = PayloadData,
  TOut extends PayloadData = PayloadData,
> implements Filter<TIn, TOut>
{
  readonly name: string;
  private readonly _inner: Filter<TIn, TOut>;
  private readonly _predicate: (payload: Payload<TIn>) => boolean;
  /** Whether the last call was skipped. Used by Pipeline for state tracking. */
  _lastSkipped = false;

  constructor(
    name: string,
    inner: Filter<TIn, TOut>,
    predicate: (payload: Payload<TIn>) => boolean,
  ) {
    this.name = name;
    this._inner = inner;
    this._predicate = predicate;
  }

  async call(payload: Payload<TIn>): Promise<Payload<TOut>> {
    if (this._predicate(payload)) {
      this._lastSkipped = false;
      return this._inner.call(payload);
    }
    this._lastSkipped = true;
    return payload as unknown as Payload<TOut>;
  }

  toString(): string {
    return `Valve(${JSON.stringify(this.name)})`;
  }
}
