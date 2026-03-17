/**
 * Pipeline: The Orchestrator
 *
 * Runs filters in sequence with hooks, taps, and state tracking.
 * Supports batch (.run) and streaming (.stream) execution modes.
 *
 * This is a focused port of codeupipe/core/pipeline.py — the core
 * orchestration loop without the Govern layer (schemas, contracts,
 * audit, dead-letter) which stays in Python.
 *
 * Ported features:
 *   - Sequential filter execution with hooks
 *   - Tap observation
 *   - Valve skip detection
 *   - Parallel fan-out/fan-in
 *   - Nested pipelines
 *   - Timing & lineage observation
 *   - Streaming via async generators
 *   - State tracking (executed, skipped, errors, timings, chunks)
 *   - run_sync convenience
 *   - describe() introspection
 */

import { Payload, type PayloadData } from "./payload.js";
import type { Filter } from "./filter.js";
import type { StreamFilter } from "./stream_filter.js";
import type { Tap } from "./tap.js";
import type { Hook } from "./hook.js";
import { State } from "./state.js";

// ---------------------------------------------------------------------------
// Internal types
// ---------------------------------------------------------------------------

type StepType = "filter" | "tap" | "parallel" | "pipeline";

type ParallelGroup = { filters: Filter[]; names: (string | null)[] };

type Step = {
  name: string;
  step: Filter | Tap | ParallelGroup | Pipeline;
  type: StepType;
};

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isStreamFilter(step: unknown): step is StreamFilter {
  return (
    typeof step === "object" &&
    step !== null &&
    "stream" in step &&
    typeof (step as StreamFilter).stream === "function"
  );
}

function isParallelGroup(step: unknown): step is ParallelGroup {
  return (
    typeof step === "object" &&
    step !== null &&
    "filters" in step &&
    Array.isArray((step as ParallelGroup).filters)
  );
}

