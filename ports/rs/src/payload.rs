//! Payload: The Data Container
//!
//! Immutable data container flowing through pipelines.
//! Returns fresh copies on modification for safety.
//!
//! Port of codeupipe/core/payload.py

use std::collections::HashMap;
use std::fmt;

/// A dynamic value that can be stored in a Payload.
#[derive(Debug, Clone, PartialEq)]
pub enum Value {
    Null,
    Bool(bool),
    Int(i64),
    Float(f64),
    Str(String),
    List(Vec<Value>),
    Map(HashMap<String, Value>),
}

impl Value {
    /// Convenience: extract as i64 if Int.
    pub fn as_int(&self) -> Option<i64> {
        match self {
            Value::Int(v) => Some(*v),
            _ => None,
        }
    }

    /// Convenience: extract as f64 if Float.
    pub fn as_float(&self) -> Option<f64> {
        match self {
            Value::Float(v) => Some(*v),
            _ => None,
        }
    }

    /// Convenience: extract as &str if Str.
    pub fn as_str(&self) -> Option<&str> {
        match self {
            Value::Str(v) => Some(v),
            _ => None,
        }
    }

    /// Convenience: extract as bool if Bool.
    pub fn as_bool(&self) -> Option<bool> {
        match self {
            Value::Bool(v) => Some(*v),
            _ => None,
        }
    }
}

impl From<i64> for Value {
    fn from(v: i64) -> Self { Value::Int(v) }
}

impl From<f64> for Value {
    fn from(v: f64) -> Self { Value::Float(v) }
}

impl From<bool> for Value {
    fn from(v: bool) -> Self { Value::Bool(v) }
}

impl From<&str> for Value {
    fn from(v: &str) -> Self { Value::Str(v.to_string()) }
}

impl From<String> for Value {
    fn from(v: String) -> Self { Value::Str(v) }
}

/// Immutable data container — holds data flowing through the pipeline.
/// Returns fresh copies on modification for safety.
#[derive(Debug, Clone)]
pub struct Payload {
    data: HashMap<String, Value>,
    trace_id: Option<String>,
    lineage: Vec<String>,
}

impl Payload {
    /// Create a new empty Payload.
    pub fn new() -> Self {
        Payload {
            data: HashMap::new(),
            trace_id: None,
            lineage: Vec::new(),
        }
    }

    /// Create a Payload from a HashMap.
    pub fn from_data(data: HashMap<String, Value>) -> Self {
        Payload {
            data,
            trace_id: None,
            lineage: Vec::new(),
        }
    }

