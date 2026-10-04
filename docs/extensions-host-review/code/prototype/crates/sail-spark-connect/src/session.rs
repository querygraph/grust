use std::collections::HashMap;
use std::fmt::Debug;
use std::sync::{Arc, Mutex};
use std::time::Duration;

use datafusion::execution::SendableRecordBatchStream;
use datafusion::logical_expr::StringifiedPlan;
use sail_common::utils::datetime::get_system_timezone;
use sail_common_datafusion::extension::SessionExtension;
use sail_common_datafusion::session::lifecycle::SessionResource;
use sail_plan::config::PlanConfig;

use crate::config::{ConfigKeyValue, SparkRuntimeConfig};
use crate::error::{SparkError, SparkResult, SparkThrowable};
use crate::executor::Executor;
use crate::spark::config::SparkConfigKey;
use crate::streaming::{
    StreamingQuery, StreamingQueryAwaitHandle, StreamingQueryAwaitHandleSet, StreamingQueryId,
    StreamingQueryManager, StreamingQueryStatus,
};

#[derive(Debug, Clone)]
pub(crate) struct SparkSessionOptions {
    pub execution_heartbeat_interval: Duration,
}

/// A Spark session extension to the DataFusion [`SessionContext`].
///
/// [`SessionContext`]: datafusion::prelude::SessionContext
pub(crate) struct SparkSession {
    session_id: String,
    user_id: String,
    options: SparkSessionOptions,
    state: Mutex<SparkSessionState>,
}

impl Debug for SparkSession {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("SparkSession")
            .field("session_id", &self.session_id)
            .field("user_id", &self.user_id)
            .field("options", &self.options)
            .finish()
    }
}

impl SessionExtension for SparkSession {
    fn name() -> &'static str {
        "spark session"
    }
}

#[tonic::async_trait]
impl SessionResource for SparkSession {
    async fn stop(&self) -> datafusion::common::Result<()> {
        let executors = {
            let mut state = self.state.lock().map_err(|error| {
                datafusion::common::DataFusionError::Execution(error.to_string())
            })?;
            state.stopped = true;
            // Dropping streaming query signals also cancels their producers.
            state.streaming_queries = StreamingQueryManager::new();
            state
                .executors
                .drain()
                .map(|(_, executor)| executor)
                .collect::<Vec<_>>()
        };
        let mut failure = None;
        for executor in executors {
            if let Err(error) = executor.interrupt().await {
                failure = Some(datafusion::common::DataFusionError::Execution(
                    error.to_string(),
                ));
            }
        }
        failure.map_or(Ok(()), Err)
    }
}

impl SparkSession {
    pub(crate) fn try_new(
        session_id: String,
        user_id: String,
        options: SparkSessionOptions,
    ) -> SparkResult<Self> {
        let extension = Self {
            session_id,
            user_id,
            options,
            state: Mutex::new(SparkSessionState::try_new()?),
        };
        extension.set_config(vec![ConfigKeyValue {
            key: SparkConfigKey::SPARK_SQL_SESSION_TIME_ZONE.to_string(),
            value: Some(get_system_timezone()?),
        }])?;
        Ok(extension)
    }

    pub(crate) fn session_id(&self) -> &str {
        &self.session_id
    }

    pub(crate) fn user_id(&self) -> &str {
        &self.user_id
    }

    pub(crate) fn options(&self) -> &SparkSessionOptions {
        &self.options
    }

    pub(crate) fn plan_config(&self) -> SparkResult<Arc<PlanConfig>> {
        let state = self.state.lock()?;
        let mut config = PlanConfig::try_from(&state.config)?;
        config.session_user_id = self.user_id().to_string();
        Ok(Arc::new(config))
    }

    pub(crate) fn get_config(&self, keys: Vec<String>) -> SparkResult<Vec<ConfigKeyValue>> {
        let state = self.state.lock()?;
        keys.into_iter()
            .map(|key| {
                let value = state.config.get(&key)?.map(|v| v.to_string());
                Ok(ConfigKeyValue { key, value })
            })
            .collect::<SparkResult<Vec<_>>>()
    }

    pub(crate) fn get_config_option(&self, keys: Vec<String>) -> SparkResult<Vec<ConfigKeyValue>> {
        let state = self.state.lock()?;
        let kv = keys
            .into_iter()
            .map(|key| {
                let value = state.config.get_option(&key).map(|x| x.to_string());
                ConfigKeyValue { key, value }
            })
            .collect();
        Ok(kv)
    }

    pub(crate) fn get_config_with_default(
        &self,
        kv: Vec<ConfigKeyValue>,
    ) -> SparkResult<Vec<ConfigKeyValue>> {
        let state = self.state.lock()?;
        let kv = kv
            .into_iter()
            .map(|ConfigKeyValue { key, value }| {
                let value = state
                    .config
                    .get_with_default(&key, value.as_deref())
                    .map(|x| x.to_string());
                ConfigKeyValue { key, value }
            })
            .collect();
        Ok(kv)
    }

    pub(crate) fn set_config(&self, kv: Vec<ConfigKeyValue>) -> SparkResult<()> {
        let mut state = self.state.lock()?;
        for ConfigKeyValue { key, value } in kv {
            if let Some(value) = value {
                state.config.set(key, value)?;
            } else {
                return Err(SparkError::invalid(format!(
                    "value is required for configuration: {key}"
                )));
            }
        }
        Ok(())
    }

    pub(crate) fn unset_config(&self, keys: Vec<String>) -> SparkResult<()> {
        let mut state = self.state.lock()?;
        for key in keys {
            state.config.unset(&key)?
        }
        Ok(())
    }

