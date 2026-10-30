//! `String.toLowerCase(Locale.ROOT)` as OpenJDK 17 computes it, for Spark's
//! `CaseInsensitiveMap` column lookup. This is a different contract from
//! `String.equalsIgnoreCase` ([`super::string::spark_case_insensitive_name_eq`]):
//! `İ` lowercases to two code points, a final capital sigma becomes `ς`, and
//! Java's simple mappings stop at Unicode 13.
//!
//! The scalar mapping is ICU's simple lowercase gated to Unicode 13
//! characters, verified exhaustively against the pinned JVM by hash. The
//! final-sigma rule is `ConditionalSpecialCasing.isFinalCased`: within the
//! word around the sigma, a cased letter before it and none after it, where
//! the word boundaries come from the JDK's own `RuleBasedBreakIterator`. That
//! iterator is ported below over UTF-16 units, including its lookahead and
//! backward tables, its surrogate stepping and its last-known-break cache;
//! its compiled tables live in `root_lowercase_tables.rs`, read from the JVM.
//! `root_lowercase_oracle.json` holds the JVM's answers the tests replay.

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

const GREEK_CAPITAL_SIGMA: u32 = 0x03A3;
const LATIN_CAPITAL_I_WITH_DOT_ABOVE: u32 = 0x0130;

/// Lowercases `name` exactly as `name.toLowerCase(Locale.ROOT)` does on OpenJDK 17.
pub fn spark_root_lowercase(name: &str) -> String {
    let case_mapper = CaseMapper::new();
    let units: Vec<u16> = name.encode_utf16().collect();
    let mut output = String::with_capacity(name.len());
    let mut index = 0;
    while index < units.len() {
        let code_point = code_point_at(&units, index);
        match code_point {
            GREEK_CAPITAL_SIGMA => output.push(if is_final_cased(&units, index) {
                'ς'
            } else {
                'σ'
            }),
            LATIN_CAPITAL_I_WITH_DOT_ABOVE => output.push_str("i\u{307}"),
            _ => {
                // `name` is valid UTF-8, so every code point is a scalar.
                if let Some(char) = char::from_u32(code_point) {
                    let mut buffer = [0; 4];
                    if JDK_17_ASSIGNED_CHARACTER.is_match(char.encode_utf8(&mut buffer)) {
                        output.push(case_mapper.simple_lowercase(char));
                    } else {
                        output.push(char);
                    }
                }
            }
        }
        index += char_count(code_point);
    }
    output
}

/// `ConditionalSpecialCasing.isCased` on this JDK.
fn is_cased(code_point: u32) -> bool {
    tables::CASED_RANGES
        .binary_search_by(|&(start, end)| range_order(start, end, code_point))
        .is_ok()
}

fn range_order(start: u32, end: u32, code_point: u32) -> std::cmp::Ordering {
    if code_point < start {
        std::cmp::Ordering::Greater
    } else if code_point > end {
        std::cmp::Ordering::Less
    } else {
        std::cmp::Ordering::Equal
    }
}

/// `ConditionalSpecialCasing.isFinalCased(src, index, Locale.ROOT)`, with a
/// fresh word iterator per call as the JDK creates one.
fn is_final_cased(units: &[u16], index: usize) -> bool {
    let mut word_boundary = WordBreaker::new(units);
    let mut i = index;
    loop {
        if word_boundary.is_boundary(i) {
            return false;
        }
        let char = code_point_before(units, i);
        if is_cased(char) {
            let mut after = index + char_count(code_point_at(units, index));
            while after < units.len() && !word_boundary.is_boundary(after) {
                let char = code_point_at(units, after);
                if is_cased(char) {
                    return false;
                }
                after += char_count(char);
            }
            return true;
        }
        let Some(previous) = i.checked_sub(char_count(char)) else {
            return false;
        };
        i = previous;
    }
}

fn is_high_surrogate(unit: u32) -> bool {
    (0xD800..=0xDBFF).contains(&unit)
}

fn is_low_surrogate(unit: u32) -> bool {
    (0xDC00..=0xDFFF).contains(&unit)
}

fn to_code_point(high: u32, low: u32) -> u32 {
    0x10000 + ((high - 0xD800) << 10) + (low - 0xDC00)
}

fn char_count(code_point: u32) -> usize {
    if code_point >= 0x10000 { 2 } else { 1 }
}

/// `String.codePointAt(index)`.
fn code_point_at(units: &[u16], index: usize) -> u32 {
    let first = u32::from(units[index]);
    if is_high_surrogate(first)
        && let Some(&second) = units.get(index + 1)
        && is_low_surrogate(u32::from(second))
    {
        return to_code_point(first, u32::from(second));
    }
    first
}

