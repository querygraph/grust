use std::collections::HashMap;
use std::collections::hash_map::Entry;
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, RwLock};

use datafusion::arrow::datatypes::SchemaRef;
use datafusion::execution::object_store::ObjectStoreUrl;
use datafusion::execution::runtime_env::RuntimeEnv;
use datafusion::physical_expr::{LexOrdering, Partitioning};
use datafusion_common::{DataFusionError, Result, internal_datafusion_err};
use object_store::path::Path;
use sail_common_datafusion::extension::SessionExtension;
use sail_object_store::{
    ResolvedObjectStorePath, delete_object_store_prefix_objects, resolve_object_store_path,
};

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RemoteCheckpointFile {
    pub location: Path,
    pub size: u64,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RemoteCheckpointPartition {
    pub partition: usize,
    pub row_count: u64,
    pub file: Option<RemoteCheckpointFile>,
}

#[derive(Clone, Debug)]
pub struct RemoteCheckpointDescriptor {
    pub relation_id: String,
    pub object_store_url: ObjectStoreUrl,
    pub prefix: Path,
    pub logical_schema: SchemaRef,
    pub storage_schema: SchemaRef,
    pub output_partitioning: Partitioning,
    pub output_ordering: Option<LexOrdering>,
    pub partitions: Vec<RemoteCheckpointPartition>,
}

/// Session-local publication index for complete checkpoints; object-store contents are not
/// reloaded after a process restart.
#[derive(Debug)]
pub struct RemoteCheckpointRegistry {
    path: Option<String>,
    session_id: String,
    closed: AtomicBool,
    relations: RwLock<HashMap<String, Arc<RemoteCheckpointDescriptor>>>,
}

impl RemoteCheckpointRegistry {
    pub fn new(path: Option<String>, session_id: String) -> Self {
        Self {
            path,
            session_id,
            closed: AtomicBool::new(false),
            relations: RwLock::new(HashMap::new()),
        }
    }

    /// Resolve a storage path while admission is open. This is not a lease on
    /// storage effects; callers must separately own and drain those effects.
    pub fn resolve_relation(
        &self,
        runtime_env: &RuntimeEnv,
        relation_id: &str,
    ) -> Result<(ObjectStoreUrl, Path)> {
        if self.closed.load(Ordering::Acquire) {
            return Err(DataFusionError::Plan(
                "checkpoint session is stopping".to_string(),
            ));
        }
        let root = self.resolve_root(runtime_env)?;
        let prefix = self.session_prefix(root.prefix()).join(relation_id);
        Ok((root.object_store_url().clone(), prefix))
    }

    pub fn insert(&self, descriptor: RemoteCheckpointDescriptor) -> Result<()> {
        let relation_id = descriptor.relation_id.clone();
        let mut relations = self.relations.write().map_err(|error| {
            internal_datafusion_err!("checkpoint registry is poisoned: {error}")
        })?;
        // Sealing takes this same lock, so an admitted publication either
        // finishes before the seal or observes the closed registry.
        if self.closed.load(Ordering::Acquire) {
            return Err(DataFusionError::Plan(
                "checkpoint session is stopping".to_string(),
            ));
        }
        match relations.entry(relation_id.clone()) {
            Entry::Occupied(_) => {
                return Err(internal_datafusion_err!(
                    "checkpoint relation already exists: {relation_id}"
                ));
            }
            Entry::Vacant(entry) => {
                entry.insert(Arc::new(descriptor));
            }
        }
        Ok(())
    }

    pub fn get(&self, relation_id: &str) -> Result<Option<Arc<RemoteCheckpointDescriptor>>> {
        let relations = self.relations.read().map_err(|error| {
            internal_datafusion_err!("checkpoint registry is poisoned: {error}")
        })?;
        if self.closed.load(Ordering::Acquire) {
            return Ok(None);
        }
        Ok(relations.get(relation_id).cloned())
    }

    pub async fn cleanup_relation(
        &self,
        runtime_env: &RuntimeEnv,
        object_store_url: &ObjectStoreUrl,
        prefix: &Path,
    ) -> Result<()> {
        let store = runtime_env.object_store(object_store_url)?;
        delete_object_store_prefix_objects(store.as_ref(), prefix).await
    }

    pub async fn cleanup_session(&self, runtime_env: &RuntimeEnv) -> Result<()> {
        self.seal()?;
        if self.path.is_some() {
            let root = self.resolve_root(runtime_env)?;
            delete_object_store_prefix_objects(
                root.store().as_ref(),
                &self.session_prefix(root.prefix()),
            )
            .await?;
        }
        // Retain the closed registry's in-memory descriptors if storage cleanup
        // fails or is canceled. A later explicit cleanup can retry the prefix.
        // This does not fence writes already admitted to the object store.
        self.clear()
    }

    fn resolve_root(&self, runtime_env: &RuntimeEnv) -> Result<ResolvedObjectStorePath> {
        let path = self.path.as_deref().ok_or_else(|| {
            DataFusionError::Plan(
                "checkpoint object-store path is not configured; set execution.checkpoint.path"
                    .to_string(),
            )
        })?;
        resolve_object_store_path(runtime_env, path)
    }

    fn session_prefix(&self, root: &Path) -> Path {
        root.clone().join(self.session_id.as_str())
    }

    fn clear(&self) -> Result<()> {
        let removed = {
            let mut relations = self.relations.write().map_err(|error| {
                internal_datafusion_err!("checkpoint registry is poisoned: {error}")
            })?;
            std::mem::take(&mut *relations)
        };
        drop(removed);
        Ok(())
    }

    fn seal(&self) -> Result<()> {
        let _relations = self.relations.write().map_err(|error| {
            internal_datafusion_err!("checkpoint registry is poisoned: {error}")
        })?;
        self.closed.store(true, Ordering::Release);
        Ok(())
    }
}

impl SessionExtension for RemoteCheckpointRegistry {
    fn name() -> &'static str {
        "remote checkpoint registry"
    }
}

