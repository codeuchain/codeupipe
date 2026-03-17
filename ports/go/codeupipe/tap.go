package codeupipe

// Tap is a non-modifying observation point in the pipeline.
// It receives the payload for inspection (logging, metrics, debugging)
// but never modifies it.
//
// Port of codeupipe/core/tap.py
type Tap interface {
	// Observe inspects the payload without changing it.
	// The pipeline discards any return value.
	Observe(payload Payload)
}
