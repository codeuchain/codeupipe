/**
 * State: Pipeline Execution Metadata
 *
 * Tracks what happened during pipeline execution — which filters ran,
 * which were skipped, timing data, and errors encountered.
 *
 * Port of codeupipe/core/state.py
 */

/**
 * Pipeline execution state — tracks filter execution, timing, and errors.
 */
export class State {
  executed: string[] = [];
  skipped: string[] = [];
  errors: Array<[string, Error]> = [];
  metadata: Record<string, unknown> = {};
  chunksProcessed: Record<string, number> = {};
  timings: Record<string, number> = {};

  /** Record that a filter executed. */
  markExecuted(name: string): void {
    this.executed.push(name);
  }

  /** Record that a filter was skipped. */
  markSkipped(name: string): void {
    this.skipped.push(name);
  }

  /** Increment the chunk counter for a streaming step. */
  incrementChunks(name: string, count = 1): void {
    this.chunksProcessed[name] =
      (this.chunksProcessed[name] ?? 0) + count;
  }

  /** Record step execution duration in seconds. */
  recordTiming(name: string, duration: number): void {
    this.timings[name] = duration;
  }

  /** Record an error from a filter. */
  recordError(name: string, error: Error): void {
    this.errors.push([name, error]);
  }

  /** Store arbitrary metadata. */
  set(key: string, value: unknown): void {
    this.metadata[key] = value;
  }

  /** Retrieve metadata. */
  get(key: string, defaultValue?: unknown): unknown {
    return this.metadata[key] ?? defaultValue;
  }

  /** Whether any errors were recorded. */
  get hasErrors(): boolean {
    return this.errors.length > 0;
  }

  /** The most recent error, or undefined. */
  get lastError(): Error | undefined {
    return this.errors.length > 0
      ? this.errors[this.errors.length - 1]![1]
      : undefined;
  }

  /** Reset state for a fresh run. */
  reset(): void {
    this.executed = [];
    this.skipped = [];
    this.errors = [];
    this.metadata = {};
    this.chunksProcessed = {};
    this.timings = {};
  }

  /** Compare this state with another — what changed between runs. */
  diff(other: State): Record<string, unknown> {
    const result: Record<string, unknown> = {};

    const added = other.executed.filter((s) => !this.executed.includes(s));
    const removed = this.executed.filter((s) => !other.executed.includes(s));
    if (added.length > 0) result["added_steps"] = added;
    if (removed.length > 0) result["removed_steps"] = removed;

    const timingChanges: Record<
      string,
      { old: number | undefined; new: number | undefined }
    > = {};
    const allSteps = new Set([
      ...Object.keys(this.timings),
      ...Object.keys(other.timings),
    ]);
    for (const step of [...allSteps].sort()) {
      const oldT = this.timings[step];
      const newT = other.timings[step];
      if (oldT !== newT) {
        timingChanges[step] = { old: oldT, new: newT };
      }
    }
    if (Object.keys(timingChanges).length > 0) {
      result["timing_changes"] = timingChanges;
    }

    const oldErrors = new Set(this.errors.map(([name]) => name));
    const newErrors = new Set(other.errors.map(([name]) => name));
    const errorAdded = [...newErrors].filter((n) => !oldErrors.has(n));
    const errorRemoved = [...oldErrors].filter((n) => !newErrors.has(n));
    if (errorAdded.length > 0 || errorRemoved.length > 0) {
      result["error_changes"] = {
        added: errorAdded.sort(),
        removed: errorRemoved.sort(),
      };
    }

    return result;
  }

  toString(): string {
    return (
      `State(executed=[${this.executed.join(", ")}], ` +
      `skipped=[${this.skipped.join(", ")}], ` +
      `errors=${this.errors.length}, ` +
      `timings=${Object.keys(this.timings).length}, ` +
      `chunks=${JSON.stringify(this.chunksProcessed)})`
    );
  }
}
