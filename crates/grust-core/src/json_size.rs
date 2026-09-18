//! Exact compact-JSON byte length without formatting the JSON.
//!
//! Admission limits are stated in serialized bytes, so a bounded reader has to
//! measure a whole graph. Running the `serde_json` formatter through a counting
//! writer formats every integer and copies every string only to add up their
//! lengths. This serializer adds the lengths directly.
//!
//! It mirrors `serde_json`'s compact encoding and nothing else. Floats are
//! delegated to `serde_json` itself, so their text is exact by construction.
//! Anything the mirror does not model — a non-string map key other than the
//! kinds handled below, or `serde_json`'s private number and raw-value
//! encodings — reports [`JsonSizeError::Unsupported`], and the caller measures
//! through the `serde_json` writer instead. A differential test pins the two.

use serde::ser::{self, Serialize};
use std::fmt;

/// Why a measurement did not produce a length.
#[derive(Debug)]
pub enum JsonSizeError {
    /// The sink asked to stop: a limit was exceeded or a deadline passed.
    Stopped,
    /// The value uses an encoding this mirror does not model.
    Unsupported,
    /// A `Serialize` implementation reported an error.
    Message(String),
}

impl fmt::Display for JsonSizeError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::Stopped => f.write_str("measurement stopped by its sink"),
            Self::Unsupported => f.write_str("encoding is not modelled by the size mirror"),
            Self::Message(message) => f.write_str(message),
        }
    }
}

impl std::error::Error for JsonSizeError {}

impl ser::Error for JsonSizeError {
    fn custom<T: fmt::Display>(message: T) -> Self {
        Self::Message(message.to_string())
    }
}

/// Add up the compact JSON encoding of `value`, reporting each run of bytes to
/// `sink`. The sink returns `false` to stop, which yields
/// [`JsonSizeError::Stopped`].
pub fn count_json_bytes<T, F>(value: &T, sink: F) -> Result<(), JsonSizeError>
where
    T: Serialize + ?Sized,
    F: FnMut(usize) -> bool,
{
    let mut counter = Counter { sink };
    value.serialize(&mut counter)
}

/// The compact JSON byte length of `value`, or `None` when it must be measured
/// through the `serde_json` writer instead.
pub fn json_byte_len<T: Serialize + ?Sized>(value: &T) -> Option<usize> {
    let mut total = 0usize;
    count_json_bytes(value, |bytes| match total.checked_add(bytes) {
        Some(next) => {
            total = next;
            true
        }
        None => false,
    })
    .ok()
    .map(|()| total)
}

struct Counter<F> {
    sink: F,
}

type Done = Result<(), JsonSizeError>;

impl<F: FnMut(usize) -> bool> Counter<F> {
    fn add(&mut self, bytes: usize) -> Done {
        if (self.sink)(bytes) {
            Ok(())
        } else {
            Err(JsonSizeError::Stopped)
        }
    }

    fn unsigned(&mut self, mut value: u128) -> Done {
        let mut digits = 1;
        while value >= 10 {
            value /= 10;
            digits += 1;
        }
        self.add(digits)
    }

    fn signed(&mut self, value: i128) -> Done {
        if value < 0 {
            self.add(1)?;
        }
        self.unsigned(value.unsigned_abs())
    }

    /// `serde_json` escapes `"` and `\` and the short control escapes in two
    /// bytes, every other control character as `\u00XX`, and nothing else.
    fn string(&mut self, value: &str) -> Done {
        let escapes: usize = value
            .bytes()
            .map(|byte| match byte {
                b'"' | b'\\' | 0x08 | 0x09 | 0x0A | 0x0C | 0x0D => 1,
                0x00..=0x1F => 5,
                _ => 0,
            })
            .sum();
        self.add(value.len() + escapes + 2)
    }

    /// Floats are formatted by `serde_json` itself, into a length.
    fn float<T: Serialize>(&mut self, value: T) -> Done {
        struct Length(usize);
        impl std::io::Write for Length {
            fn write(&mut self, bytes: &[u8]) -> std::io::Result<usize> {
                self.0 += bytes.len();
                Ok(bytes.len())
            }
            fn flush(&mut self) -> std::io::Result<()> {
                Ok(())
            }
        }
        let mut length = Length(0);
        serde_json::to_writer(&mut length, &value)
            .map_err(|error| JsonSizeError::Message(error.to_string()))?;
        self.add(length.0)
    }
}

