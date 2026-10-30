//! Pre-resolution binding of a flow's reads for one bounded lowering
//! (BOUNDED-PLAN-ADMISSION-DESIGN §2 as narrowed in §10 after CF-0136).
//!
//! Before `PlanResolver` runs, and therefore before any resolver I/O, the
//! flow's `spec::QueryPlan` is walked and every read is classified against
//! explicit, caller-supplied bindings: a streaming read must name a bound
//! source, a batch read must name a local output or a proven static binding,
//! and the constructs whose resolution executes helper plans are refused.
//! Nothing is rewritten: there is no synthetic namespace, and a flow that
//! reads one name in both modes is refused instead.

use std::collections::{BTreeMap, BTreeSet, HashSet};
use std::fmt;
use std::sync::Arc;

use datafusion::arrow::datatypes::SchemaRef;
use datafusion::datasource::TableProvider;
use sail_common::spec;
use sail_plan::resolver::scope::RelationScope;

use super::intent::BatchIntent;
use super::source::SourceDescriptor;
use crate::pipelines::analysis::GraphScope;
use crate::pipelines::graph::{Flow, GraphDefinition, Name, quoted};

/// A recorded streaming source bound to this lowering, with its identity
/// stated by the caller: the graph-local name the flow reads it by, the
/// source schema every scan must present, the descriptor captured with the
/// frontier, the intent the batch covers, and one provider per range of
/// that intent, in range order.
pub struct SourceBinding {
    pub name: Name,
    pub schema: SchemaRef,
    pub descriptor: SourceDescriptor,
    pub intent: BatchIntent,
    pub scans: Vec<Arc<dyn TableProvider>>,
}

