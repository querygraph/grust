use datafusion::physical_plan::empty::EmptyExec;
use datafusion::prelude::{SessionConfig, SessionContext};

use super::*;

#[derive(Debug)]
struct Binding(Arc<dyn ExecutionPlan>);
impl DriverExtensionBinding for Binding {
    fn materialize(
        &self,
        _: &[Arc<dyn ExecutionPlan>],
        _: Arc<TaskContext>,
    ) -> Result<Arc<dyn ExecutionPlan>> {
        Ok(self.0.clone())
    }
}

#[test]
fn driver_extension_codec_binds_only_live_plans_in_the_original_session() -> Result<()> {
    let registry = Arc::new(DriverExtensionRegistry::default());
    let context =
        SessionContext::new_with_config(SessionConfig::new().with_extension(registry.clone()))
            .task_ctx();
    let empty: Arc<dyn ExecutionPlan> =
        Arc::new(EmptyExec::new(Arc::new(arrow_schema::Schema::empty())));
    let bound = Arc::new(BoundDriverPlan {
        descriptor: DriverDescriptor {
            owner: "fixture@1:digest".into(),
            plan_id: "incarnation:operation".into(),
        },
        properties: empty.properties().clone(),
        input_schemas: vec![],
        binding: Arc::new(Binding(empty.clone())),
    });
    registry.register(&bound)?;
    let exec = DriverExtensionExec::new(bound.clone(), vec![])?;
    let mut bytes = vec![];
    exec.encode(&mut bytes)?;
    let decoded = DriverExtensionExec::decode(&bytes, &[], &context)?;
    assert_eq!(decoded.name(), "DriverExtensionExec");
    assert!(DriverExtensionExec::decode(&bytes, &[empty], &context).is_err());
    assert!(DriverExtensionExec::decode(&bytes, &[], &TaskContext::default()).is_err());
    let other = SessionContext::new_with_config(
        SessionConfig::new().with_extension(Arc::new(DriverExtensionRegistry::default())),
    )
    .task_ctx();
    assert!(DriverExtensionExec::decode(&bytes, &[], &other).is_err());
    let mut forged = DRIVER_CODEC_PREFIX.to_vec();
    serde_json::to_writer(
        &mut forged,
        &DriverDescriptor {
            owner: "other".into(),
            plan_id: bound.descriptor.plan_id.clone(),
        },
    )
    .map_err(|e| plan_datafusion_err!("{e}"))?;
    assert!(DriverExtensionExec::decode(&forged, &[], &context).is_err());
    drop(decoded);
    drop(exec);
    drop(bound);
    assert!(DriverExtensionExec::decode(&bytes, &[], &context).is_err());
    assert!(DriverExtensionExec::decode(&vec![0; 8193], &[], &context).is_err());
    Ok(())
}