/// A sequence or map in progress: a comma precedes every entry but the first,
/// and `close` is the bytes owed once it ends.
struct Compound<'a, F> {
    counter: &'a mut Counter<F>,
    first: bool,
    close: usize,
}

impl<F: FnMut(usize) -> bool> Compound<'_, F> {
    fn separate(&mut self) -> Done {
        if std::mem::replace(&mut self.first, false) {
            Ok(())
        } else {
            self.counter.add(1)
        }
    }

    fn element<T: Serialize + ?Sized>(&mut self, value: &T) -> Done {
        self.separate()?;
        value.serialize(&mut *self.counter)
    }

    fn field<T: Serialize + ?Sized>(&mut self, key: &str, value: &T) -> Done {
        self.separate()?;
        self.counter.string(key)?;
        self.counter.add(1)?;
        value.serialize(&mut *self.counter)
    }

    fn finish(self) -> Done {
        self.counter.add(self.close)
    }
}

impl<'a, F: FnMut(usize) -> bool> ser::Serializer for &'a mut Counter<F> {
    type Ok = ();
    type Error = JsonSizeError;
    type SerializeSeq = Compound<'a, F>;
    type SerializeTuple = Compound<'a, F>;
    type SerializeTupleStruct = Compound<'a, F>;
    type SerializeTupleVariant = Compound<'a, F>;
    type SerializeMap = Compound<'a, F>;
    type SerializeStruct = Compound<'a, F>;
    type SerializeStructVariant = Compound<'a, F>;

    fn serialize_bool(self, value: bool) -> Done {
        self.add(if value { 4 } else { 5 })
    }
    fn serialize_i8(self, value: i8) -> Done {
        self.signed(value.into())
    }
    fn serialize_i16(self, value: i16) -> Done {
        self.signed(value.into())
    }
    fn serialize_i32(self, value: i32) -> Done {
        self.signed(value.into())
    }
    fn serialize_i64(self, value: i64) -> Done {
        self.signed(value.into())
    }
    fn serialize_i128(self, value: i128) -> Done {
        self.signed(value)
    }
    fn serialize_u8(self, value: u8) -> Done {
        self.unsigned(value.into())
    }
    fn serialize_u16(self, value: u16) -> Done {
        self.unsigned(value.into())
    }
    fn serialize_u32(self, value: u32) -> Done {
        self.unsigned(value.into())
    }
    fn serialize_u64(self, value: u64) -> Done {
        self.unsigned(value.into())
    }
    fn serialize_u128(self, value: u128) -> Done {
        self.unsigned(value)
    }
    fn serialize_f32(self, value: f32) -> Done {
        self.float(value)
    }
    fn serialize_f64(self, value: f64) -> Done {
        self.float(value)
    }
    fn serialize_char(self, value: char) -> Done {
        self.string(value.encode_utf8(&mut [0; 4]))
    }
    fn serialize_str(self, value: &str) -> Done {
        self.string(value)
    }
    fn serialize_bytes(self, value: &[u8]) -> Done {
        use ser::SerializeSeq;
        let mut sequence = self.serialize_seq(Some(value.len()))?;
        for byte in value {
            sequence.serialize_element(byte)?;
        }
        sequence.end()
    }
    fn serialize_none(self) -> Done {
        self.add(4)
    }
    fn serialize_some<T: Serialize + ?Sized>(self, value: &T) -> Done {
        value.serialize(self)
    }
    fn serialize_unit(self) -> Done {
        self.add(4)
    }
    fn serialize_unit_struct(self, _name: &'static str) -> Done {
        self.add(4)
    }
    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _index: u32,
        variant: &'static str,
    ) -> Done {
        self.string(variant)
    }
    fn serialize_newtype_struct<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        value: &T,
    ) -> Done {
        value.serialize(self)
    }
    fn serialize_newtype_variant<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        _index: u32,
        variant: &'static str,
        value: &T,
    ) -> Done {
        // {"variant":value}
        self.add(1)?;
        self.string(variant)?;
        self.add(1)?;
        value.serialize(&mut *self)?;
        self.add(1)
    }
    fn serialize_seq(self, _len: Option<usize>) -> Result<Compound<'a, F>, JsonSizeError> {
        self.add(1)?;
        Ok(Compound {
            counter: self,
            first: true,
            close: 1,
        })
    }
    fn serialize_tuple(self, len: usize) -> Result<Compound<'a, F>, JsonSizeError> {
        self.serialize_seq(Some(len))
    }
    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        len: usize,
    ) -> Result<Compound<'a, F>, JsonSizeError> {
        self.serialize_seq(Some(len))
    }
    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _index: u32,
        variant: &'static str,
        _len: usize,
    ) -> Result<Compound<'a, F>, JsonSizeError> {
        // {"variant":[ ... ]}
        self.add(1)?;
        self.string(variant)?;
        self.add(2)?;
        Ok(Compound {
            counter: self,
            first: true,
            close: 2,
        })
    }
    fn serialize_map(self, _len: Option<usize>) -> Result<Compound<'a, F>, JsonSizeError> {
        self.add(1)?;
        Ok(Compound {
            counter: self,
            first: true,
            close: 1,
        })
    }
    fn serialize_struct(
        self,
        name: &'static str,
        len: usize,
    ) -> Result<Compound<'a, F>, JsonSizeError> {
        // `serde_json`'s arbitrary-precision numbers and raw values travel as
        // structs with private names and are not written as objects.
        if name.starts_with("$serde_json::private::") {
            return Err(JsonSizeError::Unsupported);
        }
        self.serialize_map(Some(len))
    }
    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _index: u32,
        variant: &'static str,
        _len: usize,
    ) -> Result<Compound<'a, F>, JsonSizeError> {
        // {"variant":{ ... }}
        self.add(1)?;
        self.string(variant)?;
        self.add(2)?;
        Ok(Compound {
            counter: self,
            first: true,
            close: 2,
        })
    }
}

