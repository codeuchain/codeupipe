// Pipeline: The Orchestrator
//
// Runs filters in sequence with hooks, taps, and state tracking.
// Supports batch (.Run) and streaming (.Stream) execution modes.
//
// Go-idiomatic: goroutines for parallel, channels for streaming.
//
// Port of codeupipe/core/pipeline.py
package codeupipe

import (
	"fmt"
	"reflect"
	"sync"
	"time"
)

// ---------------------------------------------------------------------------
// Step types
// ---------------------------------------------------------------------------

type stepKind int

const (
	filterStep stepKind = iota
	streamFilterStep
	tapStep
	parallelStep
	pipelineStep
)

type parallelGroup struct {
	filters []Filter
	names   []string
}

type step struct {
	name string
	impl any // Filter | StreamFilter | Tap | *parallelGroup | *Pipeline
	kind stepKind
}

// ---------------------------------------------------------------------------
// Pipeline
// ---------------------------------------------------------------------------

// Pipeline orchestrates filter execution with hooks, taps, and state tracking.
type Pipeline struct {
	steps          []step
	hooks          []Hook
	state          *State
	observeTiming  bool
	observeLineage bool
	disabledTaps   map[string]bool
}

// NewPipeline creates an empty Pipeline.
func NewPipeline() *Pipeline {
	return &Pipeline{
		state:        NewState(),
		disabledTaps: make(map[string]bool),
	}
}

// State returns the pipeline execution state after Run().
func (p *Pipeline) State() *State {
	return p.state
}

// -----------------------------------------------------------------------
// Builder API (fluent — returns *Pipeline for chaining)
// -----------------------------------------------------------------------

// AddFilter adds a filter to the pipeline.
func (p *Pipeline) AddFilter(f Filter, name ...string) *Pipeline {
	n := filterName(f, name)
	p.steps = append(p.steps, step{name: n, impl: f, kind: filterStep})
	return p
}

// AddStreamFilter adds a stream filter to the pipeline.
func (p *Pipeline) AddStreamFilter(sf StreamFilter, name ...string) *Pipeline {
	n := streamFilterName(sf, name)
	p.steps = append(p.steps, step{name: n, impl: sf, kind: streamFilterStep})
	return p
}

// AddTap adds an observation point to the pipeline.
func (p *Pipeline) AddTap(t Tap, name ...string) *Pipeline {
	n := tapName(t, name)
	p.steps = append(p.steps, step{name: n, impl: t, kind: tapStep})
	return p
}

// UseHook attaches a lifecycle hook.
func (p *Pipeline) UseHook(h Hook) *Pipeline {
	p.hooks = append(p.hooks, h)
	return p
}

// AddParallel adds a parallel fan-out/fan-in group of filters.
func (p *Pipeline) AddParallel(filters []Filter, name string, names ...string) *Pipeline {
	fnames := make([]string, len(filters))
	for i, f := range filters {
		if i < len(names) && names[i] != "" {
			fnames[i] = names[i]
		} else {
			fnames[i] = filterName(f, nil)
		}
	}
	pg := &parallelGroup{filters: filters, names: fnames}
	p.steps = append(p.steps, step{name: name, impl: pg, kind: parallelStep})
	return p
}

// AddPipeline nests a Pipeline as a single step inside this Pipeline.
func (p *Pipeline) AddPipeline(child *Pipeline, name string) *Pipeline {
	p.steps = append(p.steps, step{name: name, impl: child, kind: pipelineStep})
	return p
}

// Observe enables observation features (timing, lineage tracking).
func (p *Pipeline) Observe(timing, lineage bool) *Pipeline {
	p.observeTiming = timing
	p.observeLineage = lineage
	return p
}

// DisableTaps disables specific taps by name at runtime.
func (p *Pipeline) DisableTaps(names ...string) *Pipeline {
	for _, n := range names {
		p.disabledTaps[n] = true
	}
	return p
}

// EnableTaps re-enables previously disabled taps.
func (p *Pipeline) EnableTaps(names ...string) *Pipeline {
	for _, n := range names {
		delete(p.disabledTaps, n)
	}
	return p
}

// Call implements the Filter interface so pipelines can be nested.
func (p *Pipeline) Call(payload Payload) (Payload, error) {
	return p.Run(payload)
}

// -----------------------------------------------------------------------
// Batch execution
// -----------------------------------------------------------------------

