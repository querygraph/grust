use datafusion_expr::LogicalPlan;
use sail_catalog::manager::CatalogManager;

use crate::error::{PlanError, PlanResult};

pub(super) const VIEW_NAMESPACE_SIZE: &str = "view.catalogAndNamespace.numParts";
pub(super) const VIEW_NAMESPACE_PART: &str = "view.catalogAndNamespace.part.";

/// A private relation namespace for one planning request. Returned plans must
/// expose user-facing field names, as stored temporary-view plans do.
/// CTEs take precedence over this scope; the catalog is consulted on `None`.
pub trait RelationScope: Send + Sync {
    fn resolve(&self, name: &[String]) -> PlanResult<Option<LogicalPlan>>;

    /// Resolve a named read without discarding its requested mode. Existing
    /// scopes keep their lookup semantics until they opt into mode-specific inputs.
    fn resolve_read(
        &self,
        name: &[String],
        _is_streaming: bool,
    ) -> PlanResult<Option<LogicalPlan>> {
        self.resolve(name)
    }

    /// Resolve a target produced by a computed IDENTIFIER expression, after
    /// native CTE lookup. Callers may distinguish this later binding phase from
    /// named inputs. Existing scopes retain the same lookup by default.
    fn resolve_late_bound(&self, name: &[String]) -> PlanResult<Option<LogicalPlan>> {
        self.resolve(name)
    }

    /// Preserve the later binding phase as well as the requested read mode.
    fn resolve_late_bound_read(
        &self,
        name: &[String],
        _is_streaming: bool,
    ) -> PlanResult<Option<LogicalPlan>> {
        self.resolve_late_bound(name)
    }

    /// Bind an external name using the caller's captured namespace. This keeps
    /// independent planning requests from mutating shared catalog defaults.
    fn qualify(&self, name: &[String]) -> PlanResult<Vec<String>> {
        Ok(name.to_vec())
    }

    /// Qualify a computed target after its late lookup hook declines it.
    /// This defaults to the existing captured namespace policy.
    fn qualify_late_bound(&self, name: &[String]) -> PlanResult<Vec<String>> {
        self.qualify(name)
    }

    /// The captured catalog followed by namespace components, when this scope
    /// supplies defaults that must be retained in a persistent SQL view.
    fn default_namespace(&self) -> Option<Vec<String>> {
        None
    }
}

/// Catalog views retain their creation namespace independently of the caller's
/// current namespace. A parent scope can still bind qualified graph-local names.
pub(super) struct ViewScope<'a> {
    manager: &'a CatalogManager,
    parent: Option<&'a dyn RelationScope>,
    namespace: Vec<String>,
}

impl<'a> ViewScope<'a> {
    pub fn from_properties(
        manager: &'a CatalogManager,
        parent: Option<&'a dyn RelationScope>,
        properties: &[(String, String)],
    ) -> PlanResult<Option<Self>> {
        let Some((_, size)) = properties
            .iter()
            .find(|(key, _)| key == VIEW_NAMESPACE_SIZE)
        else {
            return Ok(None);
        };
        let size: usize = size
            .parse()
            .map_err(|_| PlanError::analysis("invalid view catalog and namespace size"))?;
        if size < 2 || size > properties.len() {
            return Err(PlanError::analysis(
                "invalid view catalog and namespace size",
            ));
        }
        let namespace = (0..size)
            .map(|index| {
                let key = format!("{VIEW_NAMESPACE_PART}{index}");
                properties
                    .iter()
                    .find(|(name, _)| name == &key)
                    .map(|(_, value)| value.clone())
                    .ok_or_else(|| PlanError::analysis(format!("missing view property {key}")))
            })
            .collect::<PlanResult<Vec<_>>>()?;
        Ok(Some(Self {
            manager,
            parent,
            namespace,
        }))
    }
}

impl RelationScope for ViewScope<'_> {
    fn resolve_read(&self, name: &[String], is_streaming: bool) -> PlanResult<Option<LogicalPlan>> {
        match self.parent {
            Some(parent) => parent.resolve_read(&self.qualify(name)?, is_streaming),
            None => Ok(None),
        }
    }

    fn resolve_late_bound_read(
        &self,
        name: &[String],
        is_streaming: bool,
    ) -> PlanResult<Option<LogicalPlan>> {
        match self.parent {
            Some(parent) => parent.resolve_late_bound_read(&self.qualify(name)?, is_streaming),
            None => Ok(None),
        }
    }

    fn resolve(&self, name: &[String]) -> PlanResult<Option<LogicalPlan>> {
        match self.parent {
            Some(parent) => parent.resolve(&self.qualify(name)?),
            None => Ok(None),
        }
    }

    fn resolve_late_bound(&self, name: &[String]) -> PlanResult<Option<LogicalPlan>> {
        match self.parent {
            Some(parent) => parent.resolve_late_bound(&self.qualify(name)?),
            None => Ok(None),
        }
    }

    fn qualify(&self, name: &[String]) -> PlanResult<Vec<String>> {
        if name.len() == 1 {
            let mut parts = self.namespace.clone();
            parts.extend_from_slice(name);
            Ok(parts)
        } else {
            // Keep the catalog manager's rules for explicit catalogs and
            // multi-level namespaces; only the default catalog changes here.
            Ok(self
                .manager
                .resolve_table_reference_with_default_catalog(&self.namespace[0], name)?
                .into())
        }
    }

    fn default_namespace(&self) -> Option<Vec<String>> {
        Some(self.namespace.clone())
    }
}