impl<F: FnMut(usize) -> bool> ser::SerializeSeq for Compound<'_, F> {
    type Ok = ();
    type Error = JsonSizeError;
    fn serialize_element<T: Serialize + ?Sized>(&mut self, value: &T) -> Done {
        self.element(value)
    }
    fn end(self) -> Done {
        self.finish()
    }
}

impl<F: FnMut(usize) -> bool> ser::SerializeTuple for Compound<'_, F> {
    type Ok = ();
    type Error = JsonSizeError;
    fn serialize_element<T: Serialize + ?Sized>(&mut self, value: &T) -> Done {
        self.element(value)
    }
    fn end(self) -> Done {
        self.finish()
    }
}

impl<F: FnMut(usize) -> bool> ser::SerializeTupleStruct for Compound<'_, F> {
    type Ok = ();
    type Error = JsonSizeError;
    fn serialize_field<T: Serialize + ?Sized>(&mut self, value: &T) -> Done {
        self.element(value)
    }
    fn end(self) -> Done {
        self.finish()
    }
}

impl<F: FnMut(usize) -> bool> ser::SerializeTupleVariant for Compound<'_, F> {
    type Ok = ();
    type Error = JsonSizeError;
    fn serialize_field<T: Serialize + ?Sized>(&mut self, value: &T) -> Done {
        self.element(value)
    }
    fn end(self) -> Done {
        self.finish()
    }
}

impl<F: FnMut(usize) -> bool> ser::SerializeMap for Compound<'_, F> {
    type Ok = ();
    type Error = JsonSizeError;
    fn serialize_key<T: Serialize + ?Sized>(&mut self, key: &T) -> Done {
        self.separate()?;
        key.serialize(MapKey {
            counter: &mut *self.counter,
        })
    }
    fn serialize_value<T: Serialize + ?Sized>(&mut self, value: &T) -> Done {
        self.counter.add(1)?;
        value.serialize(&mut *self.counter)
    }
    fn end(self) -> Done {
        self.finish()
    }
}

impl<F: FnMut(usize) -> bool> ser::SerializeStruct for Compound<'_, F> {
    type Ok = ();
    type Error = JsonSizeError;
    fn serialize_field<T: Serialize + ?Sized>(&mut self, key: &'static str, value: &T) -> Done {
        self.field(key, value)
    }
    fn end(self) -> Done {
        self.finish()
    }
}

impl<F: FnMut(usize) -> bool> ser::SerializeStructVariant for Compound<'_, F> {
    type Ok = ();
    type Error = JsonSizeError;
    fn serialize_field<T: Serialize + ?Sized>(&mut self, key: &'static str, value: &T) -> Done {
        self.field(key, value)
    }
    fn end(self) -> Done {
        self.finish()
    }
}

/// JSON object keys are strings. `serde_json` also writes integer keys as
/// quoted digits; every other non-string key is left to `serde_json`.
struct MapKey<'a, F> {
    counter: &'a mut Counter<F>,
}

