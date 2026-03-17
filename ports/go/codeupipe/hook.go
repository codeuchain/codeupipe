package codeupipe

// Hook provides lifecycle callbacks for pipeline execution.
// All methods are optional — implement only what you need by
// embedding DefaultHook.
//
// Port of codeupipe/core/hook.py
type Hook interface {
	// Before is called before a filter executes.
	// filterName is empty for pipeline-level calls.
	Before(filterName string, payload Payload)

	// After is called after a filter executes.
	// filterName is empty for pipeline-level calls.
	After(filterName string, payload Payload)

	// OnError is called when a filter raises an error.
	// filterName is empty for pipeline-level errors.
	OnError(filterName string, err error, payload Payload)
}

// DefaultHook is a no-op implementation of Hook.
// Embed it in your struct and override only the methods you need.
type DefaultHook struct{}

func (DefaultHook) Before(_ string, _ Payload)           {}
func (DefaultHook) After(_ string, _ Payload)             {}
func (DefaultHook) OnError(_ string, _ error, _ Payload)  {}
