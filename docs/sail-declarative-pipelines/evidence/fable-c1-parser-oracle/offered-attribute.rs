//! Port of Spark's `AttributeNameParser.parseAttributeName` (`sql/api`,
//! 617618396), which the Connect planner applies to every proto
//! `UnresolvedAttribute` through `UnresolvedAttribute.quotedString` before
//! `PipelinesHandler` sees its name parts. Backticks must appear in pairs, a
//! quoted string must be a complete name part, and a backtick may appear only
//! inside a quoted part, doubled. The Auto CDC definition is the only caller;
//! Sail's generic attribute converter keeps its own fallback.

use super::errors;
use crate::error::SparkResult;

pub(super) fn parse_attribute_name(name: &str) -> SparkResult<Vec<String>> {
    // Spark indexes UTF-16 units; only '`' and '.' are compared, and neither is
    // part of a surrogate pair, so iterating scalar values is equivalent.
    let chars: Vec<char> = name.chars().collect();
    let mut parts = Vec::new();
    let mut current = String::new();
    let mut in_backtick = false;
    let mut i = 0;
    while i < chars.len() {
        let char = chars[i];
        if in_backtick {
            if char == '`' {
                if i + 1 < chars.len() && chars[i + 1] == '`' {
                    current.push('`');
                    i += 1;
                } else {
                    in_backtick = false;
                    if i + 1 < chars.len() && chars[i + 1] != '.' {
                        return Err(errors::invalid_attribute_name_syntax(name));
                    }
                }
            } else {
                current.push(char);
            }
        } else if char == '`' {
            if !current.is_empty() {
                return Err(errors::invalid_attribute_name_syntax(name));
            }
            in_backtick = true;
        } else if char == '.' {
            if i == 0 || chars[i - 1] == '.' || i == chars.len() - 1 {
                return Err(errors::invalid_attribute_name_syntax(name));
            }
            parts.push(std::mem::take(&mut current));
        } else {
            current.push(char);
        }
        i += 1;
    }
    if in_backtick {
        return Err(errors::invalid_attribute_name_syntax(name));
    }
    parts.push(current);
    Ok(parts)
}
