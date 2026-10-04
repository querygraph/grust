use std::sync::Arc;

use datafusion::common::Result;
use datafusion::common::config::ConfigNonZeroUsize;
use datafusion::execution::SessionStateBuilder;
use datafusion::prelude::{SessionConfig, SessionContext};
use sail_common::config::AppConfig;
use sail_common::runtime::RuntimeHandle;
use sail_common_datafusion::session::repartition::RepartitionBufferConfig;
use sail_delta_lake::session_extension::DeltaTableCache;

use crate::runtime::{MemoryResourceDomain, RuntimeEnvFactory};
use crate::session_factory::SessionFactory;

pub struct WorkerSessionFactory {
    resource_domain: Option<MemoryResourceDomain>,
    runtime_env: RuntimeEnvFactory,
    batch_size: usize,
    repartition_buffer_size: usize,
}

impl WorkerSessionFactory {
    pub fn new(config: Arc<AppConfig>, runtime: RuntimeHandle) -> Self {
        let batch_size = config.execution.batch_size;
        let repartition_buffer_size = config.cluster.task_stream_buffer;
        let resource_domain = (std::env::var("SAIL_EXPERIMENTAL_EXTENSIONS").as_deref() == Ok("1"))
            .then(|| MemoryResourceDomain::new(&config.runtime.memory_pool));
        let runtime_env = RuntimeEnvFactory::new(config, runtime.clone());
        Self {
            resource_domain,
            runtime_env,
            batch_size,
            repartition_buffer_size,
        }
    }
    pub fn with_resource_domain(mut self, domain: Option<MemoryResourceDomain>) -> Self {
        self.resource_domain = domain;
        self
    }
}

impl SessionFactory<()> for WorkerSessionFactory {
    fn create(&mut self, _info: ()) -> Result<SessionContext> {
        if std::env::var("SAIL_EXPERIMENTAL_EXTENSIONS").as_deref() == Ok("1") {
            crate::extensions::load_worker_extensions()?;
        }
        let runtime = self.runtime_env.create(self.resource_domain.as_ref(), Ok)?;
        // We still add default features for the worker session
        // since we need built-in functions to be available for the codec
        // when decoding the execution plan.
        let mut config = SessionConfig::default()
            .with_extension(Arc::new(DeltaTableCache::default()))
            .with_extension(Arc::new(RepartitionBufferConfig::new(
                self.repartition_buffer_size,
            )));
        config.options_mut().execution.batch_size = ConfigNonZeroUsize::try_new(self.batch_size)?;
        let state = SessionStateBuilder::new()
            .with_config(config)
            .with_runtime_env(runtime)
            .with_default_features()
            .build();
        let session = SessionContext::new_with_state(state);
        Ok(session)
    }
}
