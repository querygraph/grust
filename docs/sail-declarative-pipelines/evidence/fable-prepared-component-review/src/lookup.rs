//! Spark's `StructType` name-to-index lookup, reproduced for Auto CDC column
//! selection. `nameToIndex` is a Scala immutable map built in schema order,
//! so an exact duplicate overwrites its index; `nameToIndexCaseInsensitive`
//! re-keys that map by `Locale.ROOT` lowercase, so colliding keys are decided
//! by the order the first map's iterator visits them. Scala 2.13.18 keeps up
//! to four distinct keys in insertion order (`Map1`–`Map4`); above that a
//! CHAMP `HashMap` is visited by improved Java `String` hashes: each node's
//! direct payloads in ascending bucket order, then its sub-nodes in ascending
//! bucket order, with full-hash collision leaves in insertion order. Design
//! and bytecode provenance: Grust evidence `fable-lookup-adapter-design`;
//! JVM oracle replayed by the tests: `lookup_oracle.json`.

use std::collections::{BTreeMap, HashMap};

use sail_common::utils::root_lowercase::spark_root_lowercase;

use super::schema::Case;

/// Both lookups of one `StructType`, by field name.
pub(super) struct FieldLookup {
    exact: HashMap<String, usize>,
    insensitive: HashMap<String, usize>,
}

impl FieldLookup {
    pub fn new(fields: &[String]) -> Self {
        // One record per exact spelling, in first-insertion order, holding
        // the last index that spelling was given.
        let mut records: Vec<(&str, usize)> = Vec::new();
        let mut positions: HashMap<&str, usize> = HashMap::new();
        for (index, field) in fields.iter().enumerate() {
            match positions.get(field.as_str()) {
                Some(&position) => records[position].1 = index,
                None => {
                    positions.insert(field, records.len());
                    records.push((field, index));
                }
            }
        }
        let exact = records
            .iter()
            .map(|&(name, index)| (name.to_string(), index))
            .collect();
        let mut insensitive = HashMap::new();
        for (name, index) in scala_map_order(&records) {
            insensitive.insert(spark_root_lowercase(name), index);
        }
        Self { exact, insensitive }
    }

    /// `StructType.getFieldIndex` or `getFieldIndexCaseInsensitive`.
    pub fn resolver(&self, case: Case) -> impl Fn(&str) -> Option<usize> + '_ {
        move |name| match case {
            Case::Sensitive => self.exact.get(name).copied(),
            Case::Insensitive => self.insensitive.get(&spark_root_lowercase(name)).copied(),
        }
    }
}

/// Java `String.hashCode` over UTF-16 units, then Scala `Hashing.improve`;
/// every operation wraps at 32 bits and `>>>` is the logical shift.
pub(super) fn improved_hash(name: &str) -> u32 {
    let mut hash: u32 = 0;
    for unit in name.encode_utf16() {
        hash = hash.wrapping_mul(31).wrapping_add(u32::from(unit));
    }
    let mut improved = hash.wrapping_add(!(hash << 9));
    improved ^= improved >> 14;
    improved = improved.wrapping_add(improved << 4);
    improved ^= improved >> 10;
    improved
}

/// The order Scala's immutable map iterates the records it was built from.
fn scala_map_order<'a>(records: &[(&'a str, usize)]) -> Vec<(&'a str, usize)> {
    if records.len() <= 4 {
        return records.to_vec();
    }
    let hashed: Vec<(u32, &str, usize)> = records
        .iter()
        .map(|&(name, index)| (improved_hash(name), name, index))
        .collect();
    let mut order = Vec::with_capacity(records.len());
    visit_champ_node(&hashed, 0, &mut order);
    order
}

fn visit_champ_node<'a>(
    items: &[(u32, &'a str, usize)],
    shift: u32,
    order: &mut Vec<(&'a str, usize)>,
) {
    if shift >= 32 {
        // Full-hash collision leaf: insertion order.
        order.extend(items.iter().map(|&(_, name, index)| (name, index)));
        return;
    }
    let mut buckets: BTreeMap<u32, Vec<(u32, &str, usize)>> = BTreeMap::new();
    for &item in items {
        buckets
            .entry((item.0 >> shift) & 31)
            .or_default()
            .push(item);
    }
    for group in buckets.values().filter(|group| group.len() == 1) {
        order.push((group[0].1, group[0].2));
    }
    for group in buckets.values().filter(|group| group.len() > 1) {
        visit_champ_node(group, shift + 5, order);
    }
}