#[cfg(test)]
#[path = "remote_checkpoint_tests.rs"]
mod cleanup_tests;

#[cfg(test)]
#[expect(clippy::expect_used, clippy::unwrap_used)]
mod tests {
    use datafusion::arrow::datatypes::Schema;

    use super::*;

    fn descriptor(relation_id: &str) -> RemoteCheckpointDescriptor {
        let schema = Arc::new(Schema::empty());
        RemoteCheckpointDescriptor {
            relation_id: relation_id.to_string(),
            object_store_url: ObjectStoreUrl::parse("memory://").unwrap(),
            prefix: Path::from("checkpoint"),
            logical_schema: Arc::clone(&schema),
            storage_schema: schema,
            output_partitioning: Partitioning::UnknownPartitioning(1),
            output_ordering: None,
            partitions: vec![],
        }
    }

    #[test]
    fn registry_owns_only_ready_descriptors() -> Result<()> {
        let registry = RemoteCheckpointRegistry::new(None, "session".to_string());
        registry.insert(descriptor("relation"))?;
        assert_eq!(
            registry
                .get("relation")?
                .expect("descriptor must be present")
                .relation_id,
            "relation"
        );
        let original = registry
            .get("relation")?
            .expect("descriptor must be present");
        assert!(registry.insert(descriptor("relation")).is_err());
        let retained = registry
            .get("relation")?
            .expect("descriptor must remain present");
        assert!(Arc::ptr_eq(&original, &retained));
        registry.clear()?;
        assert!(registry.get("relation")?.is_none());
        Ok(())
    }

    #[test]
    fn registry_uses_the_provided_session_id_for_storage_paths() {
        let registry = RemoteCheckpointRegistry::new(None, "session-1".to_string());
        assert_eq!(
            registry.session_prefix(&Path::from("checkpoint")),
            Path::from("checkpoint/session-1")
        );
    }
}
