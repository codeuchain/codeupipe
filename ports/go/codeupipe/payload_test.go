package codeupipe

import (
	"encoding/json"
	"testing"
)

// -----------------------------------------------------------------------
// Payload construction
// -----------------------------------------------------------------------

func TestNewPayloadEmpty(t *testing.T) {
	p := NewPayload(nil)
	if got := p.Get("anything"); got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
	if p.TraceID() != "" {
		t.Fatal("expected empty trace id")
	}
	if len(p.Lineage()) != 0 {
		t.Fatal("expected empty lineage")
	}
}

func TestNewPayloadFromData(t *testing.T) {
	p := NewPayload(map[string]any{"x": 1, "y": "hello"})
	if p.Get("x") != 1 {
		t.Fatalf("expected 1, got %v", p.Get("x"))
	}
	if p.Get("y") != "hello" {
		t.Fatalf("expected 'hello', got %v", p.Get("y"))
	}
}

func TestNewPayloadDefensive(t *testing.T) {
	original := map[string]any{"a": 1}
	p := NewPayload(original)
	original["a"] = 999
	if p.Get("a") != 1 {
		t.Fatal("mutation leaked into payload")
	}
}

func TestPayloadGetDefault(t *testing.T) {
	p := NewPayload(nil)
	if got := p.Get("missing", "fallback"); got != "fallback" {
		t.Fatalf("expected 'fallback', got %v", got)
	}
}

func TestPayloadGetDefaultNil(t *testing.T) {
	p := NewPayload(nil)
	if got := p.Get("missing"); got != nil {
		t.Fatalf("expected nil, got %v", got)
	}
}

// -----------------------------------------------------------------------
// Insert immutability
// -----------------------------------------------------------------------

func TestInsertReturnsNew(t *testing.T) {
	p1 := NewPayload(map[string]any{"a": 1})
	p2 := p1.Insert("b", 2)

	if p1.Get("b") != nil {
		t.Fatal("insert mutated original")
	}
	if p2.Get("a") != 1 {
		t.Fatal("insert lost original data")
	}
	if p2.Get("b") != 2 {
		t.Fatal("insert didn't set value")
	}
}

func TestInsertOverwrite(t *testing.T) {
	p1 := NewPayload(map[string]any{"x": 1})
	p2 := p1.Insert("x", 42)
	if p1.Get("x") != 1 {
		t.Fatal("overwrite mutated original")
	}
	if p2.Get("x") != 42 {
		t.Fatal("overwrite didn't take")
	}
}

// -----------------------------------------------------------------------
// Merge
// -----------------------------------------------------------------------

func TestMerge(t *testing.T) {
	a := NewPayload(map[string]any{"x": 1})
	b := NewPayload(map[string]any{"y": 2})
	merged := a.Merge(b)

	if merged.Get("x") != 1 || merged.Get("y") != 2 {
		t.Fatal("merge lost data")
	}
}

func TestMergePrecedence(t *testing.T) {
	a := NewPayload(map[string]any{"x": 1})
	b := NewPayload(map[string]any{"x": 99})
	merged := a.Merge(b)

	if merged.Get("x") != 99 {
		t.Fatal("other should take precedence")
	}
}

func TestMergeLineage(t *testing.T) {
	a := NewPayloadWithOptions(nil, "", []string{"step1"})
	b := NewPayloadWithOptions(nil, "", []string{"step2"})
	merged := a.Merge(b)

	lin := merged.Lineage()
	if len(lin) != 2 || lin[0] != "step1" || lin[1] != "step2" {
		t.Fatalf("expected [step1, step2], got %v", lin)
	}
}

func TestMergeTracePreference(t *testing.T) {
	a := NewPayloadWithOptions(nil, "trace-a", nil)
	b := NewPayloadWithOptions(nil, "trace-b", nil)
	merged := a.Merge(b)
	if merged.TraceID() != "trace-a" {
		t.Fatal("first trace should win")
	}

	c := NewPayloadWithOptions(nil, "", nil)
	d := NewPayloadWithOptions(nil, "trace-d", nil)
	merged2 := c.Merge(d)
	if merged2.TraceID() != "trace-d" {
		t.Fatal("fallback to other trace")
	}
}

// -----------------------------------------------------------------------
// Trace & Lineage
// -----------------------------------------------------------------------

func TestWithTrace(t *testing.T) {
	p := NewPayload(map[string]any{"x": 1})
	traced := p.WithTrace("abc-123")
	if traced.TraceID() != "abc-123" {
		t.Fatal("trace not set")
	}
	if p.TraceID() != "" {
		t.Fatal("original mutated")
	}
	if traced.Get("x") != 1 {
		t.Fatal("data lost")
	}
}

func TestStamp(t *testing.T) {
	p := NewPayload(nil)
	p2 := p.Stamp("step1").Stamp("step2")

	if len(p.Lineage()) != 0 {
		t.Fatal("stamp mutated original")
	}
	lin := p2.Lineage()
	if len(lin) != 2 || lin[0] != "step1" || lin[1] != "step2" {
		t.Fatalf("expected [step1, step2], got %v", lin)
	}
}

