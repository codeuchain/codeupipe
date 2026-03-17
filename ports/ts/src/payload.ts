/**
 * Payload: The Data Container
 *
 * Immutable data container flowing through pipelines.
 * Returns fresh copies on modification for safety.
 *
 * Port of codeupipe/core/payload.py
 */

export type PayloadData = Record<string, unknown>;

/**
 * Immutable data container — holds data flowing through the pipeline.
 * Returns fresh copies on modification for safety.
 */
export class Payload<T extends PayloadData = PayloadData> {
  private readonly _data: Readonly<T>;
  private readonly _traceId: string | undefined;
  private readonly _lineage: readonly string[];

  constructor(
    data?: T | null,
    options?: { traceId?: string; lineage?: string[] },
  ) {
    this._data = data ? ({ ...data } as T) : ({} as T);
    this._traceId = options?.traceId;
    this._lineage = options?.lineage ? [...options.lineage] : [];
  }

  /** Return the value for key, or default if absent. */
  get<K extends string>(key: K, defaultValue?: unknown): unknown {
    const val = (this._data as PayloadData)[key];
    return val !== undefined ? val : defaultValue;
  }

  /** Trace ID for distributed tracing / lineage tracking. */
  get traceId(): string | undefined {
    return this._traceId;
  }

  /** Ordered list of step names this payload has passed through. */
  get lineage(): string[] {
    return [...this._lineage];
  }

  /** Return a new Payload with trace ID set. */
  withTrace(traceId: string): Payload<T> {
    return new Payload<T>({ ...this._data }, {
      traceId,
      lineage: [...this._lineage],
    });
  }

  /** Record a processing step in lineage (internal). */
  _stamp(stepName: string): Payload<T> {
    return new Payload<T>({ ...this._data }, {
      traceId: this._traceId,
      lineage: [...this._lineage, stepName],
    });
  }

  /** Return a fresh Payload with the addition. */
  insert<K extends string, V>(
    key: K,
    value: V,
  ): Payload<T & Record<K, V>> {
    const newData = { ...this._data, [key]: value } as T & Record<K, V>;
    return new Payload<T & Record<K, V>>(newData, {
      traceId: this._traceId,
      lineage: [...this._lineage],
    });
  }

  /** Insert with type evolution — alias for insert. */
  insertAs<K extends string, V>(
    key: K,
    value: V,
  ): Payload<T & Record<K, V>> {
    return this.insert(key, value);
  }

  /** Convert to a mutable sibling for performance-critical sections. */
  withMutation(): MutablePayload<T> {
    return new MutablePayload<T>({ ...this._data }, {
      traceId: this._traceId,
      lineage: [...this._lineage],
    });
  }

  /** Combine payloads, with other taking precedence on conflicts. */
  merge<U extends PayloadData>(other: Payload<U>): Payload<T & U> {
    const newData = { ...this._data, ...other.toDict() } as T & U;
    const trace = this._traceId ?? other.traceId;
    const lineage = [...this._lineage, ...other.lineage];
    return new Payload<T & U>(newData, { traceId: trace, lineage });
  }

  /** Express as dict for ecosystem integration. */
  toDict(): T {
    return { ...this._data } as T;
  }

  /** Serialize payload for network/storage transport. */
  serialize(fmt: "json" = "json"): Uint8Array {
    if (fmt === "json") {
      const envelope: PayloadData = { data: this._data };
      if (this._traceId) envelope["trace_id"] = this._traceId;
      if (this._lineage.length > 0) envelope["lineage"] = [...this._lineage];
      return new TextEncoder().encode(JSON.stringify(envelope));
    }
    throw new Error(`Unsupported format: ${fmt}`);
  }

  /** Deserialize payload from network/storage transport. */
  static deserialize<T extends PayloadData = PayloadData>(
    raw: Uint8Array,
    fmt: "json" = "json",
  ): Payload<T> {
    if (fmt === "json") {
      const text = new TextDecoder().decode(raw);
      const envelope = JSON.parse(text) as {
        data?: T;
        trace_id?: string;
        lineage?: string[];
      };
      return new Payload<T>(envelope.data ?? ({} as T), {
        traceId: envelope.trace_id,
        lineage: envelope.lineage,
      });
    }
    throw new Error(`Unsupported format: ${fmt}`);
  }

  toString(): string {
    if (this._traceId) {
      return `Payload(${JSON.stringify(this._data)}, traceId='${this._traceId}')`;
    }
    return `Payload(${JSON.stringify(this._data)})`;
  }
}

/**
 * Mutable data container for performance-critical sections.
 */
export class MutablePayload<T extends PayloadData = PayloadData> {
  private readonly _data: T;
  private readonly _traceId: string | undefined;
  private readonly _lineage: string[];

  constructor(
    data?: T | null,
    options?: { traceId?: string; lineage?: string[] },
  ) {
    this._data = data ? ({ ...data } as T) : ({} as T);
    this._traceId = options?.traceId;
    this._lineage = options?.lineage ? [...options.lineage] : [];
  }

  /** Return the value for key, or default if absent. */
  get<K extends string>(key: K, defaultValue?: unknown): unknown {
    const val = (this._data as PayloadData)[key];
    return val !== undefined ? val : defaultValue;
  }

  /** Change in place. */
  set(key: string, value: unknown): void {
    (this._data as PayloadData)[key] = value;
  }

  /** Trace ID for distributed tracing / lineage tracking. */
  get traceId(): string | undefined {
    return this._traceId;
  }

  /** Ordered list of step names this payload has passed through. */
  get lineage(): string[] {
    return [...this._lineage];
  }

  /** Return to safety with a fresh immutable copy. */
  toImmutable(): Payload<T> {
    return new Payload<T>({ ...this._data }, {
      traceId: this._traceId,
      lineage: [...this._lineage],
    });
  }

  toString(): string {
    return `MutablePayload(${JSON.stringify(this._data)})`;
  }
}
