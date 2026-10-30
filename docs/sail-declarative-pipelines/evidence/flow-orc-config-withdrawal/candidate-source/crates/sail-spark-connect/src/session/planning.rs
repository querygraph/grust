use std::sync::Arc;

use datafusion::prelude::SessionContext;
use sail_plan::config::PlanConfig;

use super::SparkSession;
use crate::error::SparkResult;

pub(crate) struct PlanningContext {
    pub context: SessionContext,
    pub config: Arc<PlanConfig>,
}

impl SparkSession {
    /// Apply flow/graph settings to a private planning state. Shared services,
    /// catalogs, functions and runtime retain their identity; session settings
    /// are never temporarily changed while an asynchronous plan is resolved.
    pub(crate) fn planning_context(
        &self,
        parent: &SessionContext,
        overrides: impl IntoIterator<Item = (String, String)>,
    ) -> SparkResult<PlanningContext> {
        // Release the Spark mutex before taking the DataFusion state lock:
        // ordinary configuration updates may acquire these in the other order.
        let mut runtime = self.state.lock()?.config.clone();
        for (key, value) in overrides {
            runtime.set(key, value)?;
        }
        let mut config = PlanConfig::try_from(&runtime)?;
        config.session_user_id = self.user_id().to_string();
        let read_defaults = runtime.orc_listing_defaults()?;
        let read_modes = runtime.orc_read_modes();
        let write_defaults = runtime.orc_write_defaults()?;

        let mut state = parent.state();
        let options = state.config_mut();
        options.set_extension(Arc::new(read_defaults));
        options.set_extension(Arc::new(read_modes));
        options.set_extension(Arc::new(write_defaults));
        options.options_mut().execution.time_zone = Some(config.session_timezone.to_string());
        Ok(PlanningContext {
            context: SessionContext::new_with_state(state),
            config: Arc::new(config),
        })
    }
}

#[cfg(test)]
#[path = "planning_tests.rs"]
mod tests;