/// `String.codePointBefore(index)`; `index` is at least one.
fn code_point_before(units: &[u16], index: usize) -> u32 {
    let second = u32::from(units[index - 1]);
    if is_low_surrogate(second)
        && index >= 2
        && let first = u32::from(units[index - 2])
        && is_high_surrogate(first)
    {
        return to_code_point(first, second);
    }
    second
}

/// `CharacterIterator.DONE`, which the JDK iterator also treats as a real
/// U+FFFF character would be treated: it ends a scan.
const CHAR_DONE: u32 = 0xFFFF;
/// `BreakIterator.DONE`.
const DONE: i64 = -1;
const START_STATE: usize = 1;
const STOP_STATE: usize = 0;
const IGNORE: i8 = -1;

/// `sun.text.RuleBasedBreakIterator` over a `StringCharacterIterator`,
/// restricted to what `isBoundary` needs.
struct WordBreaker<'a> {
    units: &'a [u16],
    position: usize,
    cached_last_known_break: i64,
}

impl<'a> WordBreaker<'a> {
    fn new(units: &'a [u16]) -> Self {
        Self {
            units,
            position: 0,
            cached_last_known_break: DONE,
        }
    }

    fn end(&self) -> usize {
        self.units.len()
    }

    // `StringCharacterIterator.current`, `next` and `previous`.
    fn unit_current(&self) -> u32 {
        self.units
            .get(self.position)
            .map_or(CHAR_DONE, |&unit| u32::from(unit))
    }

    fn unit_next(&mut self) -> u32 {
        if self.position + 1 < self.end() {
            self.position += 1;
            u32::from(self.units[self.position])
        } else {
            self.position = self.end();
            CHAR_DONE
        }
    }

    fn unit_previous(&mut self) -> u32 {
        if self.position > 0 {
            self.position -= 1;
            u32::from(self.units[self.position])
        } else {
            CHAR_DONE
        }
    }

    /// `getCurrent`.
    fn current(&mut self) -> u32 {
        let first = self.unit_current();
        if is_high_surrogate(first) && self.position < self.end() {
            let second = self.unit_next();
            self.unit_previous();
            if is_low_surrogate(second) {
                return to_code_point(first, second);
            }
        }
        first
    }

    /// `getCurrentCodePointCount`.
    fn current_count(&mut self) -> usize {
        let first = self.unit_current();
        if is_high_surrogate(first) && self.position < self.end() {
            let second = self.unit_next();
            self.unit_previous();
            if is_low_surrogate(second) {
                return 2;
            }
        }
        1
    }

    /// `getNext`: advances one code point, or returns `DONE` without moving
    /// when that would reach the end.
    fn next(&mut self) -> u32 {
        let index = self.position;
        if index == self.end() {
            return CHAR_DONE;
        }
        let advanced = index + self.current_count();
        if advanced >= self.end() {
            return CHAR_DONE;
        }
        self.position = advanced;
        self.current()
    }

    /// `getNextIndex`.
    fn next_index(&mut self) -> usize {
        (self.position + self.current_count()).min(self.end())
    }

    /// `getPrevious`.
    fn previous(&mut self) -> u32 {
        let second = self.unit_previous();
        if is_low_surrogate(second) && self.position > 0 {
            let first = self.unit_previous();
            if is_high_surrogate(first) {
                return to_code_point(first, second);
            }
            self.unit_next();
        }
        second
    }

    fn lookup_category(code_point: u32) -> i8 {
        tables::CATEGORY_RANGES
            .binary_search_by(|&(start, end, _)| range_order(start, end, code_point))
            .ok()
            .map_or(IGNORE, |found| tables::CATEGORY_RANGES[found].2)
    }

    fn lookup_state(table: &[i16], state: usize, category: i8) -> usize {
        let column = usize::try_from(category).unwrap_or(0);
        usize::try_from(table[state * tables::NUM_CATEGORIES + column]).unwrap_or(STOP_STATE)
    }

    /// `handleNext`.
    fn handle_next(&mut self) -> i64 {
        if self.position == self.end() {
            return DONE;
        }
        let mut result = self.next_index();
        let mut lookahead_result = 0;
        let mut state = START_STATE;
        let mut char = self.current();
        while char != CHAR_DONE && state != STOP_STATE {
            let category = Self::lookup_category(char);
            if category != IGNORE {
                state = Self::lookup_state(tables::STATE_TABLE, state, category);
            }
            if tables::LOOKAHEAD_STATES[state] {
                if tables::END_STATES[state] {
                    result = lookahead_result;
                } else {
                    lookahead_result = self.next_index();
                }
            } else if tables::END_STATES[state] {
                result = self.next_index();
            }
            char = self.next();
        }
        if char == CHAR_DONE && lookahead_result == self.end() {
            result = lookahead_result;
        }
        self.position = result;
        i64::try_from(result).unwrap_or(DONE)
    }