// Run executes the pipeline in batch mode.
func (p *Pipeline) Run(initialPayload Payload) (Payload, error) {
	// Reject StreamFilters in batch mode
	for _, s := range p.steps {
		if s.kind == streamFilterStep {
			return Payload{}, fmt.Errorf(
				"pipeline contains StreamFilter '%s'; use pipeline.Stream() instead",
				s.name,
			)
		}
	}

	p.state = NewState()
	payload := initialPayload

	// Hook: pipeline start
	for _, h := range p.hooks {
		h.Before("", payload)
	}

	var stepName string

	for _, s := range p.steps {
		stepName = s.name

		// --- Tap ---
		if s.kind == tapStep {
			if p.disabledTaps[s.name] {
				p.state.MarkSkipped(s.name)
				continue
			}
			s.impl.(Tap).Observe(payload)
			p.state.MarkExecuted(s.name)
			continue
		}

		t0 := time.Now()

		switch s.kind {
		case parallelStep:
			// Goroutine-based parallel execution
			pg := s.impl.(*parallelGroup)
			results, err := p.runParallel(pg.filters, payload)
			if err != nil {
				p.recordTimingIfEnabled(s.name, t0)
				for _, h := range p.hooks {
					h.OnError("", err, payload)
				}
				return Payload{}, err
			}
			for _, r := range results {
				payload = payload.Merge(r)
			}
			p.state.MarkExecuted(s.name)

		case pipelineStep:
			child := s.impl.(*Pipeline)
			for _, h := range p.hooks {
				h.Before(s.name, payload)
			}
			result, err := child.Run(payload)
			if err != nil {
				p.recordTimingIfEnabled(s.name, t0)
				for _, h := range p.hooks {
					h.OnError("", err, payload)
				}
				return Payload{}, err
			}
			payload = result
			p.state.MarkExecuted(s.name)
			for _, h := range p.hooks {
				h.After(s.name, payload)
			}

		default: // filterStep
			f := s.impl.(Filter)
			for _, h := range p.hooks {
				h.Before(s.name, payload)
			}

			result, err := f.Call(payload)
			if err != nil {
				p.recordTimingIfEnabled(s.name, t0)
				for _, h := range p.hooks {
					h.OnError(s.name, err, payload)
				}
				return Payload{}, err
			}
			payload = result

			// Valve skip detection
			if valve, ok := f.(*Valve); ok && valve.LastSkipped {
				p.state.MarkSkipped(s.name)
			} else {
				p.state.MarkExecuted(s.name)
			}

			for _, h := range p.hooks {
				h.After(s.name, payload)
			}
		}

		p.recordTimingIfEnabled(s.name, t0)
		if p.observeLineage {
			payload = payload.Stamp(s.name)
		}
	}

	// Hook: pipeline end
	for _, h := range p.hooks {
		h.After("", payload)
	}

	_ = stepName // suppress unused warning
	return payload, nil
}

// -----------------------------------------------------------------------
// Streaming
// -----------------------------------------------------------------------

// Stream processes payloads from source through the pipeline, writing
// results to out. Both channels carry Payload values.
//
// The caller closes source when done sending. Stream closes out when
// all processing finishes. Returns any error encountered.
func (p *Pipeline) Stream(source <-chan Payload) (<-chan Payload, <-chan error) {
	out := make(chan Payload)
	errCh := make(chan error, 1)

	go func() {
		defer close(out)

		p.state = NewState()

		sentinel := NewPayload(nil)
		for _, h := range p.hooks {
			h.Before("", sentinel)
		}

		var err error
		current := source

		for _, s := range p.steps {
			current = p.wrapStep(current, s)
		}

		for payload := range current {
			out <- payload
		}

		// Check for sentinel error from step wrappers
		if err != nil {
			for _, h := range p.hooks {
				h.OnError("", err, sentinel)
			}
			errCh <- err
			return
		}

		for _, h := range p.hooks {
			h.After("", sentinel)
		}
	}()

	return out, errCh
}

func (p *Pipeline) wrapStep(upstream <-chan Payload, s step) <-chan Payload {
	out := make(chan Payload)

	go func() {
		defer close(out)

		switch s.kind {
		case tapStep:
			if p.disabledTaps[s.name] {
				p.state.MarkSkipped(s.name)
				for payload := range upstream {
					out <- payload
				}
				return
			}
			p.markExecutedOnce(s.name)
			tap := s.impl.(Tap)
			for payload := range upstream {
				tap.Observe(payload)
				p.state.IncrementChunks(s.name, 1)
				out <- payload
			}

		case streamFilterStep:
			p.markExecutedOnce(s.name)
			sf := s.impl.(StreamFilter)
			for chunk := range upstream {
				results, err := sf.Stream(chunk)
				if err != nil {
					// Propagate error by stopping
					return
				}
				for _, r := range results {
					p.state.IncrementChunks(s.name, 1)
					out <- r
				}
			}

		case filterStep:
			p.markExecutedOnce(s.name)
			f := s.impl.(Filter)
			for chunk := range upstream {
				result, err := f.Call(chunk)
				if err != nil {
					return
				}
				p.state.IncrementChunks(s.name, 1)
				out <- result
			}

		case parallelStep:
			p.markExecutedOnce(s.name)
			pg := s.impl.(*parallelGroup)
			for chunk := range upstream {
				results, err := p.runParallel(pg.filters, chunk)
				if err != nil {
					return
				}
				merged := chunk
				for _, r := range results {
					merged = merged.Merge(r)
				}
				p.state.IncrementChunks(s.name, 1)
				out <- merged
			}

		case pipelineStep:
			p.markExecutedOnce(s.name)
			child := s.impl.(*Pipeline)
			for chunk := range upstream {
				result, err := child.Run(chunk)
				if err != nil {
					return
				}
				p.state.IncrementChunks(s.name, 1)
				out <- result
			}
		}
	}()

	return out
}