    pub(crate) fn get_all_config(&self, prefix: Option<&str>) -> SparkResult<Vec<ConfigKeyValue>> {
        let state = self.state.lock()?;
        state.config.get_all(prefix)
    }

    pub(crate) fn get_config_warnings(&self, kv: &[ConfigKeyValue]) -> SparkResult<Vec<String>> {
        let state = self.state.lock()?;
        Ok(state.config.get_warnings(kv))
    }

    pub(crate) fn get_config_warnings_by_keys(&self, keys: &[String]) -> SparkResult<Vec<String>> {
        let state = self.state.lock()?;
        Ok(state.config.get_warnings_by_keys(keys))
    }

    pub(crate) fn is_config_modifiable(&self, key: &str) -> SparkResult<bool> {
        let state = self.state.lock()?;
        Ok(state.config.is_modifiable(key))
    }

    pub(crate) fn add_executor(&self, executor: Executor) -> SparkResult<()> {
        let mut state = self.state.lock()?;
        let id = executor.metadata.operation_id.clone();
        if state.stopped {
            return Err(SparkError::OperationInterrupted(id));
        }
        state.executors.insert(id, Arc::new(executor));
        Ok(())
    }

    pub(crate) fn get_executor(&self, id: &str) -> SparkResult<Option<Arc<Executor>>> {
        let state = self.state.lock()?;
        Ok(state.executors.get(id).cloned())
    }

    pub(crate) fn remove_executor(&self, id: &str) -> SparkResult<Option<Arc<Executor>>> {
        let mut state = self.state.lock()?;
        Ok(state
            .executors
            .remove_entry(id)
            .map(|(_, executor)| executor))
    }

    pub(crate) fn all_executors(&self) -> SparkResult<Vec<Arc<Executor>>> {
        let state = self.state.lock()?;
        Ok(state.executors.values().cloned().collect())
    }

    pub(crate) fn executors_by_tag(&self, tag: &str) -> SparkResult<Vec<Arc<Executor>>> {
        let state = self.state.lock()?;
        Ok(state
            .executors
            .values()
            .filter(|executor| executor.metadata.tags.iter().any(|value| value == tag))
            .cloned()
            .collect())
    }

    pub(crate) fn start_streaming_query(
        &self,
        name: String,
        info: Vec<StringifiedPlan>,
        stream: SendableRecordBatchStream,
    ) -> SparkResult<StreamingQueryId> {
        if !stream.schema().fields().is_empty() {
            return Err(SparkError::invalid(
                "streaming query must write data to a sink",
            ));
        }
        // Here we always generate new query ID and run ID regardless of whether the query
        // is started from a checkpoint. This may be different from the Spark behavior.
        let id = StreamingQueryId {
            query_id: uuid::Uuid::new_v4().to_string(),
            run_id: uuid::Uuid::new_v4().to_string(),
        };
        let mut state = self.state.lock()?;
        if state.stopped {
            return Err(SparkError::OperationInterrupted(self.session_id.clone()));
        }
        let query = StreamingQuery::new(name, info, stream);
        state.streaming_queries.add_query(id.clone(), query);
        Ok(id)
    }

    pub(crate) fn stop_streaming_query(&self, id: &StreamingQueryId) -> SparkResult<()> {
        let mut state = self.state.lock()?;
        state.streaming_queries.stop_query(id)?;
        Ok(())
    }

    pub(crate) fn explain_streaming_query(
        &self,
        id: &StreamingQueryId,
        extended: bool,
    ) -> SparkResult<String> {
        let state = self.state.lock()?;
        state.streaming_queries.explain_query(id, extended)
    }

    pub(crate) fn get_streaming_query_status(
        &self,
        id: &StreamingQueryId,
    ) -> SparkResult<StreamingQueryStatus> {
        let state = self.state.lock()?;
        state.streaming_queries.get_query_status(id)
    }

    pub(crate) fn get_streaming_query_exception(
        &self,
        id: &StreamingQueryId,
    ) -> SparkResult<Option<SparkThrowable>> {
        let state = self.state.lock()?;
        state.streaming_queries.get_query_error(id)
    }

    pub(crate) fn await_streaming_query(
        &self,
        id: &StreamingQueryId,
    ) -> SparkResult<Option<StreamingQueryAwaitHandle>> {
        let state = self.state.lock()?;
        state.streaming_queries.await_query(id)
    }

    pub(crate) fn await_streaming_queries(&self) -> SparkResult<StreamingQueryAwaitHandleSet> {
        let state = self.state.lock()?;
        state.streaming_queries.await_queries()
    }

    pub(crate) fn list_active_streaming_queries(
        &self,
    ) -> SparkResult<Vec<(StreamingQueryId, StreamingQueryStatus)>> {
        let state = self.state.lock()?;
        Ok(state.streaming_queries.list_active_queries())
    }

    pub(crate) fn find_streaming_query_by_query_id(
        &self,
        query_id: &str,
    ) -> SparkResult<(StreamingQueryId, StreamingQueryStatus)> {
        let state = self.state.lock()?;
        state.streaming_queries.find_query_by_query_id(query_id)
    }

    pub(crate) fn reset_terminated_streaming_queries(&self) -> SparkResult<()> {
        let mut state = self.state.lock()?;
        state.streaming_queries.reset_stopped_queries();
        Ok(())
    }
}

struct SparkSessionState {
    stopped: bool,
    config: SparkRuntimeConfig,
    executors: HashMap<String, Arc<Executor>>,
    streaming_queries: StreamingQueryManager,
}

impl SparkSessionState {
    fn try_new() -> SparkResult<Self> {
        Ok(Self {
            stopped: false,
            config: SparkRuntimeConfig::try_new()?,
            executors: HashMap::new(),
            streaming_queries: StreamingQueryManager::new(),
        })
    }
}
