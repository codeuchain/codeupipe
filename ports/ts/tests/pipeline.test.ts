import { describe, it, expect } from "vitest";
import { Payload } from "../src/payload.js";
import { Pipeline } from "../src/pipeline.js";
import type { Filter } from "../src/filter.js";
import type { StreamFilter } from "../src/stream_filter.js";
import type { Tap } from "../src/tap.js";
import type { Hook } from "../src/hook.js";
import { Valve } from "../src/valve.js";

// --- Test filters ---

class AddOne implements Filter {
  async call(payload: Payload): Promise<Payload> {
    const x = (payload.get("x") as number) ?? 0;
    return payload.insert("x", x + 1);
  }
}

class MultiplyTwo implements Filter {
  async call(payload: Payload): Promise<Payload> {
    const x = (payload.get("x") as number) ?? 0;
    return payload.insert("x", x * 2);
  }
}

class SetKey implements Filter {
  constructor(
    private key: string,
    private value: unknown,
  ) {}
  async call(payload: Payload): Promise<Payload> {
    return payload.insert(this.key, this.value);
  }
}

class FailFilter implements Filter {
  async call(_payload: Payload): Promise<Payload> {
    throw new Error("intentional failure");
  }
}

// Sync filter (no explicit async)
class SyncAddOne implements Filter {
  async call(payload: Payload): Promise<Payload> {
    const x = (payload.get("x") as number) ?? 0;
    return payload.insert("x", x + 1);
  }
}

// --- Test stream filter ---

class SplitChunks implements StreamFilter {
  async *stream(chunk: Payload): AsyncIterable<Payload> {
    const text = chunk.get("text") as string;
    for (const word of text.split(" ")) {
      yield chunk.insert("word", word);
    }
  }
}

class DropFilter implements StreamFilter {
  async *stream(_chunk: Payload): AsyncIterable<Payload> {
    // yields nothing — drops the chunk
  }
}

// --- Test tap ---

class RecordingTap implements Tap {
  observed: Payload[] = [];
  async observe(payload: Payload): Promise<void> {
    this.observed.push(payload);
  }
}

// --- Test hook ---

class RecordingHook implements Hook {
  calls: string[] = [];
  async before(filter: Filter | null, _payload: Payload): Promise<void> {
    this.calls.push(`before:${filter?.constructor.name ?? "pipeline"}`);
  }
  async after(filter: Filter | null, _payload: Payload): Promise<void> {
    this.calls.push(`after:${filter?.constructor.name ?? "pipeline"}`);
  }
  async onError(
    _filter: Filter | null,
    error: Error,
    _payload: Payload,
  ): Promise<void> {
    this.calls.push(`error:${error.message}`);
  }
}

// --- Tests ---