/// A proven static side for a batch read of a name that is not a local
/// output, pinned to `identity` (a table version, a snapshot digest) by the
/// caller. A name alone never qualifies; the provider joins this struct in
/// the lowering component that scans it.
pub struct StaticBinding {
    pub name: Name,
    pub identity: String,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ReadMode {
    Batch,
    Streaming,
}

/// Why a flow is refused before resolution.
#[derive(Clone, Debug, PartialEq, Eq)]
pub enum BindingError {
    /// A streaming read of a name with no source binding.
    UnboundStreamingRead(Name),
    /// A batch read of a name that is neither a local output nor a static
    /// binding; resolving it would reach the catalog.
    UnboundCatalogRead(Name),
    /// One name read as a stream and as a batch in the same flow.
    MixedReadModes(Name),
    /// `ReadNamedTable.temporal`: time travel resolution executes a helper
    /// plan (`time_travel.rs`).
    TimeTravel(Name),
    /// `Pivot` without explicit values infers them by executing the input
    /// (`pivoting.rs`).
    PivotInference,
    /// `Tail` resolves through a count query (`limit.rs`).
    Tail,
    /// The `Stat*` nodes execute helper plans during resolution (`stat.rs`).
    StatHelper(&'static str),
    /// A read kind outside the initial subset.
    UnsupportedRead(&'static str),
    /// The name cannot be qualified for this flow.
    Unqualifiable(String),
    /// A source binding has a different number of scans than ranges.
    ScanCountMismatch {
        name: Name,
        ranges: usize,
        scans: usize,
    },
    /// A scan presents a schema other than the binding's source schema.
    ScanSchemaMismatch { name: Name, range: usize },
    /// A range names a partition or incarnation the descriptor does not hold.
    RangeOutsideDescriptor { name: Name, range: usize },
    /// A static binding without a pinned identity proves nothing.
    StaticIdentityMissing(Name),
}

impl fmt::Display for BindingError {
    fn fmt(&self, f: &mut fmt::Formatter<'_>) -> fmt::Result {
        match self {
            Self::UnboundStreamingRead(name) => {
                write!(f, "streaming read of {} has no bound range", quoted(name))
            }
            Self::UnboundCatalogRead(name) => write!(
                f,
                "batch read of {} is neither a pipeline output nor a pinned static binding",
                quoted(name)
            ),
            Self::MixedReadModes(name) => write!(
                f,
                "{} is read both as a stream and as a batch in one flow",
                quoted(name)
            ),
            Self::TimeTravel(name) => {
                write!(f, "time travel read of {} is not admitted", quoted(name))
            }
            Self::PivotInference => write!(f, "pivot without explicit values is not admitted"),
            Self::Tail => write!(f, "tail is not admitted"),
            Self::StatHelper(kind) => write!(f, "{kind} is not admitted"),
            Self::UnsupportedRead(kind) => write!(f, "{kind} read is not admitted"),
            Self::Unqualifiable(message) => write!(f, "{message}"),
            Self::ScanCountMismatch {
                name,
                ranges,
                scans,
            } => write!(
                f,
                "binding {} has {ranges} ranges but {scans} scans",
                quoted(name)
            ),
            Self::ScanSchemaMismatch { name, range } => write!(
                f,
                "scan {range} of binding {} does not present the source schema",
                quoted(name)
            ),
            Self::RangeOutsideDescriptor { name, range } => write!(
                f,
                "range {range} of binding {} is outside the captured descriptor",
                quoted(name)
            ),
            Self::StaticIdentityMissing(name) => {
                write!(f, "static binding {} has no pinned identity", quoted(name))
            }
        }
    }
}

impl std::error::Error for BindingError {}

/// The reads of a validated flow, by qualified name.
#[derive(Debug, Default, PartialEq, Eq)]
pub struct ReadSet {
    pub streaming: BTreeSet<Name>,
    pub local: BTreeSet<Name>,
    pub statics: BTreeSet<Name>,
}

/// The compatibility a binding must show before it is used: one scan per
/// range, every scan presenting the source schema, every range inside the
/// captured descriptor (its partition under its incarnation). Zero ranges is
/// a recorded empty intent and is valid; it is not an absent binding.
pub fn check_source(binding: &SourceBinding) -> Result<(), BindingError> {
    let ranges = binding.intent.ranges.len();
    let scans = binding.scans.len();
    if ranges != scans {
        return Err(BindingError::ScanCountMismatch {
            name: binding.name.clone(),
            ranges,
            scans,
        });
    }
    for (index, (range, scan)) in binding.intent.ranges.iter().zip(&binding.scans).enumerate() {
        let known = binding.descriptor.partitions.iter().any(|partition| {
            partition.id == range.partition && partition.incarnation == range.incarnation
        });
        if !known {
            return Err(BindingError::RangeOutsideDescriptor {
                name: binding.name.clone(),
                range: index,
            });
        }
        if scan.schema() != binding.schema {
            return Err(BindingError::ScanSchemaMismatch {
                name: binding.name.clone(),
                range: index,
            });
        }
    }
    Ok(())
}

/// Validates every read of `plan` against the bindings, before resolution,
/// after checking each binding's own compatibility.
pub fn validate_reads(
    graph: &GraphDefinition,
    flow: &Flow,
    plan: &spec::QueryPlan,
    sources: &[SourceBinding],
    statics: &[StaticBinding],
) -> Result<ReadSet, BindingError> {
    for binding in sources {
        check_source(binding)?;
    }
    for binding in statics {
        if binding.identity.is_empty() {
            return Err(BindingError::StaticIdentityMissing(binding.name.clone()));
        }
    }
    let empty = BTreeMap::new();
    let scope = GraphScope::new(graph, &empty, flow);
    let mut walker = Walker {
        graph,
        scope: &scope,
        sources: sources.iter().map(|binding| &binding.name).collect(),
        statics: statics.iter().map(|binding| &binding.name).collect(),
        modes: BTreeMap::new(),
        reads: ReadSet::default(),
    };
    walker.walk(plan, &HashSet::new())?;
    Ok(walker.reads)
}

struct Walker<'a> {
    graph: &'a GraphDefinition,
    scope: &'a GraphScope<'a>,
    sources: BTreeSet<&'a Name>,
    statics: BTreeSet<&'a Name>,
    modes: BTreeMap<Name, ReadMode>,
    reads: ReadSet,
}

impl Walker<'_> {
    /// The qualified name of a read, as `GraphScope::resolve` would see it:
    /// lower-cased parts, taken as is when they spell an output, else
    /// qualified for the flow.
    fn qualify(&self, name: &spec::ObjectName) -> Result<Name, BindingError> {
        let raw: Name = name
            .parts()
            .iter()
            .map(|part| part.as_ref().to_ascii_lowercase())
            .collect();
        if self.graph.outputs.iter().any(|output| output.name == raw) {
            return Ok(raw);
        }
        self.scope
            .qualify(&raw)
            .map_err(|error| BindingError::Unqualifiable(error.to_string()))
    }

