//! Logical types, properties, directions and constraints. Logical: mapping a
//! type to Arrow, SQL or Substrait is the job of whoever lowers a plan.

#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum TimeUnit {
    Second,
    Millisecond,
    Microsecond,
    Nanosecond,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum LogicalType {
    /// An independently defined logical type; lowering belongs to an adapter.
    Extension {
        namespace: String,
        name: String,
        parameters: Vec<(String, String)>,
    },
    Boolean,
    Int32,
    Int64,
    Float32,
    Float64,
    Decimal {
        precision: u8,
        scale: i8,
    },
    String,
    Binary,
    Date,
    Timestamp {
        unit: TimeUnit,
        timezone: Option<String>,
    },
    Duration(TimeUnit),
    List(Box<LogicalType>),
    Struct(Vec<Property>),
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct Property {
    pub name: String,
    pub ty: LogicalType,
    pub nullable: bool,
}

impl Property {
    pub fn new(name: impl Into<String>, ty: LogicalType) -> Self {
        Self {
            name: name.into(),
            ty,
            nullable: true,
        }
    }
    pub fn required(name: impl Into<String>, ty: LogicalType) -> Self {
        Self {
            name: name.into(),
            ty,
            nullable: false,
        }
    }
}

/// Whether the edges of a group have a direction.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Direction {
    Directed,
    /// Traversable both ways; stored once.
    Undirected,
}

/// How many edges of a group a vertex may have, when the schema knows it.
#[derive(Clone, Copy, Debug, PartialEq, Eq, Hash, Default)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub struct EdgeCardinality {
    pub max_out: Option<u32>,
    pub max_in: Option<u32>,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
#[cfg_attr(feature = "serde", derive(serde::Serialize, serde::Deserialize))]
pub enum Constraint {
    /// These properties are unique together. Object identity is separate from these user-property constraints.
    Unique(Vec<String>),
    /// Bounds on edges per vertex (EPG only). One-to-one is `max_out = max_in = 1`.
    Cardinality(EdgeCardinality),
    /// Every vertex of the source group has at least one edge of this group (EPG only).
    Total,
}
