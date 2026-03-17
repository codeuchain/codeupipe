// Package codeupipe provides core pipeline primitives.
//
// Payload: The Data Container
//
// Immutable data container flowing through pipelines.
// Returns fresh copies on modification for safety.
//
// Port of codeupipe/core/payload.py
package codeupipe

import (
	"encoding/json"
	"fmt"
	"maps"
	"slices"
)

// Payload is an immutable data container flowing through the pipeline.
// Returns fresh copies on modification for safety.
type Payload struct {
	data    map[string]any
	traceID string
	lineage []string
}

// NewPayload creates a Payload with optional initial data.
func NewPayload(data map[string]any) Payload {
	d := make(map[string]any)
	if data != nil {
		maps.Copy(d, data)
	}
	return Payload{data: d}
}

// NewPayloadWithOptions creates a Payload with trace ID and lineage.
func NewPayloadWithOptions(data map[string]any, traceID string, lineage []string) Payload {
	d := make(map[string]any)
	if data != nil {
		maps.Copy(d, data)
	}
	l := make([]string, len(lineage))
	copy(l, lineage)
	return Payload{data: d, traceID: traceID, lineage: l}
}

// Get returns the value for key, or defaultValue if absent.
func (p Payload) Get(key string, defaultValue ...any) any {
	if v, ok := p.data[key]; ok {
		return v
	}
	if len(defaultValue) > 0 {
		return defaultValue[0]
	}
	return nil
}

// TraceID returns the trace ID for distributed tracing / lineage tracking.
func (p Payload) TraceID() string {
	return p.traceID
}

// Lineage returns an ordered list of step names this payload has passed through.
func (p Payload) Lineage() []string {
	return slices.Clone(p.lineage)
}

// WithTrace returns a new Payload with the trace ID set.
func (p Payload) WithTrace(traceID string) Payload {
	return Payload{
		data:    p.cloneData(),
		traceID: traceID,
		lineage: slices.Clone(p.lineage),
	}
}

// Stamp records a processing step in lineage (internal).
func (p Payload) Stamp(stepName string) Payload {
	return Payload{
		data:    p.cloneData(),
		traceID: p.traceID,
		lineage: append(slices.Clone(p.lineage), stepName),
	}
}

// Insert returns a fresh Payload with the key/value added.
func (p Payload) Insert(key string, value any) Payload {
	d := p.cloneData()
	d[key] = value
	return Payload{
		data:    d,
		traceID: p.traceID,
		lineage: slices.Clone(p.lineage),
	}
}

// WithMutation converts to a MutablePayload for performance-critical sections.
func (p Payload) WithMutation() *MutablePayload {
	return &MutablePayload{
		data:    p.cloneData(),
		traceID: p.traceID,
		lineage: slices.Clone(p.lineage),
	}
}

// Merge combines payloads, with other taking precedence on conflicts.
func (p Payload) Merge(other Payload) Payload {
	d := p.cloneData()
	for k, v := range other.data {
		d[k] = v
	}
	trace := p.traceID
	if trace == "" {
		trace = other.traceID
	}
	lineage := make([]string, 0, len(p.lineage)+len(other.lineage))
	lineage = append(lineage, p.lineage...)
	lineage = append(lineage, other.lineage...)
	return Payload{data: d, traceID: trace, lineage: lineage}
}

// ToMap returns a shallow copy of the payload data.
func (p Payload) ToMap() map[string]any {
	return p.cloneData()
}

// payloadEnvelope is the JSON serialization format.
type payloadEnvelope struct {
	Data    map[string]any `json:"data"`
	TraceID string         `json:"trace_id,omitempty"`
	Lineage []string       `json:"lineage,omitempty"`
}

// Serialize encodes the payload as JSON bytes for network/storage transport.
func (p Payload) Serialize() ([]byte, error) {
	env := payloadEnvelope{
		Data:    p.data,
		TraceID: p.traceID,
		Lineage: p.lineage,
	}
	return json.Marshal(env)
}

// DeserializePayload decodes a payload from JSON bytes.
func DeserializePayload(raw []byte) (Payload, error) {
	var env payloadEnvelope
	if err := json.Unmarshal(raw, &env); err != nil {
		return Payload{}, fmt.Errorf("deserialize payload: %w", err)
	}
	if env.Data == nil {
		env.Data = make(map[string]any)
	}
	return Payload{
		data:    env.Data,
		traceID: env.TraceID,
		lineage: env.Lineage,
	}, nil
}

// String returns a human-readable representation.
func (p Payload) String() string {
	b, _ := json.Marshal(p.data)
	if p.traceID != "" {
		return fmt.Sprintf("Payload(%s, traceId='%s')", b, p.traceID)
	}
	return fmt.Sprintf("Payload(%s)", b)
}

func (p Payload) cloneData() map[string]any {
	d := make(map[string]any, len(p.data))
	maps.Copy(d, p.data)
	return d
}

// ---------------------------------------------------------------------------
// MutablePayload
// ---------------------------------------------------------------------------

// MutablePayload is a mutable data container for performance-critical sections.
type MutablePayload struct {
	data    map[string]any
	traceID string
	lineage []string
}

// Get returns the value for key, or defaultValue if absent.
func (m *MutablePayload) Get(key string, defaultValue ...any) any {
	if v, ok := m.data[key]; ok {
		return v
	}
	if len(defaultValue) > 0 {
		return defaultValue[0]
	}
	return nil
}

// Set changes a value in place.
func (m *MutablePayload) Set(key string, value any) {
	m.data[key] = value
}

// TraceID returns the trace ID.
func (m *MutablePayload) TraceID() string {
	return m.traceID
}

// Lineage returns the ordered list of step names.
func (m *MutablePayload) Lineage() []string {
	return slices.Clone(m.lineage)
}

// ToImmutable returns a fresh immutable Payload.
func (m *MutablePayload) ToImmutable() Payload {
	d := make(map[string]any, len(m.data))
	maps.Copy(d, m.data)
	return Payload{
		data:    d,
		traceID: m.traceID,
		lineage: slices.Clone(m.lineage),
	}
}

// String returns a human-readable representation.
func (m *MutablePayload) String() string {
	b, _ := json.Marshal(m.data)
	return fmt.Sprintf("MutablePayload(%s)", b)
}
