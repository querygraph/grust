//! `String.toLowerCase(Locale.ROOT)` as OpenJDK 17 computes it, for Spark's
//! `CaseInsensitiveMap` column lookup. This is a different contract from
//! `String.equalsIgnoreCase` ([`super::string::spark_case_insensitive_name_eq`]):
//! `İ` lowercases to two code points, a final capital sigma becomes `ς`, and
//! Java's simple mappings stop at Unicode 13.
//!
//! The scalar mapping is ICU's simple lowercase gated to Unicode 13 characters,
//! verified exhaustively against the pinned JVM by hash. The final-sigma rule
//! follows `ConditionalSpecialCasing.isFinalCased`: a cased letter before the
//! sigma and none after it, within the word boundaries of the JDK's own word
//! `BreakIterator`. Those boundaries are not UAX #29; the classes in
//! `root_lowercase_tables.rs` were observed from the JVM one neighbour at a
//! time, and the designed multi-character strings in
//! `root_lowercase_oracle.json` are the acceptance set for their combination.

use std::sync::LazyLock;

use icu_casemap::CaseMapper;
use regex::Regex;

#[path = "root_lowercase_tables.rs"]
mod tables;

// OpenJDK 17 uses Unicode 13, so newer characters keep identity mappings.
#[expect(clippy::expect_used)]
static JDK_17_ASSIGNED_CHARACTER: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(r"^\p{Age:13.0}$").expect("JDK 17 Unicode age pattern should be valid")
});

/// Lowercases `name` exactly as `name.toLowerCase(Locale.ROOT)` does on OpenJDK 17.
pub fn spark_root_lowercase(name: &str) -> String {
    let case_mapper = CaseMapper::new();
    let chars: Vec<char> = name.chars().collect();
    let mut output = String::with_capacity(name.len());
    for (index, &char) in chars.iter().enumerate() {
        match char {
            'Σ' => output.push(if is_final_cased(&chars, index) {
                'ς'
            } else {
                'σ'
            }),
            'İ' => output.push_str("i\u{307}"),
            _ => {
                let mut buffer = [0; 4];
                if JDK_17_ASSIGNED_CHARACTER.is_match(char.encode_utf8(&mut buffer)) {
                    output.push(case_mapper.simple_lowercase(char));
                } else {
                    output.push(char);
                }
            }
        }
    }
    output
}

fn contains(table: &[(u32, u32)], char: char) -> bool {
    let code = u32::from(char);
    table
        .binary_search_by(|&(start, end)| {
            if code < start {
                std::cmp::Ordering::Greater
            } else if code > end {
                std::cmp::Ordering::Less
            } else {
                std::cmp::Ordering::Equal
            }
        })
        .is_ok()
}

/// A connector (`.`, `-`, `'`, `_`, ...) stays inside a word only between two
/// letters, or, for the number connectors (`.`, `,`, `'`, ...), between two digits.
fn connector_inside_word(chars: &[char], index: usize) -> bool {
    let (Some(&before), Some(&after)) = (
        index.checked_sub(1).and_then(|i| chars.get(i)),
        chars.get(index + 1),
    ) else {
        return false;
    };
    let char = chars[index];
    (contains(tables::CONNECTORS, char)
        && contains(tables::LETTER_BEFORE, before)
        && contains(tables::LETTER_AFTER, after))
        || (contains(tables::NUMBER_CONNECTORS, char)
            && contains(tables::NUMBER_BEFORE, before)
            && contains(tables::NUMBER_AFTER, after))
}

fn is_connector(char: char) -> bool {
    contains(tables::CONNECTORS, char) || contains(tables::NUMBER_CONNECTORS, char)
}

