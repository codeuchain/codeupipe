package codeupipe

// StreamFilter processes one Payload chunk and returns zero or more
// output chunks. Enables filtering (drop), mapping (1→1), and
// fan-out (1→N) at constant memory.
//
// In Go, streaming uses channels in the Pipeline. The StreamFilter
// interface returns a slice for simplicity; the Pipeline wraps it
// in channel-based plumbing.
//
// Port of codeupipe/core/stream_filter.py
type StreamFilter interface {
	// Stream processes one chunk and returns zero or more output chunks.
	//
	// Return nil or empty slice to drop a chunk.
	// Return one element for a 1→1 mapping.
	// Return multiple elements for fan-out.
	Stream(chunk Payload) ([]Payload, error)
}