    /// Return the value for key, or None if absent.
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.data.get(key)
    }

    /// Return the value for key, or a default if absent.
    pub fn get_or<'a>(&'a self, key: &str, default: &'a Value) -> &'a Value {
        self.data.get(key).unwrap_or(default)
    }

    /// Trace ID for distributed tracing / lineage tracking.
    pub fn trace_id(&self) -> Option<&str> {
        self.trace_id.as_deref()
    }

    /// Ordered list of step names this payload has passed through.
    pub fn lineage(&self) -> &[String] {
        &self.lineage
    }

    /// Return a new Payload with trace ID set.
    pub fn with_trace(&self, trace_id: &str) -> Payload {
        Payload {
            data: self.data.clone(),
            trace_id: Some(trace_id.to_string()),
            lineage: self.lineage.clone(),
        }
    }

    /// Record a processing step in lineage (internal).
    pub fn stamp(&self, step_name: &str) -> Payload {
        let mut lineage = self.lineage.clone();
        lineage.push(step_name.to_string());
        Payload {
            data: self.data.clone(),
            trace_id: self.trace_id.clone(),
            lineage,
        }
    }

    /// Return a fresh Payload with the addition.
    pub fn insert(&self, key: &str, value: Value) -> Payload {
        let mut data = self.data.clone();
        data.insert(key.to_string(), value);
        Payload {
            data,
            trace_id: self.trace_id.clone(),
            lineage: self.lineage.clone(),
        }
    }

    /// Convert to a mutable sibling for performance-critical sections.
    pub fn with_mutation(self) -> MutablePayload {
        MutablePayload {
            data: self.data,
            trace_id: self.trace_id,
            lineage: self.lineage,
        }
    }

    /// Combine payloads, with other taking precedence on conflicts.
    pub fn merge(&self, other: &Payload) -> Payload {
        let mut data = self.data.clone();
        for (k, v) in &other.data {
            data.insert(k.clone(), v.clone());
        }
        let trace_id = self.trace_id.clone().or_else(|| other.trace_id.clone());
        let mut lineage = self.lineage.clone();
        lineage.extend(other.lineage.iter().cloned());
        Payload {
            data,
            trace_id,
            lineage,
        }
    }

    /// Express as HashMap for ecosystem integration.
    pub fn to_map(&self) -> HashMap<String, Value> {
        self.data.clone()
    }

    /// Serialize payload to JSON bytes.
    pub fn serialize(&self) -> Vec<u8> {
        // Minimal JSON serialization — no external deps
        let mut parts = Vec::new();
        parts.push(format!("\"data\":{}", self.serialize_map(&self.data)));
        if let Some(ref tid) = self.trace_id {
            parts.push(format!("\"trace_id\":\"{}\"", Self::escape_json(tid)));
        }
        if !self.lineage.is_empty() {
            let lin: Vec<String> = self.lineage
                .iter()
                .map(|s| format!("\"{}\"", Self::escape_json(s)))
                .collect();
            parts.push(format!("\"lineage\":[{}]", lin.join(",")));
        }
        format!("{{{}}}", parts.join(",")).into_bytes()
    }

    /// Deserialize payload from JSON bytes.
    pub fn deserialize(raw: &[u8]) -> Result<Payload, String> {
        // Minimal JSON parsing — handles the envelope we produce
        let text = std::str::from_utf8(raw).map_err(|e| e.to_string())?;
        Self::parse_envelope(text)
    }

    // ------------------------------------------------------------------
    // Minimal JSON helpers (no serde dependency)
    // ------------------------------------------------------------------

    fn escape_json(s: &str) -> String {
        s.replace('\\', "\\\\")
            .replace('"', "\\\"")
            .replace('\n', "\\n")
            .replace('\r', "\\r")
            .replace('\t', "\\t")
    }

    fn serialize_value(v: &Value) -> String {
        match v {
            Value::Null => "null".to_string(),
            Value::Bool(b) => if *b { "true" } else { "false" }.to_string(),
            Value::Int(i) => i.to_string(),
            Value::Float(f) => format!("{}", f),
            Value::Str(s) => format!("\"{}\"", Self::escape_json(s)),
            Value::List(items) => {
                let parts: Vec<String> = items.iter().map(|v| Self::serialize_value(v)).collect();
                format!("[{}]", parts.join(","))
            }
            Value::Map(map) => Self::serialize_map_static(map),
        }
    }

    fn serialize_map(&self, map: &HashMap<String, Value>) -> String {
        Self::serialize_map_static(map)
    }

    fn serialize_map_static(map: &HashMap<String, Value>) -> String {
        let parts: Vec<String> = map
            .iter()
            .map(|(k, v)| format!("\"{}\":{}", Self::escape_json(k), Self::serialize_value(v)))
            .collect();
        format!("{{{}}}", parts.join(","))
    }

    // Minimal JSON parser for our envelope format
    fn parse_envelope(text: &str) -> Result<Payload, String> {
        let text = text.trim();
        if !text.starts_with('{') || !text.ends_with('}') {
            return Err("Expected JSON object".to_string());
        }
        let inner = &text[1..text.len()-1];

        let mut data = HashMap::new();
        let mut trace_id = None;
        let mut lineage = Vec::new();

        // Simple key-value pair extraction
        let mut pos = 0;
        let chars: Vec<char> = inner.chars().collect();
        while pos < chars.len() {
            // Skip whitespace and commas
            while pos < chars.len() && (chars[pos] == ' ' || chars[pos] == ',' || chars[pos] == '\n' || chars[pos] == '\r' || chars[pos] == '\t') {
                pos += 1;
            }
            if pos >= chars.len() { break; }

            // Parse key
            if chars[pos] != '"' { break; }
            let key = Self::parse_json_string(&chars, &mut pos)?;

            // Skip colon
            while pos < chars.len() && (chars[pos] == ' ' || chars[pos] == ':') {
                pos += 1;
            }

            match key.as_str() {
                "data" => {
                    data = Self::parse_json_map(&chars, &mut pos)?;
                }
                "trace_id" => {
                    trace_id = Some(Self::parse_json_string(&chars, &mut pos)?);
                }
                "lineage" => {
                    lineage = Self::parse_json_string_array(&chars, &mut pos)?;
                }
                _ => {
                    Self::skip_json_value(&chars, &mut pos)?;
                }
            }
        }

        Ok(Payload { data, trace_id, lineage })
    }

    fn parse_json_string(chars: &[char], pos: &mut usize) -> Result<String, String> {
        if *pos >= chars.len() || chars[*pos] != '"' {
            return Err(format!("Expected '\"' at position {}", pos));
        }
        *pos += 1;
        let mut result = String::new();
        while *pos < chars.len() && chars[*pos] != '"' {
            if chars[*pos] == '\\' {
                *pos += 1;
                if *pos < chars.len() {
                    match chars[*pos] {
                        'n' => result.push('\n'),
                        'r' => result.push('\r'),
                        't' => result.push('\t'),
                        '"' => result.push('"'),
                        '\\' => result.push('\\'),
                        c => { result.push('\\'); result.push(c); }
                    }
                }
            } else {
                result.push(chars[*pos]);
            }
            *pos += 1;
        }
        if *pos < chars.len() { *pos += 1; } // skip closing quote
        Ok(result)
    }

    fn parse_json_value(chars: &[char], pos: &mut usize) -> Result<Value, String> {
        // Skip whitespace
        while *pos < chars.len() && chars[*pos].is_whitespace() { *pos += 1; }
        if *pos >= chars.len() { return Err("Unexpected end of input".to_string()); }

        match chars[*pos] {
            '"' => Ok(Value::Str(Self::parse_json_string(chars, pos)?)),
            '{' => Ok(Value::Map(Self::parse_json_map(chars, pos)?)),
            '[' => {
                *pos += 1;
                let mut items = Vec::new();
                loop {
                    while *pos < chars.len() && chars[*pos].is_whitespace() { *pos += 1; }
                    if *pos < chars.len() && chars[*pos] == ']' { *pos += 1; break; }
                    items.push(Self::parse_json_value(chars, pos)?);
                    while *pos < chars.len() && (chars[*pos] == ',' || chars[*pos].is_whitespace()) { *pos += 1; }
                }
                Ok(Value::List(items))
            }
            't' => {
                if chars[*pos..].iter().take(4).collect::<String>() == "true" {
                    *pos += 4;
                    Ok(Value::Bool(true))
                } else {
                    Err("Invalid token".to_string())
                }
            }
            'f' => {
                if chars[*pos..].iter().take(5).collect::<String>() == "false" {
                    *pos += 5;
                    Ok(Value::Bool(false))
                } else {
                    Err("Invalid token".to_string())
                }
            }
            'n' => {
                if chars[*pos..].iter().take(4).collect::<String>() == "null" {
                    *pos += 4;
                    Ok(Value::Null)
                } else {
                    Err("Invalid token".to_string())
                }
            }
            c if c == '-' || c.is_ascii_digit() => {
                let start = *pos;
                if chars[*pos] == '-' { *pos += 1; }
                while *pos < chars.len() && chars[*pos].is_ascii_digit() { *pos += 1; }
                let mut is_float = false;
                if *pos < chars.len() && chars[*pos] == '.' {
                    is_float = true;
                    *pos += 1;
                    while *pos < chars.len() && chars[*pos].is_ascii_digit() { *pos += 1; }
                }
                let num_str: String = chars[start..*pos].iter().collect();
                if is_float {
                    num_str.parse::<f64>().map(Value::Float).map_err(|e| e.to_string())
                } else {
                    num_str.parse::<i64>().map(Value::Int).map_err(|e| e.to_string())
                }
            }
            _ => Err(format!("Unexpected character '{}' at position {}", chars[*pos], pos)),
        }
    }

    fn parse_json_map(chars: &[char], pos: &mut usize) -> Result<HashMap<String, Value>, String> {
        if *pos >= chars.len() || chars[*pos] != '{' {
            return Err("Expected '{'".to_string());
        }
        *pos += 1;
        let mut map = HashMap::new();
        loop {
            while *pos < chars.len() && (chars[*pos].is_whitespace() || chars[*pos] == ',') { *pos += 1; }
            if *pos < chars.len() && chars[*pos] == '}' { *pos += 1; break; }
            let key = Self::parse_json_string(chars, pos)?;
            while *pos < chars.len() && (chars[*pos].is_whitespace() || chars[*pos] == ':') { *pos += 1; }
            let value = Self::parse_json_value(chars, pos)?;
            map.insert(key, value);
        }
        Ok(map)
    }

    fn parse_json_string_array(chars: &[char], pos: &mut usize) -> Result<Vec<String>, String> {
        if *pos >= chars.len() || chars[*pos] != '[' {
            return Err("Expected '['".to_string());
        }
        *pos += 1;
        let mut result = Vec::new();
        loop {
            while *pos < chars.len() && (chars[*pos].is_whitespace() || chars[*pos] == ',') { *pos += 1; }
            if *pos < chars.len() && chars[*pos] == ']' { *pos += 1; break; }
            result.push(Self::parse_json_string(chars, pos)?);
        }
        Ok(result)
    }

    fn skip_json_value(chars: &[char], pos: &mut usize) -> Result<(), String> {
        Self::parse_json_value(chars, pos)?;
        Ok(())
    }
}

