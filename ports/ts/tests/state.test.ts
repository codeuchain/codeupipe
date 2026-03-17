import { describe, it, expect } from "vitest";
import { State } from "../src/state.js";

describe("State", () => {
  it("starts empty", () => {
    const s = new State();
    expect(s.executed).toEqual([]);
    expect(s.skipped).toEqual([]);
    expect(s.errors).toEqual([]);
    expect(s.hasErrors).toBe(false);
    expect(s.lastError).toBeUndefined();
  });

  it("markExecuted records", () => {
    const s = new State();
    s.markExecuted("step1");
    s.markExecuted("step2");
    expect(s.executed).toEqual(["step1", "step2"]);
  });

  it("markSkipped records", () => {
    const s = new State();
    s.markSkipped("gated");
    expect(s.skipped).toEqual(["gated"]);
  });

  it("recordError tracks errors", () => {
    const s = new State();
    const err = new Error("boom");
    s.recordError("step1", err);
    expect(s.hasErrors).toBe(true);
    expect(s.lastError).toBe(err);
    expect(s.errors).toHaveLength(1);
    expect(s.errors[0]![0]).toBe("step1");
    expect(s.errors[0]![1]).toBe(err);
  });

  it("multiple errors, lastError is most recent", () => {
    const s = new State();
    s.recordError("a", new Error("first"));
    s.recordError("b", new Error("second"));
    expect(s.lastError?.message).toBe("second");
    expect(s.errors).toHaveLength(2);
  });

  it("incrementChunks", () => {
    const s = new State();
    s.incrementChunks("stream1");
    s.incrementChunks("stream1");
    s.incrementChunks("stream1", 3);
    expect(s.chunksProcessed["stream1"]).toBe(5);
  });

  it("recordTiming", () => {
    const s = new State();
    s.recordTiming("step1", 0.123);
    expect(s.timings["step1"]).toBe(0.123);
  });

  it("metadata set/get", () => {
    const s = new State();
    s.set("key", "value");
    expect(s.get("key")).toBe("value");
    expect(s.get("missing")).toBeUndefined();
    expect(s.get("missing", 42)).toBe(42);
  });

  it("reset clears everything", () => {
    const s = new State();
    s.markExecuted("a");
    s.markSkipped("b");
    s.recordError("c", new Error("x"));
    s.set("k", "v");
    s.incrementChunks("s", 5);
    s.recordTiming("a", 1.0);
    s.reset();
    expect(s.executed).toEqual([]);
    expect(s.skipped).toEqual([]);
    expect(s.errors).toEqual([]);
    expect(s.metadata).toEqual({});
    expect(s.chunksProcessed).toEqual({});
    expect(s.timings).toEqual({});
  });

  it("diff detects added steps", () => {
    const s1 = new State();
    s1.markExecuted("a");

    const s2 = new State();
    s2.markExecuted("a");
    s2.markExecuted("b");

    const d = s1.diff(s2);
    expect(d["added_steps"]).toEqual(["b"]);
  });

  it("diff detects removed steps", () => {
    const s1 = new State();
    s1.markExecuted("a");
    s1.markExecuted("b");

    const s2 = new State();
    s2.markExecuted("a");

    const d = s1.diff(s2);
    expect(d["removed_steps"]).toEqual(["b"]);
  });

  it("diff detects timing changes", () => {
    const s1 = new State();
    s1.recordTiming("step1", 1.0);

    const s2 = new State();
    s2.recordTiming("step1", 2.0);

    const d = s1.diff(s2);
    expect(d["timing_changes"]).toBeDefined();
  });

  it("diff detects error changes", () => {
    const s1 = new State();

    const s2 = new State();
    s2.recordError("step1", new Error("fail"));

    const d = s1.diff(s2);
    expect(d["error_changes"]).toBeDefined();
  });

  it("diff returns empty for identical states", () => {
    const s1 = new State();
    s1.markExecuted("a");
    s1.recordTiming("a", 1.0);

    const s2 = new State();
    s2.markExecuted("a");
    s2.recordTiming("a", 1.0);

    const d = s1.diff(s2);
    expect(d).toEqual({});
  });

  it("toString contains summary", () => {
    const s = new State();
    s.markExecuted("a");
    expect(s.toString()).toContain("State");
    expect(s.toString()).toContain("a");
  });
});