describe("Pipeline — batch execution", () => {
  it("runs empty pipeline", async () => {
    const pipeline = new Pipeline();
    const result = await pipeline.run(new Payload({ x: 1 }));
    expect(result.get("x")).toBe(1);
  });

  it("runs single filter", async () => {
    const pipeline = new Pipeline().addFilter(new AddOne(), "add_one");
    const result = await pipeline.run(new Payload({ x: 0 }));
    expect(result.get("x")).toBe(1);
    expect(pipeline.state.executed).toEqual(["add_one"]);
  });

  it("runs multiple filters in sequence", async () => {
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "add")
      .addFilter(new MultiplyTwo(), "multiply");
    const result = await pipeline.run(new Payload({ x: 5 }));
    // (5 + 1) * 2 = 12
    expect(result.get("x")).toBe(12);
    expect(pipeline.state.executed).toEqual(["add", "multiply"]);
  });

  it("tracks tap execution", async () => {
    const tap = new RecordingTap();
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "add")
      .addTap(tap, "recorder");
    const result = await pipeline.run(new Payload({ x: 0 }));
    expect(result.get("x")).toBe(1);
    expect(tap.observed).toHaveLength(1);
    expect(tap.observed[0]!.get("x")).toBe(1);
    expect(pipeline.state.executed).toEqual(["add", "recorder"]);
  });

  it("disables taps", async () => {
    const tap = new RecordingTap();
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "add")
      .addTap(tap, "recorder")
      .disableTaps("recorder");
    await pipeline.run(new Payload({ x: 0 }));
    expect(tap.observed).toHaveLength(0);
    expect(pipeline.state.skipped).toEqual(["recorder"]);
  });

  it("re-enables taps", async () => {
    const tap = new RecordingTap();
    const pipeline = new Pipeline()
      .addTap(tap, "recorder")
      .disableTaps("recorder")
      .enableTaps("recorder");
    await pipeline.run(new Payload({ x: 0 }));
    expect(tap.observed).toHaveLength(1);
  });

  it("valve executes when predicate true", async () => {
    const valve = new Valve("double_if_big", new MultiplyTwo(), (p) => {
      return (p.get("x") as number) > 10;
    });
    const pipeline = new Pipeline().addFilter(valve, "double_if_big");
    const result = await pipeline.run(new Payload({ x: 20 }));
    expect(result.get("x")).toBe(40);
    expect(pipeline.state.executed).toEqual(["double_if_big"]);
  });

  it("valve skips when predicate false", async () => {
    const valve = new Valve("double_if_big", new MultiplyTwo(), (p) => {
      return (p.get("x") as number) > 10;
    });
    const pipeline = new Pipeline().addFilter(valve, "double_if_big");
    const result = await pipeline.run(new Payload({ x: 5 }));
    expect(result.get("x")).toBe(5); // unchanged
    expect(pipeline.state.skipped).toEqual(["double_if_big"]);
  });

  it("hooks fire in order", async () => {
    const hook = new RecordingHook();
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "add")
      .useHook(hook);
    await pipeline.run(new Payload({ x: 0 }));
    expect(hook.calls).toEqual([
      "before:pipeline",
      "before:AddOne",
      "after:AddOne",
      "after:pipeline",
    ]);
  });

  it("hooks fire onError", async () => {
    const hook = new RecordingHook();
    const pipeline = new Pipeline()
      .addFilter(new FailFilter(), "fail")
      .useHook(hook);
    await expect(pipeline.run(new Payload({}))).rejects.toThrow(
      "intentional failure",
    );
    expect(hook.calls).toContain("error:intentional failure");
  });

  it("parallel fan-out/fan-in", async () => {
    const pipeline = new Pipeline().addParallel(
      [new SetKey("a", 1), new SetKey("b", 2)],
      "parallel_set",
    );
    const result = await pipeline.run(new Payload({}));
    expect(result.get("a")).toBe(1);
    expect(result.get("b")).toBe(2);
    expect(pipeline.state.executed).toEqual(["parallel_set"]);
  });

  it("nested pipeline", async () => {
    const inner = new Pipeline()
      .addFilter(new AddOne(), "inner_add");
    const outer = new Pipeline()
      .addFilter(new MultiplyTwo(), "outer_mul")
      .addPipeline(inner, "inner_pipeline");
    const result = await outer.run(new Payload({ x: 3 }));
    // 3 * 2 = 6, then 6 + 1 = 7
    expect(result.get("x")).toBe(7);
    expect(outer.state.executed).toEqual(["outer_mul", "inner_pipeline"]);
  });

  it("observe timing records durations", async () => {
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "add")
      .observe({ timing: true });
    await pipeline.run(new Payload({ x: 0 }));
    expect(pipeline.state.timings["add"]).toBeDefined();
    expect(pipeline.state.timings["add"]).toBeGreaterThanOrEqual(0);
  });

  it("observe lineage stamps steps", async () => {
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "step_a")
      .addFilter(new MultiplyTwo(), "step_b")
      .observe({ lineage: true });
    const result = await pipeline.run(new Payload({ x: 0 }));
    expect(result.lineage).toEqual(["step_a", "step_b"]);
  });

  it("rejects StreamFilter in batch mode", async () => {
    const pipeline = new Pipeline().addFilter(
      new SplitChunks() as unknown as Filter,
      "splitter",
    );
    await expect(pipeline.run(new Payload({ text: "a b" }))).rejects.toThrow(
      "StreamFilter",
    );
  });

  it("error propagates and state has error timing", async () => {
    const pipeline = new Pipeline()
      .addFilter(new FailFilter(), "fail")
      .observe({ timing: true });
    await expect(pipeline.run(new Payload({}))).rejects.toThrow(
      "intentional failure",
    );
    expect(pipeline.state.timings["fail"]).toBeDefined();
  });

  it("state resets between runs", async () => {
    const pipeline = new Pipeline().addFilter(new AddOne(), "add");
    await pipeline.run(new Payload({ x: 0 }));
    expect(pipeline.state.executed).toEqual(["add"]);
    await pipeline.run(new Payload({ x: 10 }));
    expect(pipeline.state.executed).toEqual(["add"]);
  });

  it("call() is alias for run() — enables nesting", async () => {
    const pipeline = new Pipeline().addFilter(new AddOne(), "add");
    const result = await pipeline.call(new Payload({ x: 5 }));
    expect(result.get("x")).toBe(6);
  });
});

