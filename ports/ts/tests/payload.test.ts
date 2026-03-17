import { describe, it, expect } from "vitest";
import { Payload, MutablePayload } from "../src/payload.js";

describe("Payload", () => {
  it("creates empty payload", () => {
    const p = new Payload();
    expect(p.toDict()).toEqual({});
    expect(p.traceId).toBeUndefined();
    expect(p.lineage).toEqual([]);
  });

  it("creates payload from data", () => {
    const p = new Payload({ x: 1, y: "hello" });
    expect(p.get("x")).toBe(1);
    expect(p.get("y")).toBe("hello");
  });

  it("returns default for missing key", () => {
    const p = new Payload({ x: 1 });
    expect(p.get("missing")).toBeUndefined();
    expect(p.get("missing", 42)).toBe(42);
  });

  it("insert returns new payload", () => {
    const p1 = new Payload({ a: 1 });
    const p2 = p1.insert("b", 2);
    expect(p1.get("b")).toBeUndefined();
    expect(p2.get("a")).toBe(1);
    expect(p2.get("b")).toBe(2);
  });

  it("insertAs is alias for insert", () => {
    const p1 = new Payload({ a: 1 });
    const p2 = p1.insertAs("b", 2);
    expect(p2.get("b")).toBe(2);
    expect(p2.get("a")).toBe(1);
  });

  it("insert does not mutate original", () => {
    const p1 = new Payload({ x: 1 });
    p1.insert("y", 2);
    expect(p1.get("y")).toBeUndefined();
  });

  it("merge combines payloads", () => {
    const p1 = new Payload({ a: 1 });
    const p2 = new Payload({ b: 2 });
    const merged = p1.merge(p2);
    expect(merged.get("a")).toBe(1);
    expect(merged.get("b")).toBe(2);
  });

  it("merge gives precedence to other", () => {
    const p1 = new Payload({ x: "old" });
    const p2 = new Payload({ x: "new" });
    const merged = p1.merge(p2);
    expect(merged.get("x")).toBe("new");
  });

  it("merge combines lineage", () => {
    const p1 = new Payload({ a: 1 })._stamp("step1");
    const p2 = new Payload({ b: 2 })._stamp("step2");
    const merged = p1.merge(p2);
    expect(merged.lineage).toEqual(["step1", "step2"]);
  });

  it("merge preserves first trace_id", () => {
    const p1 = new Payload({}, { traceId: "trace-1" });
    const p2 = new Payload({}, { traceId: "trace-2" });
    expect(p1.merge(p2).traceId).toBe("trace-1");
  });

  it("merge uses other trace_id if first is undefined", () => {
    const p1 = new Payload({});
    const p2 = new Payload({}, { traceId: "trace-2" });
    expect(p1.merge(p2).traceId).toBe("trace-2");
  });

  it("toDict returns a copy", () => {
    const p = new Payload({ a: 1 });
    const d = p.toDict();
    d["a"] = 999;
    expect(p.get("a")).toBe(1);
  });

  it("trace_id preserved through insert", () => {
    const p = new Payload({ x: 1 }, { traceId: "abc" });
    const p2 = p.insert("y", 2);
    expect(p2.traceId).toBe("abc");
  });

  it("withTrace sets trace ID", () => {
    const p = new Payload({ x: 1 });
    const p2 = p.withTrace("trace-123");
    expect(p.traceId).toBeUndefined();
    expect(p2.traceId).toBe("trace-123");
    expect(p2.get("x")).toBe(1);
  });

  it("_stamp appends to lineage", () => {
    const p = new Payload({})._stamp("step1")._stamp("step2");
    expect(p.lineage).toEqual(["step1", "step2"]);
  });

  it("lineage is not shared between payloads", () => {
    const p1 = new Payload({})._stamp("a");
    const p2 = p1._stamp("b");
    expect(p1.lineage).toEqual(["a"]);
    expect(p2.lineage).toEqual(["a", "b"]);
  });

  it("withMutation converts to MutablePayload", () => {
    const p = new Payload({ x: 1 }, { traceId: "t1" });
    const mp = p.withMutation();
    expect(mp.get("x")).toBe(1);
    expect(mp.traceId).toBe("t1");
    mp.set("x", 99);
    expect(p.get("x")).toBe(1); // original unchanged
    expect(mp.get("x")).toBe(99);
  });

  it("toString includes data", () => {
    const p = new Payload({ a: 1 });
    expect(p.toString()).toContain("Payload");
    expect(p.toString()).toContain('"a":1');
  });

  it("toString includes traceId when set", () => {
    const p = new Payload({}, { traceId: "abc" });
    expect(p.toString()).toContain("abc");
  });

  it("constructor handles null data", () => {
    const p = new Payload(null);
    expect(p.toDict()).toEqual({});
  });

  it("constructor does not share reference", () => {
    const data = { a: 1 };
    const p = new Payload(data);
    data.a = 999;
    expect(p.get("a")).toBe(1);
  });

  // --- Serialize / Deserialize ---

  it("serialize to JSON", () => {
    const p = new Payload({ x: 42 }, { traceId: "t1" });
    const bytes = p.serialize("json");
    expect(bytes).toBeInstanceOf(Uint8Array);
    const text = new TextDecoder().decode(bytes);
    const obj = JSON.parse(text);
    expect(obj.data.x).toBe(42);
    expect(obj.trace_id).toBe("t1");
  });

  it("deserialize from JSON", () => {
    const original = new Payload(
      { name: "test" },
      { traceId: "t", lineage: ["s1"] },
    );
    const bytes = original.serialize("json");
    const restored = Payload.deserialize(bytes, "json");
    expect(restored.get("name")).toBe("test");
    expect(restored.traceId).toBe("t");
    expect(restored.lineage).toEqual(["s1"]);
  });

  it("roundtrip preserves data", () => {
    const original = new Payload({ a: 1, b: [2, 3], c: { d: true } });
    const restored = Payload.deserialize(original.serialize());
    expect(restored.toDict()).toEqual(original.toDict());
  });

  it("serialize rejects unknown format", () => {
    const p = new Payload({});
    expect(() => p.serialize("xml" as "json")).toThrow("Unsupported format");
  });

  it("deserialize rejects unknown format", () => {
    expect(() =>
      Payload.deserialize(new Uint8Array(), "xml" as "json"),
    ).toThrow("Unsupported format");
  });
});