impl Default for Payload {
    fn default() -> Self {
        Self::new()
    }
}

impl fmt::Display for Payload {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match &self.trace_id {
            Some(tid) => write!(f, "Payload({:?}, trace_id='{}')", self.data, tid),
            None => write!(f, "Payload({:?})", self.data),
        }
    }
}

/// Mutable data container for performance-critical sections.
#[derive(Debug, Clone)]
pub struct MutablePayload {
    data: HashMap<String, Value>,
    trace_id: Option<String>,
    lineage: Vec<String>,
}

impl MutablePayload {
    /// Create a new empty MutablePayload.
    pub fn new() -> Self {
        MutablePayload {
            data: HashMap::new(),
            trace_id: None,
            lineage: Vec::new(),
        }
    }

    /// Return the value for key, or None if absent.
    pub fn get(&self, key: &str) -> Option<&Value> {
        self.data.get(key)
    }

    /// Change in place.
    pub fn set(&mut self, key: &str, value: Value) {
        self.data.insert(key.to_string(), value);
    }

    /// Trace ID.
    pub fn trace_id(&self) -> Option<&str> {
        self.trace_id.as_deref()
    }

    /// Lineage.
    pub fn lineage(&self) -> &[String] {
        &self.lineage
    }

    /// Return to safety with a fresh immutable copy.
    pub fn to_immutable(self) -> Payload {
        Payload {
            data: self.data,
            trace_id: self.trace_id,
            lineage: self.lineage,
        }
    }
}

