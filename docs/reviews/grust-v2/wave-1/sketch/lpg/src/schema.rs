//! The in-memory schema, its builder (the "set" accessors), and validation.

use crate::types::{Constraint, Direction, Property};
use crate::{EdgeGroup, EpgId, Lpg, VertexGroup, VpgId};

#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct VertexGroupDef {
    pub id: VpgId,
    pub name: String,
    pub labels: Vec<String>,
    pub properties: Vec<Property>,
    pub key: Vec<String>,
    pub constraints: Vec<Constraint>,
}

#[derive(Clone, Debug, PartialEq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct EdgeGroupDef {
    pub id: EpgId,
    pub name: String,
    pub edge_type: String,
    pub source: VpgId,
    pub target: VpgId,
    pub direction: Direction,
    pub properties: Vec<Property>,
    pub source_key: Vec<String>,
    pub target_key: Vec<String>,
    pub constraints: Vec<Constraint>,
}

impl VertexGroup for VertexGroupDef {
    fn id(&self) -> VpgId {
        self.id
    }
    fn name(&self) -> &str {
        &self.name
    }
    fn labels(&self) -> &[String] {
        &self.labels
    }
    fn properties(&self) -> &[Property] {
        &self.properties
    }
    fn key(&self) -> &[String] {
        &self.key
    }
    fn constraints(&self) -> &[Constraint] {
        &self.constraints
    }
}

impl EdgeGroup for EdgeGroupDef {
    fn id(&self) -> EpgId {
        self.id
    }
    fn name(&self) -> &str {
        &self.name
    }
    fn edge_type(&self) -> &str {
        &self.edge_type
    }
    fn source(&self) -> VpgId {
        self.source
    }
    fn target(&self) -> VpgId {
        self.target
    }
    fn direction(&self) -> Direction {
        self.direction
    }
    fn properties(&self) -> &[Property] {
        &self.properties
    }
    fn source_key(&self) -> &[String] {
        &self.source_key
    }
    fn target_key(&self) -> &[String] {
        &self.target_key
    }
    fn constraints(&self) -> &[Constraint] {
        &self.constraints
    }
}

/// An immutable, validated schema. Build it with [`SchemaBuilder`].
#[derive(Clone, Debug, PartialEq, Default)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Schema {
    vertices: Vec<VertexGroupDef>,
    edges: Vec<EdgeGroupDef>,
}

impl Lpg for Schema {
    type Vertex = VertexGroupDef;
    type Edge = EdgeGroupDef;
    fn vertex_groups(&self) -> &[VertexGroupDef] {
        &self.vertices
    }
    fn edge_groups(&self) -> &[EdgeGroupDef] {
        &self.edges
    }
    // Ids are positions here, so lookups are O(1).
    fn vertex(&self, id: VpgId) -> Option<&VertexGroupDef> {
        self.vertices.get(id.0 as usize)
    }
    fn edge(&self, id: EpgId) -> Option<&EdgeGroupDef> {
        self.edges.get(id.0 as usize)
    }
}

impl Schema {
    pub fn builder() -> SchemaBuilder {
        SchemaBuilder::default()
    }
    /// Back to a builder, to change a schema ("set" on an immutable value).
    pub fn to_builder(&self) -> SchemaBuilder {
        SchemaBuilder {
            vertices: self.vertices.clone(),
            edges: self.edges.clone(),
        }
    }
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub enum LpgError {
    TooManyGroups,
    DuplicateName(String),
    UnknownGroup(String),
    EmptyKey(String),
    UnknownProperty { group: String, property: String },
    NullableKey { group: String, property: String },
    KeyArity { edge_group: String },
}

/// Mutable form of a schema. Groups are referred to by name until [`build`](Self::build).
#[derive(Clone, Debug, Default)]
pub struct SchemaBuilder {
    vertices: Vec<VertexGroupDef>,
    edges: Vec<EdgeGroupDef>,
}

impl SchemaBuilder {
    /// Add a vertex group. Its id is its position.
    pub fn vertex_group(
        mut self,
        name: &str,
        labels: &[&str],
        properties: Vec<Property>,
        key: &[&str],
    ) -> Self {
        let id = VpgId(self.vertices.len().min(u16::MAX as usize) as u16);
        self.vertices.push(VertexGroupDef {
            id,
            name: name.into(),
            labels: labels.iter().map(|l| l.to_string()).collect(),
            properties,
            key: key.iter().map(|k| k.to_string()).collect(),
            constraints: Vec::new(),
        });
        self
    }

