//! Column-name selection and reservation checks, without schemas, engines,
//! runtimes, or a case-folding policy of their own.
//!
//! Extracted for Sail's declarative pipelines, where Spark's Auto CDC
//! arguments select, require and reserve columns by name under the session's
//! `spark.sql.caseSensitive` setting. Each function mirrors one Spark
//! primitive, so callers can port Spark assertions one to one:
//!
//! - [`field_index`] is `StructType.getFieldIndex` or
//!   `getFieldIndexCaseInsensitive`.
//! - [`select`] is `ColumnSelection.applyToSchema`, returning indices.
//! - [`reserved`] and [`unresolved`] are the reserved-prefix and
//!   keys-present checks on `AutoCdcMergeFlow`.
//!
//! Name equality is supplied by the caller as `matches(field, name)`, so the
//! engine keeps its own Spark-parity comparator (Sail's
//! `spark_case_insensitive_name_eq`, or the lower-cased lookup of Spark's
//! `CaseInsensitiveMap`) and this crate carries no second Unicode
//! implementation. [`exact`] is the case-sensitive comparator.
//!
//! Field names are unique within a schema by contract. A duplicate name
//! resolves to its first occurrence; nothing here diagnoses duplicates.

/// Case-sensitive name equality: Spark's `caseSensitiveResolution`.
pub fn exact(left: &str, right: &str) -> bool {
    left == right
}

/// `StructType.getFieldIndex` or `getFieldIndexCaseInsensitive`: the first
/// field that `matches` `name`.
pub fn field_index<S, M>(fields: &[S], name: &str, matches: M) -> Option<usize>
where
    S: AsRef<str>,
    M: Fn(&str, &str) -> bool,
{
    fields
        .iter()
        .position(|field| matches(field.as_ref(), name))
}

/// Which named columns a selection keeps.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Selection<'a, N> {
    /// Keep only these columns. An empty list keeps nothing.
    Include(&'a [N]),
    /// Keep every column except these. An empty list keeps everything.
    Exclude(&'a [N]),
}

/// Selection names that match no field: distinct, in request order, spelled
/// as the caller wrote them.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Unresolved {
    pub names: Vec<String>,
}

/// `ColumnSelection.applyToSchema`: the indices of the fields a selection
/// retains, in field order. Several names that match the same field keep it
/// once. If any name matches no field, every such name is reported and
/// nothing is selected.
pub fn select<S, N, M>(
    fields: &[S],
    selection: Selection<'_, N>,
    matches: M,
) -> Result<Vec<usize>, Unresolved>
where
    S: AsRef<str>,
    N: AsRef<str>,
    M: Fn(&str, &str) -> bool,
{
    let (names, keep_matched) = match selection {
        Selection::Include(names) => (names, true),
        Selection::Exclude(names) => (names, false),
    };
    let mut matched = vec![false; fields.len()];
    let mut missing: Vec<String> = Vec::new();
    for name in names {
        match field_index(fields, name.as_ref(), &matches) {
            Some(index) => matched[index] = true,
            None => {
                if !missing.iter().any(|seen| seen == name.as_ref()) {
                    missing.push(name.as_ref().to_string());
                }
            }
        }
    }
    if !missing.is_empty() {
        return Err(Unresolved { names: missing });
    }
    Ok(matched
        .into_iter()
        .enumerate()
        .filter(|(_, hit)| *hit == keep_matched)
        .map(|(index, _)| index)
        .collect())
}

/// The first field whose leading characters match `prefix`, as
/// `AutoCdcMergeFlow.requireReservedPrefixAbsentInSourceColumns` finds a
/// reserved column. The prefix is taken by character count; a field shorter
/// than the prefix never matches.
pub fn reserved<S, M>(fields: &[S], prefix: &str, matches: M) -> Option<usize>
where
    S: AsRef<str>,
    M: Fn(&str, &str) -> bool,
{
    let width = prefix.chars().count();
    fields.iter().position(|field| {
        let head: String = field.as_ref().chars().take(width).collect();
        head.chars().count() == width && matches(&head, prefix)
    })
}

/// The index of the first `names` entry that matches no field, as
/// `AutoCdcMergeFlow.requireKeysPresentInSelectedSchema` finds a missing key.
pub fn unresolved<S, N, M>(fields: &[S], names: &[N], matches: M) -> Option<usize>
where
    S: AsRef<str>,
    N: AsRef<str>,
    M: Fn(&str, &str) -> bool,
{
    names.iter().position(|name| {
        !fields
            .iter()
            .any(|field| matches(field.as_ref(), name.as_ref()))
    })
}

#[cfg(test)]
mod tests;