    fn read(
        &mut self,
        read_type: &spec::ReadType,
        streaming: bool,
        cte_scope: &HashSet<String>,
    ) -> Result<(), BindingError> {
        let table = match read_type {
            spec::ReadType::NamedTable(table) => table,
            spec::ReadType::DataSource(_) => {
                return Err(BindingError::UnsupportedRead("data source"));
            }
            spec::ReadType::Udtf(_) => return Err(BindingError::UnsupportedRead("table function")),
            spec::ReadType::DynamicTable(_) => {
                return Err(BindingError::UnsupportedRead("dynamic table"));
            }
        };
        // A bare name defined by an enclosing CTE is substituted by the
        // resolver, as `is_streaming_query_plan` also assumes.
        if let [name] = table.name.parts()
            && cte_scope.contains(name.as_ref())
        {
            return Ok(());
        }
        let name = self.qualify(&table.name)?;
        if table.temporal.is_some() {
            return Err(BindingError::TimeTravel(name));
        }
        let mode = if streaming {
            ReadMode::Streaming
        } else {
            ReadMode::Batch
        };
        match self.modes.insert(name.clone(), mode) {
            Some(previous) if previous != mode => {
                return Err(BindingError::MixedReadModes(name));
            }
            _ => {}
        }
        match mode {
            ReadMode::Streaming => {
                if !self.sources.contains(&name) {
                    return Err(BindingError::UnboundStreamingRead(name));
                }
                self.reads.streaming.insert(name);
            }
            ReadMode::Batch => {
                if self.graph.outputs.iter().any(|output| output.name == name) {
                    self.reads.local.insert(name);
                } else if self.statics.contains(&name) {
                    self.reads.statics.insert(name);
                } else {
                    return Err(BindingError::UnboundCatalogRead(name));
                }
            }
        }
        Ok(())
    }