impl Default for MutablePayload {
    fn default() -> Self {
        Self::new()
    }
}

impl fmt::Display for MutablePayload {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        write!(f, "MutablePayload({:?})", self.data)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn empty_payload() {
        let p = Payload::new();
        assert!(p.to_map().is_empty());
        assert!(p.trace_id().is_none());
        assert!(p.lineage().is_empty());
    }

    #[test]
    fn payload_from_data() {
        let mut data = HashMap::new();
        data.insert("x".to_string(), Value::Int(1));
        let p = Payload::from_data(data);
        assert_eq!(p.get("x").unwrap().as_int(), Some(1));
    }

    #[test]
    fn get_missing_returns_none() {
        let p = Payload::new();
        assert!(p.get("missing").is_none());
    }

    #[test]
    fn get_or_returns_default() {
        let p = Payload::new();
        let default = Value::Int(42);
        assert_eq!(p.get_or("missing", &default).as_int(), Some(42));
    }

    #[test]
    fn insert_returns_new_payload() {
        let p1 = Payload::new().insert("a", Value::Int(1));
        let p2 = p1.insert("b", Value::Int(2));
        assert!(p1.get("b").is_none());
        assert_eq!(p2.get("a").unwrap().as_int(), Some(1));
        assert_eq!(p2.get("b").unwrap().as_int(), Some(2));
    }

    #[test]
    fn insert_does_not_mutate_original() {
        let p1 = Payload::new().insert("x", Value::Int(1));
        let _p2 = p1.insert("y", Value::Int(2));
        assert!(p1.get("y").is_none());
    }

