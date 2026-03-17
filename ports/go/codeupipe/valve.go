package codeupipe

import "fmt"

// Valve is conditional flow control — gates a Filter with a predicate.
// The inner filter only executes when the predicate returns true.
// Otherwise the payload passes through unchanged.
//
// Valve implements the Filter interface.
//
// Port of codeupipe/core/valve.py
type Valve struct {
	ValveName   string
	inner       Filter
	predicate   func(Payload) bool
	LastSkipped bool
}

// NewValve creates a Valve wrapping a filter with a predicate.
func NewValve(name string, inner Filter, predicate func(Payload) bool) *Valve {
	return &Valve{
		ValveName: name,
		inner:     inner,
		predicate: predicate,
	}
}

// Call evaluates the predicate and either runs or skips the inner filter.
func (v *Valve) Call(payload Payload) (Payload, error) {
	if v.predicate(payload) {
		v.LastSkipped = false
		return v.inner.Call(payload)
	}
	v.LastSkipped = true
	return payload, nil
}

// Name returns the valve name (implements NamedFilter).
func (v *Valve) Name() string {
	return v.ValveName
}

// String returns a human-readable representation.
func (v *Valve) String() string {
	return fmt.Sprintf("Valve(%q)", v.ValveName)
}