    fn walk(
        &mut self,
        plan: &spec::QueryPlan,
        cte_scope: &HashSet<String>,
    ) -> Result<(), BindingError> {
        use spec::QueryNode as N;
        match &plan.node {
            N::Read {
                read_type,
                is_streaming,
            } => self.read(read_type, *is_streaming, cte_scope),
            // Leaves without query inputs.
            N::LocalRelation { .. }
            | N::CachedLocalRelation { .. }
            | N::CachedRemoteRelation { .. }
            | N::Range(_)
            | N::Empty { .. }
            | N::Values(_)
            | N::CommonInlineUserDefinedTableFunction(_) => Ok(()),
            // Constructs whose resolution executes a helper plan.
            N::Tail { .. } => Err(BindingError::Tail),
            N::Pivot(pivot) if pivot.values.is_empty() => Err(BindingError::PivotInference),
            N::StatSummary { .. } => Err(BindingError::StatHelper("summary")),
            N::StatDescribe { .. } => Err(BindingError::StatHelper("describe")),
            N::StatCrosstab { .. } => Err(BindingError::StatHelper("crosstab")),
            N::StatCov { .. } => Err(BindingError::StatHelper("covariance")),
            N::StatCorr { .. } => Err(BindingError::StatHelper("correlation")),
            N::StatApproxQuantile { .. } => Err(BindingError::StatHelper("approximate quantile")),
            N::StatFreqItems { .. } => Err(BindingError::StatHelper("frequent items")),
            N::StatSampleBy { .. } => Err(BindingError::StatHelper("sample by")),
            // One required input.
            N::Filter { input, .. }
            | N::Sort { input, .. }
            | N::Limit { input, .. }
            | N::SubqueryAlias { input, .. }
            | N::Repartition { input, .. }
            | N::ToDf { input, .. }
            | N::WithColumnsRenamed { input, .. }
            | N::Drop { input, .. }
            | N::WithColumns { input, .. }
            | N::Hint { input, .. }
            | N::ToSchema { input, .. }
            | N::RepartitionByExpression { input, .. }
            | N::MapPartitions { input, .. }
            | N::CollectMetrics { input, .. }
            | N::FillNa { input, .. }
            | N::DropNa { input, .. }
            | N::Replace { input, .. }
            | N::WithParameters { input, .. }
            | N::TableAlias { input, .. }
            | N::TableSample { input, .. }
            | N::NamedWindows { input, .. } => self.walk(input, cte_scope),
            // One optional input.
            N::Project { input, .. } | N::LateralView { input, .. } => match input {
                Some(input) => self.walk(input, cte_scope),
                None => Ok(()),
            },
            // Nested structs with one input.
            N::Aggregate(aggregate) => self.walk(&aggregate.input, cte_scope),
            N::Sample(sample) => self.walk(&sample.input, cte_scope),
            N::Deduplicate(deduplicate) => self.walk(&deduplicate.input, cte_scope),
            N::Pivot(pivot) => self.walk(&pivot.input, cte_scope),
            N::Unpivot(unpivot) => self.walk(&unpivot.input, cte_scope),
            N::Parse(parse) => self.walk(&parse.input, cte_scope),
            N::WithWatermark(watermark) => self.walk(&watermark.input, cte_scope),
            N::ApplyInPandasWithState(apply) => self.walk(&apply.input, cte_scope),
            N::GroupMap(group) => {
                self.walk(&group.input, cte_scope)?;
                match &group.initial_input {
                    Some(initial) => self.walk(initial, cte_scope),
                    None => Ok(()),
                }
            }
            // Several inputs.
            N::Join(join) => {
                self.walk(&join.left, cte_scope)?;
                self.walk(&join.right, cte_scope)
            }
            N::LateralJoin { left, right, .. } => {
                self.walk(left, cte_scope)?;
                self.walk(right, cte_scope)
            }
            N::SetOperation(set) => {
                self.walk(&set.left, cte_scope)?;
                self.walk(&set.right, cte_scope)
            }
            N::CoGroupMap(cogroup) => {
                self.walk(&cogroup.input, cte_scope)?;
                self.walk(&cogroup.other, cte_scope)
            }
            N::WithRelations { root, references } => {
                for reference in references {
                    self.walk(reference, cte_scope)?;
                }
                self.walk(root, cte_scope)
            }
            N::WithCtes { input, ctes, .. } => {
                let mut inner = cte_scope.clone();
                for (name, definition) in ctes {
                    self.walk(definition, &inner)?;
                    inner.insert(name.as_ref().to_string());
                }
                self.walk(input, &inner)
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use std::collections::HashMap;

    use datafusion::arrow::datatypes::{DataType, Field, Schema};
    use datafusion::datasource::MemTable;

    use super::*;
    use crate::pipelines::graph::Output;
    use crate::spark::connect::OutputType;
    use crate::spark::connect::pipeline_command::DefineOutput;

    fn name(parts: &[&str]) -> Name {
        parts.iter().map(|part| part.to_string()).collect()
    }

    fn output(parts: &[&str]) -> Output {
        Output {
            name: name(parts),
            kind: OutputType::Table,
            definition: DefineOutput::default(),
            schema: None,
            view: None,
        }
    }

    fn read(table: &str, streaming: bool) -> spec::QueryPlan {
        spec::QueryPlan::new(spec::QueryNode::Read {
            read_type: spec::ReadType::NamedTable(Box::new(spec::ReadNamedTable {
                name: spec::ObjectName::bare(table),
                temporal: None,
                sample: None,
                options: vec![],
            })),
            is_streaming: streaming,
        })
    }

    fn graph() -> GraphDefinition {
        GraphDefinition {
            catalog: "c".into(),
            database: "d".into(),
            sql_conf: HashMap::new(),
            outputs: vec![output(&["c", "d", "events"]), output(&["c", "d", "target"])],
            flows: vec![],
        }
    }

    fn flow(query: spec::QueryPlan) -> Flow {
        Flow {
            name: name(&["c", "d", "target"]),
            target: name(&["c", "d", "target"]),
            query,
            sql_conf: HashMap::new(),
            catalog: "c".into(),
            database: "d".into(),
            auto_cdc: None,
        }
    }

    type TestResult = Result<(), Box<dyn std::error::Error>>;

    fn provider() -> Result<Arc<dyn TableProvider>, Box<dyn std::error::Error>> {
        let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)]));
        Ok(Arc::new(MemTable::try_new(schema, vec![vec![]])?))
    }