describe("Pipeline — describe", () => {
  it("describes empty pipeline", () => {
    const desc = new Pipeline().describe();
    expect(desc.steps).toEqual([]);
    expect(desc.hooks).toEqual([]);
    expect(desc.step_count).toBe(0);
  });

  it("describes filters and taps", () => {
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "add")
      .addTap(new RecordingTap(), "log");
    const desc = pipeline.describe();
    expect(desc.step_count).toBe(2);
    expect(desc.steps[0]!).toMatchObject({ name: "add", type: "filter" });
    expect(desc.steps[1]!).toMatchObject({ name: "log", type: "tap" });
  });

  it("describes parallel groups", () => {
    const pipeline = new Pipeline().addParallel(
      [new SetKey("a", 1), new SetKey("b", 2)],
      "fan_out",
    );
    const desc = pipeline.describe();
    expect(desc.steps[0]!).toMatchObject({
      name: "fan_out",
      type: "parallel",
    });
  });

  it("describes nested pipelines", () => {
    const inner = new Pipeline().addFilter(new AddOne(), "inner_add");
    const outer = new Pipeline().addPipeline(inner, "nested");
    const desc = outer.describe();
    expect(desc.steps[0]!).toMatchObject({ name: "nested", type: "pipeline" });
    expect((desc.steps[0] as Record<string, unknown>)["children"]).toBeDefined();
  });

  it("describes hooks", () => {
    const pipeline = new Pipeline().useHook(new RecordingHook());
    const desc = pipeline.describe();
    expect(desc.hooks).toEqual(["RecordingHook"]);
  });
});