/// `ConditionalSpecialCasing.isFinalCased`: within the word around the sigma at
/// `index`, a cased letter precedes it and no cased letter follows it.
fn is_final_cased(chars: &[char], index: usize) -> bool {
    let mut preceded = false;
    let mut j = index;
    while j > 0 {
        j -= 1;
        let char = chars[j];
        if is_connector(char) {
            if connector_inside_word(chars, j) {
                continue;
            }
            return false;
        }
        if contains(tables::CASED_BEFORE, char) {
            preceded = true;
            break;
        }
        if contains(tables::WORD_BEFORE, char) {
            continue;
        }
        return false;
    }
    if !preceded {
        return false;
    }
    for k in index + 1..chars.len() {
        let char = chars[k];
        if is_connector(char) {
            if connector_inside_word(chars, k) {
                continue;
            }
            return true;
        }
        if contains(tables::CASED_AFTER, char) {
            return false;
        }
        if contains(tables::WORD_AFTER, char) {
            continue;
        }
        return true;
    }
    true
}

#[cfg(test)]
mod tests {
    use serde::Deserialize;

    use super::{spark_root_lowercase, tables};
    use crate::utils::string::spark_case_insensitive_name_eq;

    #[derive(Deserialize)]
    struct Oracle {
        java_runtime_version: String,
        scalar_fnv1a64: String,
        strings: Vec<Case>,
    }

    #[derive(Deserialize)]
    struct Case {
        input: Vec<u32>,
        lower: Vec<u32>,
    }

    fn oracle() -> Oracle {
        #[expect(clippy::expect_used)]
        serde_json::from_str(include_str!("root_lowercase_oracle.json"))
            .expect("the JDK oracle fixture should parse")
    }

    fn text(code_points: &[u32]) -> String {
        code_points
            .iter()
            .filter_map(|&c| char::from_u32(c))
            .collect()
    }

    #[test]
    fn every_scalar_lowercases_as_on_the_pinned_jvm() {
        // The JVM hashed `String.toLowerCase(Locale.ROOT)` of every scalar in
        // order, each followed by a zero byte, with 64-bit FNV-1a.
        let oracle = oracle();
        assert!(oracle.java_runtime_version.starts_with("17.0.8"));
        let mut hash: u64 = 0xcbf29ce484222325;
        let mut feed = |bytes: &[u8]| {
            for &byte in bytes {
                hash ^= u64::from(byte);
                hash = hash.wrapping_mul(0x100000001b3);
            }
        };
        for code in 0..=0x10FFFF_u32 {
            let Some(char) = char::from_u32(code) else {
                continue;
            };
            feed(spark_root_lowercase(&char.to_string()).as_bytes());
            feed(&[0]);
        }
        assert_eq!(format!("{hash:x}"), oracle.scalar_fnv1a64);
        assert_eq!(hash, tables::SCALAR_FNV1A64);
    }

    #[test]
    fn designed_context_strings_match_the_pinned_jvm() {
        let oracle = oracle();
        assert!(oracle.strings.len() >= 150);
        for case in &oracle.strings {
            let input = text(&case.input);
            assert_eq!(
                spark_root_lowercase(&input),
                text(&case.lower),
                "JDK 17 ROOT lowercase of {input:?}"
            );
        }
    }

    #[test]
    fn lookup_lowercase_and_resolver_equality_are_different_contracts() {
        // Spark's case-insensitive column lookup compares ROOT-lowercased names;
        // its resolver compares with `equalsIgnoreCase`. They disagree here.
        for (left, right, lookup_equal, resolver_equal) in [
            ("İ", "i", false, true),
            ("I", "ı", false, true),
            ("Σ", "ς", false, true),
            ("ΟΔΟΣ", "οδοσ", false, true),
            ("ΟΔΟΣ", "οδος", true, true),
            ("\u{10570}", "\u{10597}", false, false),
            ("\u{1C89}", "\u{1C8A}", false, false),
            ("É", "é", true, true),
            ("Name", "NAME", true, true),
        ] {
            assert_eq!(
                spark_root_lowercase(left) == spark_root_lowercase(right),
                lookup_equal,
                "lookup equality of {left:?} and {right:?}"
            );
            assert_eq!(
                spark_case_insensitive_name_eq(left, right),
                resolver_equal,
                "resolver equality of {left:?} and {right:?}"
            );
        }
    }
}