// -----------------------------------------------------------------------
// Introspection
// -----------------------------------------------------------------------

// StepInfo describes a single step for introspection.
type StepInfo struct {
	Name     string     `json:"name"`
	Type     string     `json:"type"`
	Class    string     `json:"class,omitempty"`
	Filters  []StepInfo `json:"filters,omitempty"`
	Children []StepInfo `json:"children,omitempty"`
}

// DescribeResult is the output of Describe().
type DescribeResult struct {
	Steps     []StepInfo `json:"steps"`
	Hooks     []string   `json:"hooks"`
	StepCount int        `json:"step_count"`
}

// Describe returns a machine-readable tree of the pipeline structure.
func (p *Pipeline) Describe() DescribeResult {
	steps := make([]StepInfo, 0, len(p.steps))

	for _, s := range p.steps {
		switch s.kind {
		case parallelStep:
			pg := s.impl.(*parallelGroup)
			children := make([]StepInfo, len(pg.filters))
			for i, f := range pg.filters {
				children[i] = StepInfo{
					Name: pg.names[i],
					Type: "filter",
				}
				_ = f
			}
			steps = append(steps, StepInfo{
				Name:    s.name,
				Type:    "parallel",
				Filters: children,
			})

		case pipelineStep:
			child := s.impl.(*Pipeline)
			desc := child.Describe()
			steps = append(steps, StepInfo{
				Name:     s.name,
				Type:     "pipeline",
				Children: desc.Steps,
			})

		default:
			steps = append(steps, StepInfo{
				Name:  s.name,
				Type:  kindString(s.kind),
				Class: typeName(s.impl),
			})
		}
	}

	hookNames := make([]string, len(p.hooks))
	for i, h := range p.hooks {
		hookNames[i] = typeName(h)
	}

	return DescribeResult{
		Steps:     steps,
		Hooks:     hookNames,
		StepCount: len(steps),
	}
}

// -----------------------------------------------------------------------
// Helpers
// -----------------------------------------------------------------------

func (p *Pipeline) runParallel(filters []Filter, payload Payload) ([]Payload, error) {
	results := make([]Payload, len(filters))
	errs := make([]error, len(filters))
	var wg sync.WaitGroup

	for i, f := range filters {
		wg.Add(1)
		go func(idx int, filter Filter) {
			defer wg.Done()
			r, err := filter.Call(payload)
			results[idx] = r
			errs[idx] = err
		}(i, f)
	}
	wg.Wait()

	for _, err := range errs {
		if err != nil {
			return nil, err
		}
	}
	return results, nil
}

func (p *Pipeline) recordTimingIfEnabled(name string, t0 time.Time) {
	if p.observeTiming {
		p.state.RecordTiming(name, time.Since(t0).Seconds())
	}
}

func (p *Pipeline) markExecutedOnce(name string) {
	for _, n := range p.state.Executed {
		if n == name {
			return
		}
	}
	p.state.MarkExecuted(name)
}

func filterName(f Filter, explicit []string) string {
	if len(explicit) > 0 && explicit[0] != "" {
		return explicit[0]
	}
	if nf, ok := f.(NamedFilter); ok {
		return nf.Name()
	}
	return typeName(f)
}

func streamFilterName(sf StreamFilter, explicit []string) string {
	if len(explicit) > 0 && explicit[0] != "" {
		return explicit[0]
	}
	return typeName(sf)
}

func tapName(t Tap, explicit []string) string {
	if len(explicit) > 0 && explicit[0] != "" {
		return explicit[0]
	}
	return typeName(t)
}

func typeName(v any) string {
	t := reflect.TypeOf(v)
	if t.Kind() == reflect.Ptr {
		t = t.Elem()
	}
	return t.Name()
}

func kindString(k stepKind) string {
	switch k {
	case filterStep:
		return "filter"
	case streamFilterStep:
		return "stream_filter"
	case tapStep:
		return "tap"
	case parallelStep:
		return "parallel"
	case pipelineStep:
		return "pipeline"
	default:
		return "unknown"
	}
}
