import { describe, it, expect } from "vitest";
import { Payload } from "../src/payload.js";
import { Valve } from "../src/valve.js";
import type { Filter } from "../src/filter.js";

class DoubleX implements Filter {
  async call(payload: Payload): Promise<Payload> {
    const x = payload.get("x") as number;
    return payload.insert("x", x * 2);
  }
}

describe("Valve", () => {
  it("executes when predicate is true", async () => {
    const valve = new Valve("double_if_positive", new DoubleX(), (p) => {
      const x = p.get("x") as number;
      return x > 0;
    });
    const result = await valve.call(new Payload({ x: 5 }));
    expect(result.get("x")).toBe(10);
    expect(valve._lastSkipped).toBe(false);
  });

  it("skips when predicate is false", async () => {
    const valve = new Valve("double_if_positive", new DoubleX(), (p) => {
      const x = p.get("x") as number;
      return x > 0;
    });
    const result = await valve.call(new Payload({ x: -1 }));
    expect(result.get("x")).toBe(-1); // unchanged
    expect(valve._lastSkipped).toBe(true);
  });

  it("toString includes name", () => {
    const valve = new Valve("test_valve", new DoubleX(), () => true);
    expect(valve.toString()).toContain("test_valve");
  });

  it("conforms to Filter interface (can be used in pipeline)", async () => {
    const valve: Filter = new Valve("v", new DoubleX(), () => true);
    const result = await valve.call(new Payload({ x: 3 }));
    expect(result.get("x")).toBe(6);
  });
});
