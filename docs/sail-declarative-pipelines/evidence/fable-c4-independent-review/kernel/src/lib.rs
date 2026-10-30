//! Column-name selection and reservation checks, without schemas, engines,
//! runtimes, or a name-resolution policy of their own.
//!
//! Extracted for Sail's declarative pipelines, where Spark's Auto CDC
//! arguments select, require and reserve columns by name under the session's
//! `spark.sql.caseSensitive` setting. Each function mirrors one Spark
//! primitive, so callers can port Spark assertions one to one:
//!
//! - [`select`] is `ColumnSelection.applyToSchema`, returning indices.
//! - [`reserved`] and [`unresolved`] are the reserved-prefix and
//!   keys-present checks on `AutoCdcMergeFlow`.
//!
//! Selection resolves names through a caller-supplied resolver,
//! `resolve(name) -> Option<index>`, because the engine owns the lookup policy:
//! Spark's `StructType` resolves through a name-to-index map whose duplicate
//! and case-collision behavior is the map's, not a search over the field
//! list. The reserved-prefix and required-name checks take a pairwise
//! comparator, `matches(field, name)`, as Spark's analysis `Resolver` does.
//! This crate carries no case folding of its own; [`exact`] is the
//! case-sensitive comparator.

/// Case-sensitive name equality: Spark's `caseSensitiveResolution`.
pub fn exact(left: &str, right: &str) -> bool {
    left == right
}

/// Which named columns a selection keeps.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Selection<'a, N> {
    /// Keep only these columns. An empty list keeps nothing.
    Include(&'a [N]),
    /// Keep every column except these. An empty list keeps everything.
    Exclude(&'a [N]),
}

/// Selection names that resolve to no field: distinct, in request order,
/// spelled as the caller wrote them.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct Unresolved {
    pub names: Vec<String>,
}

/// `ColumnSelection.applyToSchema`: the indices, among `field_count` fields,
/// that a selection retains, in field order. Each name is resolved once with
/// `resolve`; several names resolving to one field keep it once. If any name
/// resolves to nothing, every such name is reported and nothing is selected.
/// An index at or beyond `field_count` breaks the resolver's contract and is
/// reported as unresolved rather than selected.
pub fn select<N, R>(
    field_count: usize,
    selection: Selection<'_, N>,
    resolve: R,
) -> Result<Vec<usize>, Unresolved>
where
    N: AsRef<str>,
    R: Fn(&str) -> Option<usize>,
{
    let (names, keep_matched) = match selection {
        Selection::Include(names) => (names, true),
        Selection::Exclude(names) => (names, false),
    };
    let mut matched = vec![false; field_count];
    let mut missing: Vec<String> = Vec::new();
    for name in names {
        match resolve(name.as_ref()).and_then(|index| matched.get_mut(index)) {
            Some(hit) => *hit = true,
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
