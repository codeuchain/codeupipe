package codeupipe

import (
	"errors"
	"testing"
)

func TestNewState(t *testing.T) {
	s := NewState()
	if len(s.Executed) != 0 {
		t.Fatal("expected empty executed")
	}
	if len(s.Skipped) != 0 {
		t.Fatal("expected empty skipped")
	}
	if s.HasErrors() {
		t.Fatal("expected no errors")
	}
	if s.LastError() != nil {
		t.Fatal("expected nil last error")
	}
}

func TestMarkExecuted(t *testing.T) {
	s := NewState()
	s.MarkExecuted("A")
	s.MarkExecuted("B")
	if len(s.Executed) != 2 || s.Executed[0] != "A" || s.Executed[1] != "B" {
		t.Fatalf("expected [A, B], got %v", s.Executed)
	}
}

func TestMarkSkipped(t *testing.T) {
	s := NewState()
	s.MarkSkipped("X")
	if len(s.Skipped) != 1 || s.Skipped[0] != "X" {
		t.Fatalf("expected [X], got %v", s.Skipped)
	}
}

func TestRecordError(t *testing.T) {
	s := NewState()
	err := errors.New("boom")
	s.RecordError("BadFilter", err)

	if !s.HasErrors() {
		t.Fatal("expected errors")
	}
	if s.LastError() != err {
		t.Fatal("wrong last error")
	}
	if s.Errors[0].Name != "BadFilter" {
		t.Fatal("wrong error name")
	}
}

func TestIncrementChunks(t *testing.T) {
	s := NewState()
	s.IncrementChunks("splitter", 1)
	s.IncrementChunks("splitter", 3)
	if s.ChunksProcessed["splitter"] != 4 {
		t.Fatalf("expected 4, got %d", s.ChunksProcessed["splitter"])
	}
}

func TestRecordTiming(t *testing.T) {
	s := NewState()
	s.RecordTiming("step1", 0.123)
	if s.Timings["step1"] != 0.123 {
		t.Fatal("timing not recorded")
	}
}

func TestMetadata(t *testing.T) {
	s := NewState()
	s.Set("key", "value")
	if s.Get("key") != "value" {
		t.Fatal("metadata not stored")
	}
	if s.Get("missing", "default") != "default" {
		t.Fatal("default not returned")
	}
	if s.Get("missing") != nil {
		t.Fatal("expected nil")
	}
}

func TestReset(t *testing.T) {
	s := NewState()
	s.MarkExecuted("A")
	s.MarkSkipped("B")
	s.RecordError("C", errors.New("err"))
	s.Set("k", "v")
	s.IncrementChunks("x", 1)
	s.RecordTiming("y", 0.5)

	s.Reset()

	if len(s.Executed) != 0 || len(s.Skipped) != 0 || len(s.Errors) != 0 {
		t.Fatal("reset didn't clear")
	}
	if len(s.Metadata) != 0 || len(s.ChunksProcessed) != 0 || len(s.Timings) != 0 {
		t.Fatal("reset didn't clear maps")
	}
}

func TestDiffAddedSteps(t *testing.T) {
	s1 := NewState()
	s1.MarkExecuted("A")

	s2 := NewState()
	s2.MarkExecuted("A")
	s2.MarkExecuted("B")

	d := s1.Diff(s2)
	added, ok := d["added_steps"].([]string)
	if !ok || len(added) != 1 || added[0] != "B" {
		t.Fatalf("expected added [B], got %v", d)
	}
}

func TestDiffRemovedSteps(t *testing.T) {
	s1 := NewState()
	s1.MarkExecuted("A")
	s1.MarkExecuted("B")

	s2 := NewState()
	s2.MarkExecuted("A")

	d := s1.Diff(s2)
	removed, ok := d["removed_steps"].([]string)
	if !ok || len(removed) != 1 || removed[0] != "B" {
		t.Fatalf("expected removed [B], got %v", d)
	}
}

func TestDiffTimingChanges(t *testing.T) {
	s1 := NewState()
	s1.RecordTiming("fast", 0.1)

	s2 := NewState()
	s2.RecordTiming("fast", 0.5)

	d := s1.Diff(s2)
	if _, ok := d["timing_changes"]; !ok {
		t.Fatal("expected timing changes")
	}
}

func TestDiffErrorChanges(t *testing.T) {
	s1 := NewState()
	s2 := NewState()
	s2.RecordError("BadFilter", errors.New("err"))

	d := s1.Diff(s2)
	if _, ok := d["error_changes"]; !ok {
		t.Fatal("expected error changes")
	}
}

func TestDiffEmpty(t *testing.T) {
	s1 := NewState()
	s2 := NewState()
	d := s1.Diff(s2)
	if len(d) != 0 {
		t.Fatalf("expected empty diff, got %v", d)
	}
}

func TestStateString(t *testing.T) {
	s := NewState()
	s.MarkExecuted("A")
	str := s.String()
	if str == "" {
		t.Fatal("empty string")
	}
}
