package codeupipe

// Filter is the processing unit — takes a Payload in, processes it,
// and returns a (potentially transformed) Payload out.
//
// Port of codeupipe/core/filter.py
type Filter interface {
	// Call processes a payload and returns the result.
	Call(payload Payload) (Payload, error)
}

// NamedFilter is an optional interface for filters that provide a custom name.
// If not implemented, the pipeline uses the type name.
type NamedFilter interface {
	Name() string
}
