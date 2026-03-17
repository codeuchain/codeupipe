//! State: Pipeline Execution Metadata
//!
//! Tracks what happened during pipeline execution — which filters ran,
//! which were skipped, timing data, and errors encountered.
//!
//! Port of codeupipe/core/state.py

use std::collections::{HashMap, HashSet};
use std::fmt;

/// Pipeline execution state — tracks filter execution, timing, and errors.
#[derive(Debug, Clone)]
pub struct State {
    pub executed: Vec<String>,
    pub skipped: Vec<String>,
    pub errors: Vec<(String, String)>, // (step_name, error_message)
    pub metadata: HashMap<String, String>,
    pub chunks_processed: HashMap<String, usize>,
    pub timings: HashMap<String, f64>,
}

impl State {
    pub fn new() -> Self {
        State {
            executed: Vec::new(),
            skipped: Vec::new(),
            errors: Vec::new(),
            metadata: HashMap::new(),
            chunks_processed: HashMap::new(),
            timings: HashMap::new(),
        }
    }

    /// Record that a filter executed.
    pub fn mark_executed(&mut self, name: &str) {
        self.executed.push(name.to_string());
    }

    /// Record that a filter was skipped.
    pub fn mark_skipped(&mut self, name: &str) {
        self.skipped.push(name.to_string());
    }

    /// Increment the chunk counter for a streaming step.
    pub fn increment_chunks(&mut self, name: &str, count: usize) {
        let entry = self.chunks_processed.entry(name.to_string()).or_insert(0);
        *entry += count;
    }

    /// Record step execution duration in seconds.
    pub fn record_timing(&mut self, name: &str, duration: f64) {
        self.timings.insert(name.to_string(), duration);
    }

    /// Record an error from a filter.
    pub fn record_error(&mut self, name: &str, error: &str) {
        self.errors.push((name.to_string(), error.to_string()));
    }

    /// Store arbitrary metadata.
    pub fn set(&mut self, key: &str, value: &str) {
        self.metadata.insert(key.to_string(), value.to_string());
    }

    /// Retrieve metadata.
    pub fn get(&self, key: &str) -> Option<&str> {
        self.metadata.get(key).map(|s| s.as_str())
    }

    /// Whether any errors were recorded.
    pub fn has_errors(&self) -> bool {
        !self.errors.is_empty()
    }

    /// The most recent error message, or None.
    pub fn last_error(&self) -> Option<&str> {
        self.errors.last().map(|(_, msg)| msg.as_str())
    }

    /// Reset state for a fresh run.
    pub fn reset(&mut self) {
        self.executed.clear();
        self.skipped.clear();
        self.errors.clear();
        self.metadata.clear();
        self.chunks_processed.clear();
        self.timings.clear();
    }

    /// Compare this state with another — what changed between runs.
    pub fn diff(&self, other: &State) -> HashMap<String, Vec<String>> {
        let mut result = HashMap::new();

        let added: Vec<String> = other.executed.iter()
            .filter(|s| !self.executed.contains(s))
            .cloned()
            .collect();
        let removed: Vec<String> = self.executed.iter()
            .filter(|s| !other.executed.contains(s))
            .cloned()
            .collect();

        if !added.is_empty() { result.insert("added_steps".to_string(), added); }
        if !removed.is_empty() { result.insert("removed_steps".to_string(), removed); }

        let old_errors: HashSet<&str> = self.errors.iter().map(|(n, _)| n.as_str()).collect();
        let new_errors: HashSet<&str> = other.errors.iter().map(|(n, _)| n.as_str()).collect();
        let error_added: Vec<String> = new_errors.difference(&old_errors).map(|s| s.to_string()).collect();
        let error_removed: Vec<String> = old_errors.difference(&new_errors).map(|s| s.to_string()).collect();
        if !error_added.is_empty() || !error_removed.is_empty() {
            let mut changes = Vec::new();
            for a in &error_added { changes.push(format!("+{}", a)); }
            for r in &error_removed { changes.push(format!("-{}", r)); }
            result.insert("error_changes".to_string(), changes);
        }

        result
    }
}