describe("MutablePayload", () => {
  it("creates empty mutable payload", () => {
    const mp = new MutablePayload();
    expect(mp.get("x")).toBeUndefined();
  });

  it("get returns value", () => {
    const mp = new MutablePayload({ x: 1 });
    expect(mp.get("x")).toBe(1);
  });

  it("get returns default for missing", () => {
    const mp = new MutablePayload({});
    expect(mp.get("missing", 42)).toBe(42);
  });

  it("set mutates in place", () => {
    const mp = new MutablePayload({ x: 1 });
    mp.set("x", 99);
    expect(mp.get("x")).toBe(99);
  });

  it("set adds new key", () => {
    const mp = new MutablePayload({});
    mp.set("key", "value");
    expect(mp.get("key")).toBe("value");
  });

  it("toImmutable returns Payload", () => {
    const mp = new MutablePayload({ x: 1 }, { traceId: "t1" });
    const p = mp.toImmutable();
    expect(p.get("x")).toBe(1);
    expect(p.traceId).toBe("t1");
    mp.set("x", 99);
    expect(p.get("x")).toBe(1); // immutable not affected
  });

  it("traceId accessible", () => {
    const mp = new MutablePayload({}, { traceId: "abc" });
    expect(mp.traceId).toBe("abc");
  });

  it("lineage accessible", () => {
    const mp = new MutablePayload({}, { lineage: ["a", "b"] });
    expect(mp.lineage).toEqual(["a", "b"]);
  });

  it("lineage returns a copy", () => {
    const mp = new MutablePayload({}, { lineage: ["a"] });
    const lin = mp.lineage;
    lin.push("b");
    expect(mp.lineage).toEqual(["a"]);
  });

  it("toString includes data", () => {
    const mp = new MutablePayload({ x: 1 });
    expect(mp.toString()).toContain("MutablePayload");
  });
});
