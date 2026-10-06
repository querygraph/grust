//! Storage-independent schema contracts for the Wave 2 design.
//! Group IDs identify catalog groups, never objects or dense kernel indices.
pub mod types;
use std::collections::{BTreeSet, HashSet};
pub use types::{Constraint, Direction, LogicalType, Property, TimeUnit};

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct GroupId(pub u64);
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, PartialOrd, Ord)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct TypeId(pub u64);

/// Object identity need not be a user property; no storage encoding is prescribed.
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Identity {
    Opaque,
    PropertyKey(Vec<String>),
}

#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct ElementType {
    pub id: TypeId,
    pub name: String,
    pub labels: Vec<String>,
    pub supertypes: Vec<TypeId>,
    pub properties: Vec<Property>,
}
pub trait VertexGroup {
    fn id(&self) -> GroupId;
    fn element_type(&self) -> TypeId;
    fn identity(&self) -> &Identity;
    fn constraints(&self) -> &[Constraint];
}
pub trait EdgeGroup {
    fn id(&self) -> GroupId;
    fn element_type(&self) -> TypeId;
    fn endpoints(&self) -> (GroupId, GroupId);
    fn direction(&self) -> Direction;
    fn identity(&self) -> &Identity;
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Vertex {
    pub id: GroupId,
    pub element_type: TypeId,
    pub identity: Identity,
    pub constraints: Vec<Constraint>,
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Edge {
    pub id: GroupId,
    pub element_type: TypeId,
    pub source: GroupId,
    pub target: GroupId,
    pub direction: Direction,
    pub identity: Identity,
}
impl VertexGroup for Vertex {
    fn id(&self) -> GroupId {
        self.id
    }
    fn element_type(&self) -> TypeId {
        self.element_type
    }
    fn identity(&self) -> &Identity {
        &self.identity
    }
    fn constraints(&self) -> &[Constraint] {
        &self.constraints
    }
}
impl EdgeGroup for Edge {
    fn id(&self) -> GroupId {
        self.id
    }
    fn element_type(&self) -> TypeId {
        self.element_type
    }
    fn endpoints(&self) -> (GroupId, GroupId) {
        (self.source, self.target)
    }
    fn direction(&self) -> Direction {
        self.direction
    }
    fn identity(&self) -> &Identity {
        &self.identity
    }
}
pub trait Lpg {
    type Vertex: VertexGroup;
    type Edge: EdgeGroup;
    fn types(&self) -> &[ElementType];
    fn vertex_groups(&self) -> &[Self::Vertex];
    fn edge_groups(&self) -> &[Self::Edge];
    fn element_type(&self, id: TypeId) -> Option<&ElementType> {
        self.types().iter().find(|t| t.id == id)
    }
    /// Includes inherited labels without assigning an object to several groups.
    fn labels(&self, id: TypeId) -> Result<BTreeSet<&str>, SchemaError> {
        let mut pending = vec![id];
        let mut seen = HashSet::new();
        let mut labels = BTreeSet::new();
        while let Some(next) = pending.pop() {
            if seen.insert(next) {
                let ty = self
                    .element_type(next)
                    .ok_or(SchemaError::UnknownType(next))?;
                labels.extend(ty.labels.iter().map(String::as_str));
                pending.extend(ty.supertypes.iter().copied());
            }
        }
        Ok(labels)
    }
}
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum SchemaError {
    DuplicateType(TypeId),
    DuplicateGroup(GroupId),
    UnknownType(TypeId),
    UnknownVertex(GroupId),
    InheritanceCycle(TypeId),
    EmptyPropertyKey(GroupId),
    AmbiguousKeyProperty { group: GroupId, property: String },
    UnknownKeyProperty { group: GroupId, property: String },
    NullableKeyProperty { group: GroupId, property: String },
    DuplicateProperty { ty: TypeId, property: String },
}
#[derive(Clone, Debug, PartialEq, Eq)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
#[cfg_attr(feature = "serde", serde(try_from = "SchemaWire"))]
pub struct Schema {
    types: Vec<ElementType>,
    vertices: Vec<Vertex>,
    edges: Vec<Edge>,
}
impl Lpg for Schema {
    type Vertex = Vertex;
    type Edge = Edge;
    fn types(&self) -> &[ElementType] {
        &self.types
    }
    fn vertex_groups(&self) -> &[Vertex] {
        &self.vertices
    }
    fn edge_groups(&self) -> &[Edge] {
        &self.edges
    }
}
impl Schema {
    /// Free catalog-metadata checks; this function does not inspect graph data.
    pub fn new(
        types: Vec<ElementType>,
        vertices: Vec<Vertex>,
        edges: Vec<Edge>,
    ) -> Result<Self, SchemaError> {
        let schema = Self {
            types,
            vertices,
            edges,
        };
        schema.validate()?;
        Ok(schema)
    }
    fn validate(&self) -> Result<(), SchemaError> {
        let mut types = HashSet::new();
        for ty in &self.types {
            if !types.insert(ty.id) {
                return Err(SchemaError::DuplicateType(ty.id));
            }
            let mut properties = HashSet::new();
            for p in &ty.properties {
                if !properties.insert(&p.name) {
                    return Err(SchemaError::DuplicateProperty {
                        ty: ty.id,
                        property: p.name.clone(),
                    });
                }
            }
        }
        fn visit(
            schema: &Schema,
            id: TypeId,
            active: &mut HashSet<TypeId>,
            done: &mut HashSet<TypeId>,
        ) -> Result<(), SchemaError> {
            if done.contains(&id) {
                return Ok(());
            }
            if !active.insert(id) {
                return Err(SchemaError::InheritanceCycle(id));
            }
            let ty = schema
                .element_type(id)
                .ok_or(SchemaError::UnknownType(id))?;
            for parent in &ty.supertypes {
                visit(schema, *parent, active, done)?;
            }
            active.remove(&id);
            done.insert(id);
            Ok(())
        }
        let mut done = HashSet::new();
        for ty in &self.types {
            visit(self, ty.id, &mut HashSet::new(), &mut done)?;
        }
        let mut groups = HashSet::new();
        for v in &self.vertices {
            if !groups.insert(v.id) {
                return Err(SchemaError::DuplicateGroup(v.id));
            }
            self.validate_identity(v.id, v.element_type, &v.identity)?;
        }
        for e in &self.edges {
            if !groups.insert(e.id) {
                return Err(SchemaError::DuplicateGroup(e.id));
            }
            for endpoint in [e.source, e.target] {
                if !self.vertices.iter().any(|v| v.id == endpoint) {
                    return Err(SchemaError::UnknownVertex(endpoint));
                }
            }
            self.validate_identity(e.id, e.element_type, &e.identity)?;
        }
        Ok(())
    }
    fn validate_identity(
        &self,
        group: GroupId,
        ty: TypeId,
        identity: &Identity,
    ) -> Result<(), SchemaError> {
        self.element_type(ty).ok_or(SchemaError::UnknownType(ty))?;
        if let Identity::PropertyKey(keys) = identity {
            if keys.is_empty() {
                return Err(SchemaError::EmptyPropertyKey(group));
            }
            for key in keys {
                let mut pending = vec![ty];
                let mut found: Option<&Property> = None;
                let mut seen = HashSet::new();
                while let Some(id) = pending.pop() {
                    if !seen.insert(id) {
                        continue;
                    }
                    let t = self.element_type(id).ok_or(SchemaError::UnknownType(id))?;
                    if let Some(p) = t.properties.iter().find(|p| &p.name == key) {
                        if p.nullable {
                            return Err(SchemaError::NullableKeyProperty {
                                group,
                                property: key.clone(),
                            });
                        }
                        if found.is_some_and(|previous| previous != p) {
                            return Err(SchemaError::AmbiguousKeyProperty {
                                group,
                                property: key.clone(),
                            });
                        }
                        found = Some(p);
                    }
                    pending.extend(t.supertypes.iter().copied());
                }
                if found.is_none() {
                    return Err(SchemaError::UnknownKeyProperty {
                        group,
                        property: key.clone(),
                    });
                }
            }
        }
        Ok(())
    }
}
#[cfg(test)]
mod tests;

impl std::fmt::Display for SchemaError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "invalid schema: {self:?}")
    }
}
impl std::error::Error for SchemaError {}
#[cfg(feature = "serde")]
#[derive(serde::Deserialize)]
struct SchemaWire {
    types: Vec<ElementType>,
    vertices: Vec<Vertex>,
    edges: Vec<Edge>,
}
#[cfg(feature = "serde")]
impl TryFrom<SchemaWire> for Schema {
    type Error = SchemaError;
    fn try_from(value: SchemaWire) -> Result<Self, Self::Error> {
        Self::new(value.types, value.vertices, value.edges)
    }
}
