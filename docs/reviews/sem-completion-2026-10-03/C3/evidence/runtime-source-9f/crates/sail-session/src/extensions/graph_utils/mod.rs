//! Opt-in, host-owned storage utilities for relational graph clients.
//!
//! This is a compiled-in adapter: object-store credentials/runtime never cross
//! the native wheel interface. The ordinary scalar codec handles its functions.
#[cfg(test)]
mod cleanup_tests;
mod functions;
mod local;
#[cfg(all(test, unix))]
mod local_tests;
mod plan;
mod storage;
#[cfg(test)]
mod tests;

use std::sync::Arc;

use datafusion::execution::runtime_env::RuntimeEnv;
use datafusion::prelude::SessionConfig;
use datafusion_common::{Result, plan_err};
use datafusion_expr::ScalarUDF;
use sail_common_datafusion::connect_extension::ConnectExtensionRegistry;
use sail_common_datafusion::driver_extension::DriverExtensionRegistry;
pub(crate) use storage::GraphRuns;

pub(super) mod proto {
    include!(concat!(env!("OUT_DIR"), "/gf.utils.v1.rs"));
}

pub(super) const TYPE_URL: &str = "type.googleapis.com/gf.utils.v1.Request";

pub(super) fn register(
    config: &mut SessionConfig,
    runtime: &Arc<RuntimeEnv>,
    registry: &mut ConnectExtensionRegistry,
    driver: Option<Arc<DriverExtensionRegistry>>,
) -> Result<Vec<ScalarUDF>> {
    let root = match std::env::var("SAIL_GRAPH_UTILS_ROOT") {
        Ok(root) if !root.is_empty() => root,
        Ok(_) => return plan_err!("SAIL_GRAPH_UTILS_ROOT must be a nonempty absolute URI"),
        Err(std::env::VarError::NotPresent) => return Ok(vec![]),
        Err(error) => return plan_err!("SAIL_GRAPH_UTILS_ROOT: {error}"),
    };
    let runs = Arc::new(GraphRuns::new(runtime, &root)?);
    registry.register(
        TYPE_URL.into(),
        true,
        0,
        0,
        Arc::new(plan::Handler {
            runs: runs.clone(),
            driver,
        }),
    )?;
    config.set_extension(runs);
    functions::register()
}

pub(super) fn register_worker_functions() -> Result<()> {
    // Workers need no filesystem capability or configured driver root. The
    // function identity is versioned with its bit-level implementation contract.
    functions::register()?;
    Ok(())
}
