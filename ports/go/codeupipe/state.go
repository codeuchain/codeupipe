package codeupipe

import (
	"fmt"
	"sort"
	"strings"
)

// State tracks what happened during pipeline execution — which filters ran,
// which were skipped, timing data, and errors encountered.
//
// Port of codeupipe/core/state.py
type State struct {
	Executed        []string
	Skipped         []string
	Errors          []StateError
	Metadata        map[string]any
	ChunksProcessed map[string]int
	Timings         map[string]float64
}

// StateError records a filter name and the error it produced.
type StateError struct {
	Name string
	Err  error
}

// NewState creates a fresh State.
func NewState() *State {
	return &State{
		Metadata:        make(map[string]any),
		ChunksProcessed: make(map[string]int),
		Timings:         make(map[string]float64),
	}
}

// MarkExecuted records that a filter executed.
func (s *State) MarkExecuted(name string) {
	s.Executed = append(s.Executed, name)
}

// MarkSkipped records that a filter was skipped.
func (s *State) MarkSkipped(name string) {
	s.Skipped = append(s.Skipped, name)
}

// IncrementChunks increments the chunk counter for a streaming step.
func (s *State) IncrementChunks(name string, count int) {
	s.ChunksProcessed[name] += count
}

// RecordTiming records step execution duration in seconds.
func (s *State) RecordTiming(name string, duration float64) {
	s.Timings[name] = duration
}

// RecordError records an error from a filter.
func (s *State) RecordError(name string, err error) {
	s.Errors = append(s.Errors, StateError{Name: name, Err: err})
}

// Set stores arbitrary metadata.
func (s *State) Set(key string, value any) {
	s.Metadata[key] = value
}

// Get retrieves metadata, with an optional default.
func (s *State) Get(key string, defaultValue ...any) any {
	if v, ok := s.Metadata[key]; ok {
		return v
	}
	if len(defaultValue) > 0 {
		return defaultValue[0]
	}
	return nil
}

// HasErrors returns whether any errors were recorded.
func (s *State) HasErrors() bool {
	return len(s.Errors) > 0
}

// LastError returns the most recent error, or nil.
func (s *State) LastError() error {
	if len(s.Errors) == 0 {
		return nil
	}
	return s.Errors[len(s.Errors)-1].Err
}

// Reset clears state for a fresh run.
func (s *State) Reset() {
	s.Executed = nil
	s.Skipped = nil
	s.Errors = nil
	s.Metadata = make(map[string]any)
	s.ChunksProcessed = make(map[string]int)
	s.Timings = make(map[string]float64)
}

// Diff compares this state with another — what changed between runs.
func (s *State) Diff(other *State) map[string]any {
	result := make(map[string]any)

	// Added / removed steps
	oldSet := toSet(s.Executed)
	newSet := toSet(other.Executed)

	var added, removed []string
	for _, name := range other.Executed {
		if !oldSet[name] {
			added = append(added, name)
		}
	}
	for _, name := range s.Executed {
		if !newSet[name] {
			removed = append(removed, name)
		}
	}
	if len(added) > 0 {
		result["added_steps"] = added
	}
	if len(removed) > 0 {
		result["removed_steps"] = removed
	}

	// Timing changes
	allSteps := make(map[string]bool)
	for k := range s.Timings {
		allSteps[k] = true
	}
	for k := range other.Timings {
		allSteps[k] = true
	}
	timingChanges := make(map[string]any)
	sorted := sortedKeys(allSteps)
	for _, step := range sorted {
		oldT, oldOk := s.Timings[step]
		newT, newOk := other.Timings[step]
		if oldOk != newOk || oldT != newT {
			tc := map[string]any{}
			if oldOk {
				tc["old"] = oldT
			}
			if newOk {
				tc["new"] = newT
			}
			timingChanges[step] = tc
		}
	}
	if len(timingChanges) > 0 {
		result["timing_changes"] = timingChanges
	}

	// Error changes
	oldErrors := make(map[string]bool)
	newErrors := make(map[string]bool)
	for _, e := range s.Errors {
		oldErrors[e.Name] = true
	}
	for _, e := range other.Errors {
		newErrors[e.Name] = true
	}
	var errAdded, errRemoved []string
	for name := range newErrors {
		if !oldErrors[name] {
			errAdded = append(errAdded, name)
		}
	}
	for name := range oldErrors {
		if !newErrors[name] {
			errRemoved = append(errRemoved, name)
		}
	}
	sort.Strings(errAdded)
	sort.Strings(errRemoved)
	if len(errAdded) > 0 || len(errRemoved) > 0 {
		result["error_changes"] = map[string]any{
			"added":   errAdded,
			"removed": errRemoved,
		}
	}

	return result
}

// String returns a human-readable representation.
func (s *State) String() string {
	return fmt.Sprintf(
		"State(executed=[%s], skipped=[%s], errors=%d, timings=%d)",
		strings.Join(s.Executed, ", "),
		strings.Join(s.Skipped, ", "),
		len(s.Errors),
		len(s.Timings),
	)
}

func toSet(items []string) map[string]bool {
	m := make(map[string]bool, len(items))
	for _, s := range items {
		m[s] = true
	}
	return m
}

func sortedKeys(m map[string]bool) []string {
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	sort.Strings(keys)
	return keys
}