impl<F: FnMut(usize) -> bool> MapKey<'_, F> {
    fn quoted(self, digits: impl FnOnce(&mut Counter<F>) -> Done) -> Done {
        self.counter.add(2)?;
        digits(self.counter)
    }
}

type Never = ser::Impossible<(), JsonSizeError>;

impl<F: FnMut(usize) -> bool> ser::Serializer for MapKey<'_, F> {
    type Ok = ();
    type Error = JsonSizeError;
    type SerializeSeq = Never;
    type SerializeTuple = Never;
    type SerializeTupleStruct = Never;
    type SerializeTupleVariant = Never;
    type SerializeMap = Never;
    type SerializeStruct = Never;
    type SerializeStructVariant = Never;

    fn serialize_str(self, value: &str) -> Done {
        self.counter.string(value)
    }
    fn serialize_char(self, value: char) -> Done {
        self.counter.string(value.encode_utf8(&mut [0; 4]))
    }
    fn serialize_unit_variant(
        self,
        _name: &'static str,
        _index: u32,
        variant: &'static str,
    ) -> Done {
        self.counter.string(variant)
    }
    fn serialize_newtype_struct<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        value: &T,
    ) -> Done {
        value.serialize(self)
    }
    fn serialize_i8(self, value: i8) -> Done {
        self.quoted(|counter| counter.signed(value.into()))
    }
    fn serialize_i16(self, value: i16) -> Done {
        self.quoted(|counter| counter.signed(value.into()))
    }
    fn serialize_i32(self, value: i32) -> Done {
        self.quoted(|counter| counter.signed(value.into()))
    }
    fn serialize_i64(self, value: i64) -> Done {
        self.quoted(|counter| counter.signed(value.into()))
    }
    fn serialize_i128(self, value: i128) -> Done {
        self.quoted(|counter| counter.signed(value))
    }
    fn serialize_u8(self, value: u8) -> Done {
        self.quoted(|counter| counter.unsigned(value.into()))
    }
    fn serialize_u16(self, value: u16) -> Done {
        self.quoted(|counter| counter.unsigned(value.into()))
    }
    fn serialize_u32(self, value: u32) -> Done {
        self.quoted(|counter| counter.unsigned(value.into()))
    }
    fn serialize_u64(self, value: u64) -> Done {
        self.quoted(|counter| counter.unsigned(value.into()))
    }
    fn serialize_u128(self, value: u128) -> Done {
        self.quoted(|counter| counter.unsigned(value))
    }

    fn serialize_bool(self, _value: bool) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_f32(self, _value: f32) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_f64(self, _value: f64) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_bytes(self, _value: &[u8]) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_none(self) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_some<T: Serialize + ?Sized>(self, _value: &T) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_unit(self) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_unit_struct(self, _name: &'static str) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_newtype_variant<T: Serialize + ?Sized>(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _value: &T,
    ) -> Done {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_seq(self, _len: Option<usize>) -> Result<Never, JsonSizeError> {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_tuple(self, _len: usize) -> Result<Never, JsonSizeError> {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_tuple_struct(
        self,
        _name: &'static str,
        _len: usize,
    ) -> Result<Never, JsonSizeError> {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_tuple_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Never, JsonSizeError> {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_map(self, _len: Option<usize>) -> Result<Never, JsonSizeError> {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_struct(self, _name: &'static str, _len: usize) -> Result<Never, JsonSizeError> {
        Err(JsonSizeError::Unsupported)
    }
    fn serialize_struct_variant(
        self,
        _name: &'static str,
        _index: u32,
        _variant: &'static str,
        _len: usize,
    ) -> Result<Never, JsonSizeError> {
        Err(JsonSizeError::Unsupported)
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::{Edge, Graph, Node, Props, Value};
    use std::collections::BTreeMap;

    fn assert_exact<T: Serialize + ?Sized + fmt::Debug>(value: &T) {
        let expected = serde_json::to_vec(value).unwrap().len();
        assert_eq!(json_byte_len(value), Some(expected), "{value:?}");
    }

    #[test]
    fn scalars_and_strings_match_serde_json() {
        for value in [i64::MIN, -10, -9, -1, 0, 9, 10, 99, 100, i64::MAX] {
            assert_exact(&value);
        }
        for value in [0u64, 9, 10, u64::MAX] {
            assert_exact(&value);
        }
        assert_exact(&u128::MAX);
        assert_exact(&i128::MIN);
        for value in [
            0.0,
            -0.0,
            1.0,
            0.1,
            -2.5e-7,
            1e15,
            1e16,
            1e21,
            1.7976931348623157e308,
            5e-324,
            f64::NAN,
            f64::INFINITY,
        ] {
            assert_exact(&value);
            assert_exact(&(value as f32));
        }
        for value in [
            "",
            "plain",
            "quote\" slash\\ tab\t newline\n return\r backspace\u{8} feed\u{c}",
            "controls \u{0}\u{1}\u{1f} delete \u{7f}",
            "unicode é 漢字 🚀 \u{2028}",
        ] {
            assert_exact(value);
        }
        assert_exact(&'"');
        assert_exact(&'é');
        assert_exact(&true);
        assert_exact(&false);
        assert_exact(&());
        assert_exact(&Option::<i64>::None);
        assert_exact(&Some("x"));
        assert_exact(&(1, "two", 3.5));
        assert_exact(&Vec::<i64>::new());
        assert_exact(&BTreeMap::<String, i64>::new());
        assert_exact(&BTreeMap::from([(-3i64, "a"), (12, "b")]));
        assert_exact(&BTreeMap::from([('k', vec![1u8, 2])]));
    }

    #[derive(Debug, serde::Serialize)]
    enum Shapes {
        Unit,
        Newtype(i64),
        Tuple(i64, String),
        Struct { a: i64, b: Option<String> },
    }

    #[derive(Debug, serde::Serialize)]
    struct Skips {
        kept: i64,
        #[serde(skip_serializing_if = "Option::is_none")]
        skipped: Option<i64>,
        #[serde(flatten)]
        rest: BTreeMap<String, i64>,
    }

    #[test]
    fn enum_and_struct_encodings_match_serde_json() {
        assert_exact(&vec![
            Shapes::Unit,
            Shapes::Newtype(-4),
            Shapes::Tuple(7, "x\"y".into()),
            Shapes::Struct {
                a: 1,
                b: Some("z".into()),
            },
            Shapes::Struct { a: 2, b: None },
        ]);
        assert_exact(&Skips {
            kept: 1,
            skipped: None,
            rest: BTreeMap::from([("extra".into(), 2)]),
        });
    }

    #[test]
    fn every_value_kind_in_a_graph_matches_serde_json() {
        let mut props = Props::new();
        props.insert("null".into(), Value::Null);
        props.insert("bool".into(), Value::Bool(true));
        props.insert("int".into(), Value::Int(-1234567890123));
        props.insert("float".into(), Value::Float(6.02214076e23));
        props.insert("nan".into(), Value::Float(f64::NAN));
        props.insert("string \"quoted\"\n".into(), Value::from("tab\there é"));
        props.insert(
            "strings".into(),
            Value::StringArray(vec!["a".into(), "\\".into()]),
        );
        props.insert("ints".into(), Value::IntArray(vec![i64::MIN, 0, i64::MAX]));
        props.insert("floats".into(), Value::FloatArray(vec![0.5, -1e-9, 3.0]));
        props.insert(
            "json".into(),
            Value::Json(serde_json::json!({
                "nested": [1, 2.5, "x", null, true, {"deep": {"k\u{1}": [[], {}]}}],
                "big": 18446744073709551615u64,
                "negative": -9223372036854775808i64,
            })),
        );
        let graph = Graph::new(
            vec![
                Node::new("Person", "p\"1", props.clone()),
                Node::new("City", "c1", Props::new()),
            ],
            vec![
                Edge::new("KNOWS", "p\"1", "c1", props),
                Edge::new("LIKES", "c1", "p\"1", Props::new()).with_id("e-1"),
            ],
        );
        assert_exact(&graph);
        assert_exact(&graph.nodes[0]);
        assert_exact(&graph.edges[1]);
        assert_exact(&Graph::default());
    }

    #[test]
    fn the_sink_can_stop_a_measurement() {
        let mut seen = 0usize;
        let stopped = count_json_bytes(&vec![1u8; 1024], |bytes| {
            seen += bytes;
            seen < 100
        });
        assert!(matches!(stopped, Err(JsonSizeError::Stopped)));
        assert!((100..110).contains(&seen), "{seen}");
    }

    #[test]
    fn unmodelled_keys_are_reported_not_guessed() {
        assert_eq!(json_byte_len(&BTreeMap::from([(true, 1)])), None);
    }
}
