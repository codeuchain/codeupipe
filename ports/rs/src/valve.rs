//! Valve: Conditional Flow Control
//!
//! A Valve wraps a Filter with a predicate — the inner filter only
//! executes when the predicate evaluates to true.
//!
//! Port of codeupipe/core/valve.py

use crate::filter::Filter;
use crate::payload::Payload;
use std::sync::atomic::{AtomicBool, Ordering};
use std::fmt;

/// Conditional flow control — gates a Filter with a predicate.
pub struct Valve {
    name: String,
    inner: Box<dyn Filter>,
    predicate: Box<dyn Fn(&Payload) -> bool + Send + Sync>,
    last_skipped: AtomicBool,
}

impl Valve {
    pub fn new<F>(
        name: &str,
        inner: Box<dyn Filter>,
        predicate: F,
    ) -> Self
    where
        F: Fn(&Payload) -> bool + Send + Sync + 'static,
    {
        Valve {
            name: name.to_string(),
            inner,
            predicate: Box::new(predicate),
            last_skipped: AtomicBool::new(false),
        }
    }

    /// Whether the last call was skipped.
    pub fn last_skipped(&self) -> bool {
        self.last_skipped.load(Ordering::Relaxed)
    }
}

impl Filter for Valve {
    fn call(&self, payload: Payload) -> Result<Payload, Box<dyn std::error::Error + Send + Sync>> {
        if (self.predicate)(&payload) {
            self.last_skipped.store(false, Ordering::Relaxed);
            self.inner.call(payload)
        } else {
            self.last_skipped.store(true, Ordering::Relaxed);
            Ok(payload)
        }
    }

    fn name(&self) -> &str {
        &self.name
    }
}

impl fmt::Display for Valve {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "Valve(\"{}\")", self.name)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::payload::Value;

    struct DoubleX;
    impl Filter for DoubleX {
        fn call(&self, payload: Payload) -> Result<Payload, Box<dyn std::error::Error + Send + Sync>> {
            let x = payload.get("x").and_then(|v| v.as_int()).unwrap_or(0);
            Ok(payload.insert("x", Value::Int(x * 2)))
        }
        fn name(&self) -> &str { "DoubleX" }
    }

    #[test]
    fn executes_when_predicate_true() {
        let valve = Valve::new("double_if_pos", Box::new(DoubleX), |p| {
            p.get("x").and_then(|v| v.as_int()).unwrap_or(0) > 0
        });
        let result = valve.call(Payload::new().insert("x", Value::Int(5))).unwrap();
        assert_eq!(result.get("x").unwrap().as_int(), Some(10));
    }

    #[test]
    fn skips_when_predicate_false() {
        let valve = Valve::new("double_if_pos", Box::new(DoubleX), |p| {
            p.get("x").and_then(|v| v.as_int()).unwrap_or(0) > 0
        });
        let result = valve.call(Payload::new().insert("x", Value::Int(-1))).unwrap();
        assert_eq!(result.get("x").unwrap().as_int(), Some(-1));
        assert!(valve.last_skipped());
    }

    #[test]
    fn display() {
        let valve = Valve::new("test_valve", Box::new(DoubleX), |_| true);
        let s = format!("{}", valve);
        assert!(s.contains("test_valve"));
    }
}