    /// Add an edge group between two vertex groups named earlier. The edge rows'
    /// key columns default to `src_<key>` and `dst_<key>`.
    pub fn edge_group(
        mut self,
        name: &str,
        edge_type: &str,
        source: &str,
        target: &str,
        direction: Direction,
        properties: Vec<Property>,
    ) -> Self {
        let find = |n: &str| self.vertices.iter().find(|v| v.name == n);
        let (s, t) = (find(source), find(target));
        let source_key = s
            .map(|v| v.key.iter().map(|k| format!("src_{k}")).collect())
            .unwrap_or_default();
        let target_key = t
            .map(|v| v.key.iter().map(|k| format!("dst_{k}")).collect())
            .unwrap_or_default();
        let id = EpgId(self.edges.len().min(u16::MAX as usize) as u16);
        self.edges.push(EdgeGroupDef {
            id,
            name: name.into(),
            edge_type: edge_type.into(),
            // Unknown names are kept as an out-of-range id and rejected by `build`.
            source: s.map(|v| v.id).unwrap_or(VpgId(u16::MAX)),
            target: t.map(|v| v.id).unwrap_or(VpgId(u16::MAX)),
            direction,
            properties,
            source_key,
            target_key,
            constraints: Vec::new(),
        });
        self
    }

    /// Add a constraint to the group named `group` (vertex or edge).
    pub fn constraint(mut self, group: &str, constraint: Constraint) -> Self {
        if let Some(v) = self.vertices.iter_mut().find(|v| v.name == group) {
            v.constraints.push(constraint);
        } else if let Some(e) = self.edges.iter_mut().find(|e| e.name == group) {
            e.constraints.push(constraint);
        }
        self
    }

    /// Replace or add a property of a group (vertex or edge).
    pub fn set_property(mut self, group: &str, property: Property) -> Self {
        let slot = match self.vertices.iter_mut().find(|v| v.name == group) {
            Some(v) => Some(&mut v.properties),
            None => self
                .edges
                .iter_mut()
                .find(|e| e.name == group)
                .map(|e| &mut e.properties),
        };
        if let Some(properties) = slot {
            match properties.iter_mut().find(|p| p.name == property.name) {
                Some(existing) => *existing = property,
                None => properties.push(property),
            }
        }
        self
    }

    pub fn build(self) -> Result<Schema, LpgError> {
        if self.vertices.len() > 1 << 16 || self.edges.len() > 1 << 16 {
            return Err(LpgError::TooManyGroups);
        }
        let mut names = std::collections::HashSet::new();
        for name in self
            .vertices
            .iter()
            .map(|v| &v.name)
            .chain(self.edges.iter().map(|e| &e.name))
        {
            if !names.insert(name) {
                return Err(LpgError::DuplicateName(name.clone()));
            }
        }
        for v in &self.vertices {
            if v.key.is_empty() {
                return Err(LpgError::EmptyKey(v.name.clone()));
            }
            for k in &v.key {
                match v.properties.iter().find(|p| &p.name == k) {
                    None => {
                        return Err(LpgError::UnknownProperty {
                            group: v.name.clone(),
                            property: k.clone(),
                        })
                    }
                    Some(p) if p.nullable => {
                        return Err(LpgError::NullableKey {
                            group: v.name.clone(),
                            property: k.clone(),
                        })
                    }
                    Some(_) => {}
                }
            }
        }
        for e in &self.edges {
            let (Some(s), Some(t)) = (
                self.vertices.get(e.source.0 as usize),
                self.vertices.get(e.target.0 as usize),
            ) else {
                return Err(LpgError::UnknownGroup(e.name.clone()));
            };
            if e.source_key.len() != s.key.len() || e.target_key.len() != t.key.len() {
                return Err(LpgError::KeyArity {
                    edge_group: e.name.clone(),
                });
            }
        }
        Ok(Schema {
            vertices: self.vertices,
            edges: self.edges,
        })
    }
}