// -----------------------------------------------------------------------
// Serialize / Deserialize
// -----------------------------------------------------------------------

func TestSerializeDeserializeRoundtrip(t *testing.T) {
	p := NewPayloadWithOptions(
		map[string]any{"key": "value", "num": float64(42)},
		"trace-001",
		[]string{"step1"},
	)

	raw, err := p.Serialize()
	if err != nil {
		t.Fatal(err)
	}

	p2, err := DeserializePayload(raw)
	if err != nil {
		t.Fatal(err)
	}

	if p2.Get("key") != "value" {
		t.Fatalf("expected 'value', got %v", p2.Get("key"))
	}
	// JSON numbers deserialize as float64
	if p2.Get("num") != float64(42) {
		t.Fatalf("expected 42, got %v", p2.Get("num"))
	}
	if p2.TraceID() != "trace-001" {
		t.Fatal("trace lost")
	}
	if len(p2.Lineage()) != 1 || p2.Lineage()[0] != "step1" {
		t.Fatal("lineage lost")
	}
}

func TestSerializeEmpty(t *testing.T) {
	p := NewPayload(nil)
	raw, err := p.Serialize()
	if err != nil {
		t.Fatal(err)
	}

	p2, err := DeserializePayload(raw)
	if err != nil {
		t.Fatal(err)
	}

	if p2.TraceID() != "" {
		t.Fatal("expected empty trace")
	}
}

func TestDeserializeInvalid(t *testing.T) {
	_, err := DeserializePayload([]byte("not json"))
	if err == nil {
		t.Fatal("expected error for invalid JSON")
	}
}

func TestSerializeFormat(t *testing.T) {
	p := NewPayloadWithOptions(
		map[string]any{"a": float64(1)},
		"t1",
		[]string{"s1"},
	)
	raw, _ := p.Serialize()

	var env map[string]any
	if err := json.Unmarshal(raw, &env); err != nil {
		t.Fatal(err)
	}
	if _, ok := env["data"]; !ok {
		t.Fatal("missing 'data' key in envelope")
	}
	if _, ok := env["trace_id"]; !ok {
		t.Fatal("missing 'trace_id' key in envelope")
	}
	if _, ok := env["lineage"]; !ok {
		t.Fatal("missing 'lineage' key in envelope")
	}
}

// -----------------------------------------------------------------------
// ToMap
// -----------------------------------------------------------------------

func TestToMapDefensive(t *testing.T) {
	p := NewPayload(map[string]any{"x": 1})
	m := p.ToMap()
	m["x"] = 999
	if p.Get("x") != 1 {
		t.Fatal("ToMap allowed mutation")
	}
}

// -----------------------------------------------------------------------
// String
// -----------------------------------------------------------------------

func TestPayloadString(t *testing.T) {
	p := NewPayload(map[string]any{"x": float64(1)})
	s := p.String()
	if s == "" {
		t.Fatal("empty string")
	}

	traced := p.WithTrace("tid")
	s2 := traced.String()
	if s2 == "" {
		t.Fatal("empty string with trace")
	}
}

// -----------------------------------------------------------------------
// MutablePayload
// -----------------------------------------------------------------------

func TestWithMutation(t *testing.T) {
	p := NewPayload(map[string]any{"x": 1})
	m := p.WithMutation()

	m.Set("x", 42)
	m.Set("y", "new")

	// Original untouched
	if p.Get("x") != 1 {
		t.Fatal("mutation leaked")
	}

	// Mutable has new values
	if m.Get("x") != 42 {
		t.Fatal("set didn't work")
	}
	if m.Get("y") != "new" {
		t.Fatal("set didn't work")
	}
}

func TestMutablePayloadToImmutable(t *testing.T) {
	p := NewPayload(map[string]any{"a": 1})
	m := p.WithMutation()
	m.Set("a", 99)

	p2 := m.ToImmutable()
	if p2.Get("a") != 99 {
		t.Fatal("immutable didn't capture mutation")
	}

	// Further mutations don't affect the immutable
	m.Set("a", 0)
	if p2.Get("a") != 99 {
		t.Fatal("immutable leaked")
	}
}

func TestMutablePayloadDefaults(t *testing.T) {
	m := NewPayload(nil).WithMutation()
	if got := m.Get("missing", "default"); got != "default" {
		t.Fatalf("expected 'default', got %v", got)
	}
}

func TestMutablePayloadTraceAndLineage(t *testing.T) {
	p := NewPayloadWithOptions(nil, "trace-1", []string{"step-a"})
	m := p.WithMutation()
	if m.TraceID() != "trace-1" {
		t.Fatal("trace lost")
	}
	if len(m.Lineage()) != 1 || m.Lineage()[0] != "step-a" {
		t.Fatal("lineage lost")
	}
}

func TestMutablePayloadString(t *testing.T) {
	m := NewPayload(map[string]any{"x": float64(1)}).WithMutation()
	s := m.String()
	if s == "" {
		t.Fatal("empty string")
	}
}
