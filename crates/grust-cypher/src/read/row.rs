//! One candidate solution, as a key-sorted vector.
//!
//! A row holds a handful of bindings and is copied once per expanded candidate.
//! A B-tree allocates a full leaf for even one binding, so a materialized stream
//! of small rows spent most of its time in memory it never used. Iteration is in
//! key order, exactly as the map this replaces iterated.

use super::Bound;

#[derive(Debug, Default)]
pub(super) struct Row<'g> {
    entries: Vec<(String, Bound<'g>)>,
}

impl<'g> Row<'g> {
    pub(super) fn new() -> Self {
        Self::default()
    }

    fn position(&self, name: &str) -> std::result::Result<usize, usize> {
        self.entries
            .binary_search_by(|(key, _)| key.as_str().cmp(name))
    }

    pub(super) fn get(&self, name: &str) -> Option<&Bound<'g>> {
        self.position(name).ok().map(|index| &self.entries[index].1)
    }

    pub(super) fn get_mut(&mut self, name: &str) -> Option<&mut Bound<'g>> {
        self.position(name)
            .ok()
            .map(|index| &mut self.entries[index].1)
    }

    pub(super) fn contains_key(&self, name: &str) -> bool {
        self.position(name).is_ok()
    }

    pub(super) fn insert(&mut self, name: String, bound: Bound<'g>) -> Option<Bound<'g>> {
        match self.position(&name) {
            Ok(index) => Some(std::mem::replace(&mut self.entries[index].1, bound)),
            Err(index) => {
                self.entries.insert(index, (name, bound));
                None
            }
        }
    }

    pub(super) fn len(&self) -> usize {
        self.entries.len()
    }

    pub(super) fn iter(&self) -> impl Iterator<Item = (&String, &Bound<'g>)> {
        self.entries.iter().map(|(name, bound)| (name, bound))
    }

    pub(super) fn keys(&self) -> impl Iterator<Item = &String> {
        self.entries.iter().map(|(name, _)| name)
    }

    pub(super) fn values(&self) -> impl Iterator<Item = &Bound<'g>> {
        self.entries.iter().map(|(_, bound)| bound)
    }
}

impl<'g> FromIterator<(String, Bound<'g>)> for Row<'g> {
    fn from_iter<I: IntoIterator<Item = (String, Bound<'g>)>>(bindings: I) -> Self {
        let bindings = bindings.into_iter();
        let mut row = Self {
            entries: Vec::with_capacity(bindings.size_hint().0),
        };
        for (name, bound) in bindings {
            // Copies arrive in key order, so this appends without searching.
            if row.entries.last().is_none_or(|(last, _)| *last < name) {
                row.entries.push((name, bound));
            } else {
                row.insert(name, bound);
            }
        }
        row
    }
}

impl<'g, const N: usize> From<[(String, Bound<'g>); N]> for Row<'g> {
    fn from(bindings: [(String, Bound<'g>); N]) -> Self {
        bindings.into_iter().collect()
    }
}

impl<'g> IntoIterator for Row<'g> {
    type Item = (String, Bound<'g>);
    type IntoIter = std::vec::IntoIter<(String, Bound<'g>)>;
    fn into_iter(self) -> Self::IntoIter {
        self.entries.into_iter()
    }
}

impl<'a, 'g> IntoIterator for &'a Row<'g> {
    type Item = (&'a String, &'a Bound<'g>);
    type IntoIter = std::iter::Map<
        std::slice::Iter<'a, (String, Bound<'g>)>,
        fn(&'a (String, Bound<'g>)) -> (&'a String, &'a Bound<'g>),
    >;
    fn into_iter(self) -> Self::IntoIter {
        self.entries.iter().map(|(name, bound)| (name, bound))
    }
}
