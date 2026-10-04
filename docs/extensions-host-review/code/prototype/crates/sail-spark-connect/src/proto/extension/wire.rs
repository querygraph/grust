//! Bounded raw protobuf traversal before prost decodes embedded input plans.
//!
//! The workspace enables prost's `no-recursion-limit`, so its generated decoder
//! cannot protect this boundary. Visit only descriptor-declared message fields;
//! arbitrary strings, Arrow IPC and extension-specific payloads remain opaque.
//! Sail envelopes inside Any.value are traversed before any recursive decoding.

use std::collections::BTreeMap;
use std::sync::LazyLock;

use prost::Message;
use prost::encoding::{WireType, decode_key, decode_varint};
use prost_types::field_descriptor_proto::Type;
use prost_types::{DescriptorProto, FileDescriptorSet};

use crate::error::{SparkError, SparkResult};
use crate::spark::connect::FILE_DESCRIPTOR_SET;

const ENVELOPE_MESSAGE: &str = ".sail.extension.v1.SailExtensionRequest";

type MessageFields = BTreeMap<String, BTreeMap<u32, String>>;

static MESSAGE_FIELDS: LazyLock<Result<MessageFields, String>> = LazyLock::new(|| {
    // This is build-generated, trusted data, never a descriptor from a request.
    let descriptors = FileDescriptorSet::decode(FILE_DESCRIPTOR_SET).map_err(|e| e.to_string())?;
    let mut messages = BTreeMap::new();
    for file in descriptors.file {
        let prefix = format!(".{}", file.package.as_deref().unwrap_or_default());
        for message in file.message_type {
            register_message(&mut messages, &prefix, message)?;
        }
    }
    messages.insert(
        ENVELOPE_MESSAGE.into(),
        BTreeMap::from([(3, ".spark.connect.Plan".into())]),
    );
    Ok(messages)
});

fn register_message(
    messages: &mut MessageFields,
    prefix: &str,
    message: DescriptorProto,
) -> Result<(), String> {
    let name = message.name.ok_or("protobuf descriptor without a name")?;
    let name = format!("{prefix}.{name}");
    let mut fields = BTreeMap::new();
    for field in message.field {
        if field.r#type == Some(Type::Message as i32) {
            let number = field.number.ok_or("protobuf field without a number")?;
            let number = u32::try_from(number).map_err(|e| e.to_string())?;
            let target = field
                .type_name
                .ok_or("protobuf message field without a type")?;
            fields.insert(number, target);
        }
    }
    messages.insert(name.clone(), fields);
    for nested in message.nested_type {
        register_message(messages, &name, nested)?;
    }
    Ok(())
}

/// Read one field without recursion or allocation. Groups are not part of the
/// proto3 extension contract and are rejected even when their tag is unknown.
pub(super) fn next_field<'a>(bytes: &mut &'a [u8]) -> SparkResult<(u32, WireType, &'a [u8])> {
    let (tag, wire_type) = decode_key(bytes)?;
    let length = match wire_type {
        WireType::Varint => {
            decode_varint(bytes)?;
            0
        }
        WireType::ThirtyTwoBit => 4,
        WireType::SixtyFourBit => 8,
        WireType::LengthDelimited => usize::try_from(decode_varint(bytes)?)
            .map_err(|_| SparkError::invalid("extension protobuf field length overflow"))?,
        WireType::StartGroup | WireType::EndGroup => {
            return Err(SparkError::invalid(
                "protobuf groups are not supported in extension input plans",
            ));
        }
    };
    if length > bytes.len() {
        return Err(SparkError::invalid("truncated extension protobuf field"));
    }
    let (value, rest) = bytes.split_at(length);
    *bytes = rest;
    Ok((tag, wire_type, value))
}

pub(super) fn validate_plan(bytes: &[u8], max_depth: usize) -> SparkResult<()> {
    let messages = MESSAGE_FIELDS
        .as_ref()
        .map_err(|e| SparkError::internal(format!("invalid Spark protocol descriptor: {e}")))?;
    // Depth-first iteration retains at most one unfinished message per level,
    // rather than allocating an entry for every repeated field in the request.
    let mut stack = vec![(".spark.connect.Plan", bytes, 0usize)];
    while let Some((message, mut remaining, depth)) = stack.pop() {
        if depth >= max_depth {
            return Err(SparkError::invalid(format!(
                "Sail extension input nesting exceeds the remaining {max_depth} protobuf levels"
            )));
        }
        if message == ".google.protobuf.Any" {
            let mut type_url = &[][..];
            let mut value = &[][..];
            while !remaining.is_empty() {
                let (tag, wire_type, field) = next_field(&mut remaining)?;
                if matches!(tag, 1 | 2) && wire_type != WireType::LengthDelimited {
                    return Err(SparkError::invalid(
                        "invalid wire type for extension Any field",
                    ));
                }
                match tag {
                    1 => type_url = field,
                    2 => value = field,
                    _ => {}
                }
            }
            if type_url == super::ENVELOPE_TYPE_URL.as_bytes() {
                if value.len() > super::MAX_ENVELOPE_BYTES {
                    return Err(SparkError::invalid("Sail extension envelope exceeds 8 MiB"));
                }
                super::preflight_envelope(value)?;
                stack.push((ENVELOPE_MESSAGE, value, depth + 1));
            }
            continue;
        }
        let fields = messages.get(message).ok_or_else(|| {
            SparkError::internal(format!("missing Spark protocol descriptor for {message}"))
        })?;
        while !remaining.is_empty() {
            let (tag, wire_type, value) = next_field(&mut remaining)?;
            if let Some(child) = fields.get(&tag) {
                if wire_type != WireType::LengthDelimited {
                    return Err(SparkError::invalid(format!(
                        "invalid protobuf wire type for message field {message}:{tag}"
                    )));
                }
                if !remaining.is_empty() {
                    stack.push((message, remaining, depth));
                }
                stack.push((child.as_str(), value, depth + 1));
                break;
            }
        }
    }
    Ok(())
}
