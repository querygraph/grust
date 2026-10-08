//! Provider lowering is bounded and preserves the caller scope.
use super::*;
use grust_unresolved_plan::Relation as U;

impl State<'_, '_> {
    /// Peel provider chains without spending a Rust stack frame per lowering.
    pub(super) fn extension_relation(&mut self, relation: &U) -> Result<Scope, ResolveError> {
        let depth = self.extension_depth;
        let result = (|| {
            let mut current = relation.clone();
            while let U::Extension {
                name,
                inputs,
                arguments,
            } = &current
            {
                if self.extension_depth >= 32 {
                    return Err(unsupported("extension", "provider lowering depth exceeded"));
                }
                current = self
                    .providers
                    .lower(name, inputs, arguments)?
                    .ok_or_else(|| {
                        unsupported(
                            "extension",
                            &format!("no relation provider registered for {name:?}"),
                        )
                    })?;
                self.extension_depth += 1;
            }
            self.relation(&current)
        })();
        self.extension_depth = depth;
        result
    }
}
