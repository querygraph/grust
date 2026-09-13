//! Retained adapter selection provenance, separate from kernel topology.

use super::*;
use crate::{MissingWeight, ProjectionOptions, WeightSelection};

/// Input representation used to build owned CSR. Each representation constructs owned topology.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum ProjectionRepresentation {
    Topology,
    PropertyGraph,
    ArrowBatches,
}

/// Selection recorded by a property/Arrow adapter. Raw topology input has no
/// labels or property policy to record and exposes no selection descriptor.
#[derive(Debug)]
pub struct ProjectionSelection {
    pub node_labels: Option<Vec<String>>,
    pub relationship_labels: Option<Vec<String>>,
    /// None means unit weights. A raw weighted topology has no property name.
    pub weight_property: Option<String>,
    pub missing_weight: Option<MissingWeight>,
    _reservation: MemoryReservation,
}

impl GraphProjection {
    pub(crate) fn with_origin(
        mut self,
        representation: ProjectionRepresentation,
        options: ProjectionOptions<'_>,
    ) -> Result<Self> {
        let context = self.execution();
        let mut bytes = 0usize;
        for labels in [options.node_labels, options.relationship_labels]
            .into_iter()
            .flatten()
        {
            bytes = bytes.saturating_add(labels.len().saturating_mul(size_of::<String>()));
            for label in labels {
                context.charge_work(1)?;
                bytes = bytes.saturating_add(label.len());
            }
        }
        if let WeightSelection::Property { key, .. } = options.weight {
            bytes = bytes.saturating_add(key.len());
        }
        let reservation = context.reserve(bytes)?;
        let (weight_property, missing_weight) = match options.weight {
            WeightSelection::Unit => (None, None),
            WeightSelection::Property { key, missing } => (Some(text(key)?), Some(missing)),
        };
        let selection = ProjectionSelection {
            node_labels: labels(options.node_labels, context)?,
            relationship_labels: labels(options.relationship_labels, context)?,
            weight_property,
            missing_weight,
            _reservation: reservation,
        };
        let inner = Arc::get_mut(&mut self.inner).ok_or_else(|| {
            ProcedureError::OutputContract("projection shared before adapter initialization".into())
        })?;
        inner.representation = representation;
        inner.selection = Some(selection);
        Ok(self)
    }
}

fn labels(input: Option<&[String]>, context: &ExecutionContext) -> Result<Option<Vec<String>>> {
    let Some(input) = input else {
        return Ok(None);
    };
    let mut output = Vec::new();
    output.try_reserve_exact(input.len())?;
    for label in input {
        context.charge_work(1)?;
        output.push(text(label)?);
    }
    Ok(Some(output))
}

fn text(input: &str) -> Result<String> {
    let mut output = String::new();
    output.try_reserve_exact(input.len())?;
    output.push_str(input);
    Ok(output)
}