describe("Pipeline — streaming", () => {
  async function collect(gen: AsyncIterable<Payload>): Promise<Payload[]> {
    const results: Payload[] = [];
    for await (const chunk of gen) {
      results.push(chunk);
    }
    return results;
  }

  async function* toAsyncIter(
    payloads: Payload[],
  ): AsyncGenerator<Payload> {
    for (const p of payloads) {
      yield p;
    }
  }

  it("streams through regular filter", async () => {
    const pipeline = new Pipeline().addFilter(new AddOne(), "add");
    const source = toAsyncIter([
      new Payload({ x: 1 }),
      new Payload({ x: 2 }),
      new Payload({ x: 3 }),
    ]);
    const results = await collect(pipeline.stream(source));
    expect(results.map((r) => r.get("x"))).toEqual([2, 3, 4]);
    expect(pipeline.state.chunksProcessed["add"]).toBe(3);
  });

  it("streams through StreamFilter (fan-out)", async () => {
    const pipeline = new Pipeline().addFilter(
      new SplitChunks() as unknown as Filter,
      "split",
    );
    const source = toAsyncIter([new Payload({ text: "hello world" })]);
    const results = await collect(pipeline.stream(source));
    expect(results.map((r) => r.get("word"))).toEqual(["hello", "world"]);
  });

  it("streams through drop filter", async () => {
    const pipeline = new Pipeline().addFilter(
      new DropFilter() as unknown as Filter,
      "drop",
    );
    const source = toAsyncIter([
      new Payload({ x: 1 }),
      new Payload({ x: 2 }),
    ]);
    const results = await collect(pipeline.stream(source));
    expect(results).toEqual([]);
  });

  it("streaming taps observe each chunk", async () => {
    const tap = new RecordingTap();
    const pipeline = new Pipeline().addTap(tap, "log");
    const source = toAsyncIter([
      new Payload({ x: 1 }),
      new Payload({ x: 2 }),
    ]);
    const results = await collect(pipeline.stream(source));
    expect(results).toHaveLength(2);
    expect(tap.observed).toHaveLength(2);
    expect(pipeline.state.chunksProcessed["log"]).toBe(2);
  });

  it("streaming disabled tap skips", async () => {
    const tap = new RecordingTap();
    const pipeline = new Pipeline()
      .addTap(tap, "log")
      .disableTaps("log");
    const source = toAsyncIter([new Payload({ x: 1 })]);
    const results = await collect(pipeline.stream(source));
    expect(results).toHaveLength(1);
    expect(tap.observed).toHaveLength(0);
    expect(pipeline.state.skipped).toEqual(["log"]);
  });

  it("streaming hooks fire", async () => {
    const hook = new RecordingHook();
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "add")
      .useHook(hook);
    const source = toAsyncIter([new Payload({ x: 0 })]);
    await collect(pipeline.stream(source));
    expect(hook.calls).toContain("before:pipeline");
    expect(hook.calls).toContain("after:pipeline");
  });

  it("streaming error fires hook", async () => {
    const hook = new RecordingHook();
    const pipeline = new Pipeline()
      .addFilter(new FailFilter(), "fail")
      .useHook(hook);
    const source = toAsyncIter([new Payload({})]);
    await expect(collect(pipeline.stream(source))).rejects.toThrow(
      "intentional failure",
    );
    expect(hook.calls).toContain("error:intentional failure");
  });

  it("streaming parallel applies to each chunk", async () => {
    const pipeline = new Pipeline().addParallel(
      [new SetKey("a", 1), new SetKey("b", 2)],
      "par",
    );
    const source = toAsyncIter([new Payload({}), new Payload({})]);
    const results = await collect(pipeline.stream(source));
    expect(results).toHaveLength(2);
    for (const r of results) {
      expect(r.get("a")).toBe(1);
      expect(r.get("b")).toBe(2);
    }
  });

  it("streaming nested pipeline", async () => {
    const inner = new Pipeline().addFilter(new AddOne(), "inner_add");
    const outer = new Pipeline().addPipeline(inner, "nested");
    const source = toAsyncIter([
      new Payload({ x: 10 }),
      new Payload({ x: 20 }),
    ]);
    const results = await collect(outer.stream(source));
    expect(results.map((r) => r.get("x"))).toEqual([11, 21]);
  });
});

describe("Pipeline — addFilter returns this (fluent)", () => {
  it("chaining works", () => {
    const pipeline = new Pipeline()
      .addFilter(new AddOne(), "a")
      .addFilter(new MultiplyTwo(), "b")
      .addTap(new RecordingTap(), "t")
      .useHook(new RecordingHook())
      .observe({ timing: true });
    expect(pipeline).toBeInstanceOf(Pipeline);
  });
});