function isPipeline(step: unknown): step is Pipeline {
  return step instanceof Pipeline;
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
async function invoke(fn: (...args: any[]) => any, ...args: any[]): Promise<void> {
  const result = fn(...args);
  if (result instanceof Promise) {
    await result;
  }
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

/**
 * Orchestrator — runs filters in sequence with hooks, taps, and state
 * tracking.
 *
 * Build a pipeline by adding filters, taps, and hooks. Run it with
 * `.run(payload)`. After execution, inspect `.state` for metadata.
 */
export class Pipeline<
  TIn extends PayloadData = PayloadData,
  TOut extends PayloadData = PayloadData,
> {
  private _steps: Step[] = [];
  private _hooks: Hook[] = [];
  private _state: State = new State();
  private _observeTiming = false;
  private _observeLineage = false;
  private _disabledTaps: Set<string> = new Set();

  // -----------------------------------------------------------------------
  // Builder API
  // -----------------------------------------------------------------------

  /** Access pipeline execution state after run(). */
  get state(): State {
    return this._state;
  }

  /** Add a filter to the pipeline. */
  addFilter(filter: Filter, name?: string): this {
    const filterName = name ?? filter.constructor.name;
    this._steps.push({ name: filterName, step: filter, type: "filter" });
    return this;
  }

  /** Add a tap (observation point) to the pipeline. */
  addTap(tap: Tap, name?: string): this {
    const tapName = name ?? tap.constructor.name;
    this._steps.push({ name: tapName, step: tap, type: "tap" });
    return this;
  }

  /** Attach a lifecycle hook. */
  useHook(hook: Hook): this {
    this._hooks.push(hook);
    return this;
  }

  /** Add a parallel fan-out/fan-in group of filters. */
  addParallel(
    filters: Filter[],
    name: string,
    options?: { names?: string[] },
  ): this {
    const names = options?.names ?? filters.map(() => null);
    this._steps.push({
      name,
      step: { filters, names },
      type: "parallel",
    });
    return this;
  }

  /** Nest a Pipeline as a single step inside this Pipeline. */
  addPipeline(pipeline: Pipeline, name: string): this {
    this._steps.push({ name, step: pipeline, type: "pipeline" });
    return this;
  }

  /** Enable observation features (timing, lineage tracking). */
  observe(options?: { timing?: boolean; lineage?: boolean }): this {
    this._observeTiming = options?.timing ?? true;
    this._observeLineage = options?.lineage ?? false;
    return this;
  }

  /** Disable specific taps by name at runtime. */
  disableTaps(...names: string[]): this {
    for (const n of names) this._disabledTaps.add(n);
    return this;
  }

  /** Re-enable previously disabled taps. */
  enableTaps(...names: string[]): this {
    for (const n of names) this._disabledTaps.delete(n);
    return this;
  }

  // -----------------------------------------------------------------------
  // Filter protocol — allows nesting
  // -----------------------------------------------------------------------

  async call(payload: Payload<TIn>): Promise<Payload<TOut>> {
    return this.run(payload);
  }

  // -----------------------------------------------------------------------
  // Batch execution
  // -----------------------------------------------------------------------

  async run(initialPayload: Payload<TIn>): Promise<Payload<TOut>> {
    // Reject StreamFilters in batch mode
    for (const { name, step, type } of this._steps) {
      if (type === "filter" && isStreamFilter(step)) {
        throw new Error(
          `Pipeline contains StreamFilter '${name}'. ` +
            `Use pipeline.stream() with an async iterable instead.`,
        );
      }
    }

    this._state = new State();
    let payload: Payload = initialPayload;

    // Hook: pipeline start
    for (const hook of this._hooks) {
      if (hook.before) await invoke(hook.before.bind(hook), null, payload);
    }

    let stepName: string | undefined;
    let stepT0: number | undefined;

    try {
      for (const { name, step, type } of this._steps) {
        stepName = name;
        stepT0 = undefined;

        // --- Tap ---
        if (type === "tap") {
          if (this._disabledTaps.has(name)) {
            this._state.markSkipped(name);
            continue;
          }
          await invoke((step as Tap).observe.bind(step), payload);
          this._state.markExecuted(name);
          continue;
        }

        stepT0 = performance.now();

        // --- Parallel ---
        if (type === "parallel" && isParallelGroup(step)) {
          const results = await Promise.all(
            step.filters.map((f) => f.call(payload)),
          );
          for (const result of results) {
            payload = payload.merge(result);
          }
          this._state.markExecuted(name);
        }
        // --- Nested Pipeline ---
        else if (type === "pipeline" && isPipeline(step)) {
          for (const hook of this._hooks) {
            if (hook.before) await invoke(hook.before.bind(hook), step as unknown as Filter, payload);
          }
          payload = await step.run(payload);
          this._state.markExecuted(name);
          for (const hook of this._hooks) {
            if (hook.after) await invoke(hook.after.bind(hook), step as unknown as Filter, payload);
          }
        }
        // --- Filter / Valve ---
        else {
          for (const hook of this._hooks) {
            if (hook.before) await invoke(hook.before.bind(hook), step as Filter, payload);
          }

          payload = await (step as Filter).call(payload);

          // Valve skip detection
          if (
            "_lastSkipped" in (step as unknown as Record<string, unknown>) &&
            (step as unknown as { _lastSkipped: boolean })._lastSkipped
          ) {
            this._state.markSkipped(name);
          } else {
            this._state.markExecuted(name);
          }

          for (const hook of this._hooks) {
            if (hook.after) await invoke(hook.after.bind(hook), step as Filter, payload);
          }
        }

        // Post-step instrumentation
        const duration = (performance.now() - stepT0) / 1000;
        if (this._observeTiming) {
          this._state.recordTiming(name, duration);
        }
        if (this._observeLineage) {
          payload = payload._stamp(name);
        }
      }
    } catch (e) {
      if (stepT0 !== undefined && stepName !== undefined) {
        const duration = (performance.now() - stepT0) / 1000;
        if (this._observeTiming) {
          this._state.recordTiming(stepName, duration);
        }
      }
      const error = e instanceof Error ? e : new Error(String(e));
      for (const hook of this._hooks) {
        if (hook.onError) await invoke(hook.onError.bind(hook), null, error, payload);
      }
      throw e;
    }

    // Hook: pipeline end
    for (const hook of this._hooks) {
      if (hook.after) await invoke(hook.after.bind(hook), null, payload);
    }

    return payload as unknown as Payload<TOut>;
  }

  // -----------------------------------------------------------------------
  // Introspection
  // -----------------------------------------------------------------------

  /** Return a machine-readable tree of the pipeline structure. */
  describe(): {
    steps: Record<string, unknown>[];
    hooks: string[];
    step_count: number;
  } {
    const steps: Record<string, unknown>[] = [];

    for (const { name, step, type } of this._steps) {
      if (type === "parallel" && isParallelGroup(step)) {
        steps.push({
          name,
          type: "parallel",
          filters: step.filters.map((f, i) => ({
            name: step.names[i] ?? f.constructor.name,
            type: "filter",
          })),
        });
      } else if (type === "pipeline" && isPipeline(step)) {
        steps.push({
          name,
          type: "pipeline",
          children: step.describe().steps,
        });
      } else {
        steps.push({
          name,
          type,
          class: (step as object).constructor.name,
        });
      }
    }

    return {
      steps,
      hooks: this._hooks.map((h) => h.constructor.name),
      step_count: steps.length,
    };
  }

  // -----------------------------------------------------------------------
  // Streaming
  // -----------------------------------------------------------------------

  /** Stream payloads through the pipeline, one chunk at a time. */
  async *stream(
    source: AsyncIterable<Payload<TIn>>,
  ): AsyncGenerator<Payload<TOut>> {
    this._state = new State();

    const sentinel = new Payload();
    for (const hook of this._hooks) {
      if (hook.before) await invoke(hook.before.bind(hook), null, sentinel);
    }

    try {
      let current: AsyncIterable<Payload> = source;

      for (const { name, step, type } of this._steps) {
        current = this._wrapStep(current, name, step, type);
      }

      for await (const result of current) {
        yield result as Payload<TOut>;
      }
    } catch (e) {
      const error = e instanceof Error ? e : new Error(String(e));
      for (const hook of this._hooks) {
        if (hook.onError) await invoke(hook.onError.bind(hook), null, error, sentinel);
      }
      throw e;
    }

    for (const hook of this._hooks) {
      if (hook.after) await invoke(hook.after.bind(hook), null, sentinel);
    }
  }

  private async *_wrapStep(
    upstream: AsyncIterable<Payload>,
    name: string,
    step: Filter | Tap | ParallelGroup | Pipeline,
    stepType: StepType,
  ): AsyncGenerator<Payload> {
    // --- Tap ---
    if (stepType === "tap") {
      if (this._disabledTaps.has(name)) {
        this._state.markSkipped(name);
        for await (const chunk of upstream) {
          yield chunk;
        }
        return;
      }
      if (!this._state.executed.includes(name)) {
        this._state.markExecuted(name);
      }
      for await (const chunk of upstream) {
        await invoke((step as Tap).observe.bind(step), chunk);
        this._state.incrementChunks(name);
        yield chunk;
      }
      return;
    }

    // --- StreamFilter ---
    if (stepType === "filter" && isStreamFilter(step)) {
      if (!this._state.executed.includes(name)) {
        this._state.markExecuted(name);
      }
      for await (const chunk of upstream) {
        for await (const out of step.stream(chunk)) {
          this._state.incrementChunks(name);
          yield out;
        }
      }
      return;
    }

    // --- Regular Filter ---
    if (stepType === "filter") {
      if (!this._state.executed.includes(name)) {
        this._state.markExecuted(name);
      }
      for await (const chunk of upstream) {
        const result = await (step as Filter).call(chunk);
        this._state.incrementChunks(name);
        yield result;
      }
      return;
    }

    // --- Parallel ---
    if (stepType === "parallel" && isParallelGroup(step)) {
      if (!this._state.executed.includes(name)) {
        this._state.markExecuted(name);
      }
      for await (const chunk of upstream) {
        const results = await Promise.all(
          step.filters.map((f) => f.call(chunk)),
        );
        let merged = chunk;
        for (const r of results) {
          merged = merged.merge(r);
        }
        this._state.incrementChunks(name);
        yield merged;
      }
      return;
    }

    // --- Nested Pipeline ---
    if (stepType === "pipeline" && isPipeline(step)) {
      if (!this._state.executed.includes(name)) {
        this._state.markExecuted(name);
      }
      for await (const chunk of upstream) {
        const result = await step.run(chunk);
        this._state.incrementChunks(name);
        yield result;
      }
      return;
    }
  }
}