impl Default for State {
    fn default() -> Self {
        Self::new()
    }
}

impl fmt::Display for State {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(
            f,
            "State(executed={:?}, skipped={:?}, errors={}, timings={}, chunks={:?})",
            self.executed,
            self.skipped,
            self.errors.len(),
            self.timings.len(),
            self.chunks_processed,
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn starts_empty() {
        let s = State::new();
        assert!(s.executed.is_empty());
        assert!(s.skipped.is_empty());
        assert!(s.errors.is_empty());
        assert!(!s.has_errors());
        assert!(s.last_error().is_none());
    }

    #[test]
    fn mark_executed() {
        let mut s = State::new();
        s.mark_executed("step1");
        s.mark_executed("step2");
        assert_eq!(s.executed, vec!["step1", "step2"]);
    }

    #[test]
    fn mark_skipped() {
        let mut s = State::new();
        s.mark_skipped("gated");
        assert_eq!(s.skipped, vec!["gated"]);
    }

    #[test]
    fn record_error() {
        let mut s = State::new();
        s.record_error("step1", "boom");
        assert!(s.has_errors());
        assert_eq!(s.last_error(), Some("boom"));
    }

    #[test]
    fn multiple_errors() {
        let mut s = State::new();
        s.record_error("a", "first");
        s.record_error("b", "second");
        assert_eq!(s.last_error(), Some("second"));
        assert_eq!(s.errors.len(), 2);
    }

    #[test]
    fn increment_chunks() {
        let mut s = State::new();
        s.increment_chunks("s1", 1);
        s.increment_chunks("s1", 1);
        s.increment_chunks("s1", 3);
        assert_eq!(s.chunks_processed["s1"], 5);
    }

    #[test]
    fn record_timing() {
        let mut s = State::new();
        s.record_timing("step1", 0.123);
        assert_eq!(s.timings["step1"], 0.123);
    }

    #[test]
    fn metadata_set_get() {
        let mut s = State::new();
        s.set("key", "value");
        assert_eq!(s.get("key"), Some("value"));
        assert_eq!(s.get("missing"), None);
    }

    #[test]
    fn reset_clears() {
        let mut s = State::new();
        s.mark_executed("a");
        s.mark_skipped("b");
        s.record_error("c", "x");
        s.set("k", "v");
        s.increment_chunks("s", 5);
        s.record_timing("a", 1.0);
        s.reset();
        assert!(s.executed.is_empty());
        assert!(s.skipped.is_empty());
        assert!(s.errors.is_empty());
        assert!(s.metadata.is_empty());
        assert!(s.chunks_processed.is_empty());
        assert!(s.timings.is_empty());
    }

    #[test]
    fn diff_added_steps() {
        let mut s1 = State::new();
        s1.mark_executed("a");
        let mut s2 = State::new();
        s2.mark_executed("a");
        s2.mark_executed("b");
        let d = s1.diff(&s2);
        assert_eq!(d.get("added_steps").unwrap(), &vec!["b".to_string()]);
    }

    #[test]
    fn diff_removed_steps() {
        let mut s1 = State::new();
        s1.mark_executed("a");
        s1.mark_executed("b");
        let mut s2 = State::new();
        s2.mark_executed("a");
        let d = s1.diff(&s2);
        assert_eq!(d.get("removed_steps").unwrap(), &vec!["b".to_string()]);
    }

    #[test]
    fn diff_empty_for_identical() {
        let mut s1 = State::new();
        s1.mark_executed("a");
        let mut s2 = State::new();
        s2.mark_executed("a");
        assert!(s1.diff(&s2).is_empty());
    }

    #[test]
    fn display_format() {
        let mut s = State::new();
        s.mark_executed("a");
        let text = format!("{}", s);
        assert!(text.contains("State"));
        assert!(text.contains("a"));
    }
}