    /// `handlePrevious`.
    fn handle_previous(&mut self) -> i64 {
        let mut state = START_STATE;
        let mut category: i8 = 0;
        let mut last_category: i8 = 0;
        let mut char = self.current();
        while char != CHAR_DONE && state != STOP_STATE {
            last_category = category;
            category = Self::lookup_category(char);
            if category != IGNORE {
                state = Self::lookup_state(tables::BACKWARDS_STATE_TABLE, state, category);
            }
            char = self.previous();
        }
        if char != CHAR_DONE {
            if last_category != IGNORE {
                self.next();
                self.next();
            } else {
                self.next();
            }
        }
        i64::try_from(self.position).unwrap_or(DONE)
    }

    /// `following`.
    fn following(&mut self, offset: usize) -> i64 {
        self.position = offset;
        if offset == 0 {
            self.cached_last_known_break = self.handle_next();
            return self.cached_last_known_break;
        }
        let offset_i64 = i64::try_from(offset).unwrap_or(i64::MAX);
        let mut result = self.cached_last_known_break;
        if result >= offset_i64 || result <= DONE {
            result = self.handle_previous();
        } else {
            self.position = usize::try_from(result).unwrap_or(0);
        }
        while result != DONE && result <= offset_i64 {
            result = self.handle_next();
        }
        self.cached_last_known_break = result;
        result
    }

    /// `isBoundary`.
    fn is_boundary(&mut self, offset: usize) -> bool {
        offset == 0 || self.following(offset - 1) == i64::try_from(offset).unwrap_or(DONE)
    }
}

#[cfg(test)]
mod tests {
    use serde::Deserialize;

    use super::spark_root_lowercase;
    use crate::utils::string::spark_case_insensitive_name_eq;

    #[derive(Deserialize)]
    struct Oracle {
        java_runtime_version: String,
        scalar_fnv1a64: String,
        strings: Vec<CodePoints>,
        enumeration_count: usize,
        enumeration_fnv1a64: String,
        random_count: usize,
        random_seed: String,
        random_fnv1a64: String,
        named: Vec<Units>,
    }

    #[derive(Deserialize)]
    struct CodePoints {
        input: Vec<u32>,
        lower: Vec<u32>,
    }

    #[derive(Deserialize)]
    struct Units {
        input: Vec<u16>,
        lower: Vec<u16>,
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

    /// 64-bit FNV-1a over each output's UTF-8 followed by a zero byte, as the probes hash.
    struct Fnv(u64);

    impl Fnv {
        fn new() -> Self {
            Self(0xcbf29ce484222325)
        }

        fn feed(&mut self, output: &str) {
            for byte in output.bytes().chain(std::iter::once(0)) {
                self.0 ^= u64::from(byte);
                self.0 = self.0.wrapping_mul(0x100000001b3);
            }
        }

        fn hex(&self) -> String {
            format!("{:x}", self.0)
        }
    }

    #[test]
    fn every_scalar_lowercases_as_on_the_pinned_jvm() {
        let oracle = oracle();
        assert!(oracle.java_runtime_version.starts_with("17.0.8"));
        let mut hash = Fnv::new();
        for code in 0..=0x10FFFF_u32 {
            if let Some(char) = char::from_u32(code) {
                hash.feed(&spark_root_lowercase(&char.to_string()));
            }
        }
        assert_eq!(hash.hex(), oracle.scalar_fnv1a64);
    }