    fn source(parts: &[&str]) -> SourceBinding {
        SourceBinding {
            name: name(parts),
            schema: Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, false)])),
            descriptor: SourceDescriptor {
                kind: "test".into(),
                descriptor: serde_json::json!({}),
                partitions: vec![],
            },
            intent: BatchIntent { ranges: vec![] },
            scans: vec![],
        }
    }

    fn statik(parts: &[&str]) -> StaticBinding {
        StaticBinding {
            name: name(parts),
            identity: "version:7".into(),
        }
    }

    fn validate(
        plan: spec::QueryPlan,
        sources: &[SourceBinding],
        statics: &[StaticBinding],
    ) -> Result<ReadSet, BindingError> {
        let graph = graph();
        let flow = flow(plan.clone());
        validate_reads(&graph, &flow, &plan, sources, statics)
    }

    #[test]
    fn a_bound_streaming_read_and_a_local_batch_read_are_accepted_and_qualified() -> TestResult {
        let plan = spec::QueryPlan::new(spec::QueryNode::Join(spec::Join {
            left: Box::new(read("Clicks", true)),
            right: Box::new(read("EVENTS", false)),
            join_type: spec::JoinType::Inner,
            join_criteria: None,
            join_data_type: None,
        }));
        let reads = validate(plan, &[source(&["c", "d", "clicks"])], &[])?;
        assert_eq!(
            reads.streaming,
            BTreeSet::from([name(&["c", "d", "clicks"])])
        );
        assert_eq!(reads.local, BTreeSet::from([name(&["c", "d", "events"])]));
        assert!(reads.statics.is_empty());
        Ok(())
    }

    #[test]
    fn unbound_reads_are_refused_before_resolution() -> TestResult {
        assert_eq!(
            validate(read("clicks", true), &[], &[]),
            Err(BindingError::UnboundStreamingRead(name(&[
                "c", "d", "clicks"
            ])))
        );
        assert_eq!(
            validate(read("dim", false), &[], &[]),
            Err(BindingError::UnboundCatalogRead(name(&["c", "d", "dim"])))
        );
        let reads = validate(read("dim", false), &[], &[statik(&["c", "d", "dim"])])?;
        assert_eq!(reads.statics, BTreeSet::from([name(&["c", "d", "dim"])]));
        Ok(())
    }

    #[test]
    fn one_name_in_both_modes_is_refused_instead_of_renamed() -> TestResult {
        let plan = spec::QueryPlan::new(spec::QueryNode::Join(spec::Join {
            left: Box::new(read("events", true)),
            right: Box::new(read("events", false)),
            join_type: spec::JoinType::Inner,
            join_criteria: None,
            join_data_type: None,
        }));
        assert_eq!(
            validate(plan, &[source(&["c", "d", "events"])], &[]),
            Err(BindingError::MixedReadModes(name(&["c", "d", "events"])))
        );
        Ok(())
    }

    #[test]
    fn helper_executing_constructs_are_refused() -> TestResult {
        let streaming = || read("clicks", true);
        let sources = [source(&["c", "d", "clicks"])];
        let mut temporal = read("clicks", true);
        if let spec::QueryNode::Read {
            read_type: spec::ReadType::NamedTable(table),
            ..
        } = &mut temporal.node
        {
            table.temporal = Some(spec::TableTemporal::Version {
                value: spec::Expr::Literal(spec::Literal::Int64 { value: Some(3) }),
            });
        }
        assert_eq!(
            validate(temporal, &sources, &[]),
            Err(BindingError::TimeTravel(name(&["c", "d", "clicks"])))
        );
        let pivot = spec::QueryPlan::new(spec::QueryNode::Pivot(spec::Pivot {
            input: Box::new(streaming()),
            grouping: None,
            aggregate: vec![],
            columns: vec![],
            values: vec![],
        }));
        assert_eq!(
            validate(pivot, &sources, &[]),
            Err(BindingError::PivotInference)
        );
        let tail = spec::QueryPlan::new(spec::QueryNode::Tail {
            input: Box::new(streaming()),
            limit: spec::Expr::Literal(spec::Literal::Int32 { value: Some(1) }),
        });
        assert_eq!(validate(tail, &sources, &[]), Err(BindingError::Tail));
        let describe = spec::QueryPlan::new(spec::QueryNode::StatDescribe {
            input: Box::new(streaming()),
            columns: vec![],
        });
        assert_eq!(
            validate(describe, &sources, &[]),
            Err(BindingError::StatHelper("describe"))
        );
        Ok(())
    }

    #[test]
    fn a_cte_name_is_not_a_table_read_and_its_definition_is_walked() -> TestResult {
        let plan = spec::QueryPlan::new(spec::QueryNode::WithCtes {
            input: Box::new(read("staged", false)),
            recursive: false,
            ctes: vec![("staged".into(), read("clicks", true))],
        });
        let reads = validate(plan, &[source(&["c", "d", "clicks"])], &[])?;
        assert_eq!(
            reads.streaming,
            BTreeSet::from([name(&["c", "d", "clicks"])])
        );
        assert!(reads.local.is_empty());
        let unbound = spec::QueryPlan::new(spec::QueryNode::WithCtes {
            input: Box::new(read("staged", false)),
            recursive: false,
            ctes: vec![("staged".into(), read("missing", true))],
        });
        assert_eq!(
            validate(unbound, &[], &[]),
            Err(BindingError::UnboundStreamingRead(name(&[
                "c", "d", "missing"
            ])))
        );
        Ok(())
    }

    #[test]
    fn a_binding_must_be_compatible_with_its_own_intent_and_descriptor() -> TestResult {
        use super::super::source::{Cursor, Incarnation, Partition, PartitionId, Range};
        let range = |partition: &str, incarnation: &str| Range {
            partition: PartitionId(partition.into()),
            incarnation: Incarnation(incarnation.into()),
            start: Cursor("pos:0".into()),
            end: Cursor("pos:2".into()),
        };
        let mut binding = source(&["c", "d", "clicks"]);
        binding.descriptor.partitions = vec![Partition {
            id: PartitionId("p0".into()),
            incarnation: Incarnation("inc:1".into()),
        }];
        binding.intent.ranges = vec![range("p0", "inc:1")];
        assert_eq!(
            check_source(&binding),
            Err(BindingError::ScanCountMismatch {
                name: name(&["c", "d", "clicks"]),
                ranges: 1,
                scans: 0,
            })
        );
        binding.scans = vec![provider()?];
        assert_eq!(check_source(&binding), Ok(()));
        // A recreated partition is outside the captured descriptor.
        binding.intent.ranges = vec![range("p0", "inc:2")];
        assert_eq!(
            check_source(&binding),
            Err(BindingError::RangeOutsideDescriptor {
                name: name(&["c", "d", "clicks"]),
                range: 0,
            })
        );
        binding.intent.ranges = vec![range("p0", "inc:1")];
        let other = Arc::new(Schema::new(vec![Field::new("id", DataType::Utf8, true)]));
        binding.scans = vec![Arc::new(MemTable::try_new(other, vec![vec![]])?)];
        assert_eq!(
            check_source(&binding),
            Err(BindingError::ScanSchemaMismatch {
                name: name(&["c", "d", "clicks"]),
                range: 0,
            })
        );
        // An empty recorded intent is valid and distinct from an absent binding.
        binding.intent.ranges = vec![];
        binding.scans = vec![];
        assert_eq!(check_source(&binding), Ok(()));
        assert_eq!(
            validate(
                read("dim", false),
                &[],
                &[StaticBinding {
                    name: name(&["c", "d", "dim"]),
                    identity: String::new(),
                }]
            ),
            Err(BindingError::StaticIdentityMissing(name(&[
                "c", "d", "dim"
            ])))
        );
        Ok(())
    }

    #[test]
    fn unsupported_read_kinds_are_refused() -> TestResult {
        let plan = spec::QueryPlan::new(spec::QueryNode::Read {
            read_type: spec::ReadType::DataSource(Box::new(spec::ReadDataSource {
                format: Some("parquet".into()),
                schema: None,
                options: vec![],
                paths: vec!["/tmp/x".into()],
                predicates: vec![],
            })),
            is_streaming: true,
        });
        assert_eq!(
            validate(plan, &[], &[]),
            Err(BindingError::UnsupportedRead("data source"))
        );
        Ok(())
    }
}