    #[test]
    fn merge_combines() {
        let p1 = Payload::new().insert("a", Value::Int(1));
        let p2 = Payload::new().insert("b", Value::Int(2));
        let merged = p1.merge(&p2);
        assert_eq!(merged.get("a").unwrap().as_int(), Some(1));
        assert_eq!(merged.get("b").unwrap().as_int(), Some(2));
    }

    #[test]
    fn merge_precedence() {
        let p1 = Payload::new().insert("x", Value::Str("old".to_string()));
        let p2 = Payload::new().insert("x", Value::Str("new".to_string()));
        let merged = p1.merge(&p2);
        assert_eq!(merged.get("x").unwrap().as_str(), Some("new"));
    }

    #[test]
    fn merge_combines_lineage() {
        let p1 = Payload::new().stamp("step1");
        let p2 = Payload::new().stamp("step2");
        let merged = p1.merge(&p2);
        assert_eq!(merged.lineage(), &["step1", "step2"]);
    }

    #[test]
    fn merge_preserves_first_trace_id() {
        let p1 = Payload::new().with_trace("trace-1");
        let p2 = Payload::new().with_trace("trace-2");
        assert_eq!(p1.merge(&p2).trace_id(), Some("trace-1"));
    }

    #[test]
    fn merge_uses_other_trace_id_if_none() {
        let p1 = Payload::new();
        let p2 = Payload::new().with_trace("trace-2");
        assert_eq!(p1.merge(&p2).trace_id(), Some("trace-2"));
    }

    #[test]
    fn with_trace_sets_trace_id() {
        let p = Payload::new().with_trace("abc");
        assert_eq!(p.trace_id(), Some("abc"));
    }

    #[test]
    fn stamp_appends_lineage() {
        let p = Payload::new().stamp("a").stamp("b");
        assert_eq!(p.lineage(), &["a", "b"]);
    }

    #[test]
    fn lineage_not_shared() {
        let p1 = Payload::new().stamp("a");
        let p2 = p1.stamp("b");
        assert_eq!(p1.lineage(), &["a"]);
        assert_eq!(p2.lineage(), &["a", "b"]);
    }

    #[test]
    fn with_mutation_converts() {
        let p = Payload::new().insert("x", Value::Int(1)).with_trace("t1");
        let mut mp = p.with_mutation();
        assert_eq!(mp.get("x").unwrap().as_int(), Some(1));
        assert_eq!(mp.trace_id(), Some("t1"));
        mp.set("x", Value::Int(99));
        assert_eq!(mp.get("x").unwrap().as_int(), Some(99));
    }

    #[test]
    fn to_immutable() {
        let mut mp = MutablePayload::new();
        mp.set("x", Value::Int(1));
        let p = mp.to_immutable();
        assert_eq!(p.get("x").unwrap().as_int(), Some(1));
    }

    #[test]
    fn serialize_deserialize_roundtrip() {
        let p = Payload::new()
            .insert("name", Value::Str("test".to_string()))
            .insert("count", Value::Int(42))
            .with_trace("t1")
            .stamp("s1");
        let bytes = p.serialize();
        let restored = Payload::deserialize(&bytes).unwrap();
        assert_eq!(restored.get("name").unwrap().as_str(), Some("test"));
        assert_eq!(restored.get("count").unwrap().as_int(), Some(42));
        assert_eq!(restored.trace_id(), Some("t1"));
        assert_eq!(restored.lineage(), &["s1"]);
    }

    #[test]
    fn display_includes_data() {
        let p = Payload::new().insert("a", Value::Int(1));
        let s = format!("{}", p);
        assert!(s.contains("Payload"));
    }

    #[test]
    fn display_includes_trace() {
        let p = Payload::new().with_trace("abc");
        let s = format!("{}", p);
        assert!(s.contains("abc"));
    }

    #[test]
    fn mutable_payload_display() {
        let mp = MutablePayload::new();
        let s = format!("{}", mp);
        assert!(s.contains("MutablePayload"));
    }

    #[test]
    fn value_from_conversions() {
        assert_eq!(Value::from(42i64), Value::Int(42));
        assert_eq!(Value::from(3.14f64), Value::Float(3.14));
        assert_eq!(Value::from(true), Value::Bool(true));
        assert_eq!(Value::from("hello"), Value::Str("hello".to_string()));
        assert_eq!(Value::from("world".to_string()), Value::Str("world".to_string()));
    }
}