    #[test]
    fn designed_context_strings_match_the_pinned_jvm() {
        let oracle = oracle();
        assert!(oracle.strings.len() >= 200);
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
    fn reviewed_counterexamples_match_the_pinned_jvm() {
        // Marks and format characters after a digit belong to the number, so
        // a following connector and sigma start a new word (Codex, CF-0019).
        let oracle = oracle();
        assert!(oracle.named.len() >= 10);
        for case in &oracle.named {
            let input = String::from_utf16_lossy(&case.input);
            assert_eq!(
                spark_root_lowercase(&input),
                String::from_utf16_lossy(&case.lower),
                "JDK 17 ROOT lowercase of {input:?}"
            );
        }
    }

    #[test]
    fn review_enumeration_set_matches_the_pinned_jvm() {
        // Every suffix of length zero to five over A, 1, dot, apostrophe,
        // underscore, combining acute and ZWJ, in `AΣ`+suffix and
        // `A`+suffix+`Σ` frames, deduplicated in order: the set of the
        // independent context review.
        let oracle = oracle();
        let symbols = ['A', '1', '.', '\'', '_', '\u{301}', '\u{200D}'];
        let mut seen = std::collections::HashSet::new();
        let mut hash = Fnv::new();
        let mut count = 0;
        for length in 0..=5 {
            let total = symbols.len().pow(length);
            for ordinal in 0..total {
                let mut digits = vec![0; length as usize];
                let mut value = ordinal;
                for digit in digits.iter_mut().rev() {
                    *digit = value % symbols.len();
                    value /= symbols.len();
                }
                let suffix: String = digits.iter().map(|&d| symbols[d]).collect();
                for input in [format!("AΣ{suffix}"), format!("A{suffix}Σ")] {
                    if seen.insert(input.clone()) {
                        hash.feed(&spark_root_lowercase(&input));
                        count += 1;
                    }
                }
            }
        }
        assert_eq!(count, oracle.enumeration_count);
        assert_eq!(hash.hex(), oracle.enumeration_fnv1a64);
    }

    #[test]
    fn seeded_random_context_strings_match_the_pinned_jvm() {
        // xorshift64* with the fixture's seed over the probe's alphabet,
        // lengths one to eight; the JVM hashed the same sequence.
        const ALPHABET: [u32; 62] = [
            0x41, 0x61, 0x31, 0x2E, 0x27, 0x5F, 0x2D, 0x22, 0x2C, 0x3A, 0x20, 0x09, 0x0A, 0x2019,
            0x2018, 0x00B7, 0x2027, 0x066B, 0x0301, 0x0345, 0x037A, 0x200D, 0x200C, 0x00AD, 0x200B,
            0x2060, 0xFE0F, 0x0391, 0x03A3, 0x03C3, 0x03C2, 0x03B1, 0x0130, 0x0131, 0x0049, 0x0069,
            0x02B0, 0x02C0, 0x02E0, 0x1D2C, 0x2160, 0x2170, 0x24B6, 0x24D0, 0x00B2, 0x0660, 0x1C90,
            0x10D0, 0x10400, 0x10428, 0x10570, 0x10597, 0x1C89, 0x1C8A, 0x3042, 0x30A2, 0x4E00,
            0xFF21, 0xFF41, 0xFF10, 0xFFFF, 0xFFFE,
        ];
        let oracle = oracle();
        let mut state = u64::from_str_radix(&oracle.random_seed, 16).unwrap_or_default();
        let mut step = || {
            state ^= state >> 12;
            state ^= state << 25;
            state ^= state >> 27;
            state.wrapping_mul(0x2545F4914F6CDD1D)
        };
        let mut hash = Fnv::new();
        for _ in 0..oracle.random_count {
            let length = 1 + usize::try_from(step() % 8).unwrap_or(0);
            let input: String = (0..length)
                .filter_map(|_| {
                    let pick = usize::try_from(step() % ALPHABET.len() as u64).unwrap_or(0);
                    char::from_u32(ALPHABET[pick])
                })
                .collect();
            hash.feed(&spark_root_lowercase(&input));
        }
        assert_eq!(hash.hex(), oracle.random_fnv1a64);
    }

    /// Opt-in replay of an external JVM corpus (Grust evidence
    /// fable-c2-corrected-review: 68,588 strings, too large to embed). Set
    /// SAIL_FABLE_LOWERCASE_CORPUS to a JSON `{cases: [{input, lower}]}`.
    #[test]
    fn optional_external_jvm_corpus_replays_against_the_helper() {
        #[derive(Deserialize)]
        struct Corpus {
            cases: Vec<External>,
        }
        #[derive(Deserialize)]
        struct External {
            input: String,
            lower: String,
        }
        let Ok(path) = std::env::var("SAIL_FABLE_LOWERCASE_CORPUS") else {
            eprintln!("SAIL_FABLE_LOWERCASE_CORPUS unset; external corpus replay skipped");
            return;
        };
        let text = std::fs::read_to_string(&path).unwrap_or_default();
        let Ok(corpus) = serde_json::from_str::<Corpus>(&text) else {
            eprintln!("could not parse {path}");
            return;
        };
        let mut mismatches = 0;
        for case in &corpus.cases {
            if spark_root_lowercase(&case.input) != case.lower {
                mismatches += 1;
                if mismatches <= 5 {
                    eprintln!("mismatch for {:?}", case.input);
                }
            }
        }
        eprintln!(
            "external corpus: {} strings, {mismatches} mismatches",
            corpus.cases.len()
        );
        assert_eq!(mismatches, 0);
        assert!(!corpus.cases.is_empty());
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
