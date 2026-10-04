use std::sync::Arc;

use datafusion::common::Result;

use crate::extension::SessionExtension;

/// Protocol-owned operations can retain task contexts containing their session.
/// Explicit teardown breaks those ownership cycles before a session is removed.
#[tonic::async_trait]
pub trait SessionResource: Send + Sync + 'static {
    async fn stop(&self) -> Result<()>;
}

pub struct SessionLifecycle {
    resource: Arc<dyn SessionResource>,
}

impl SessionLifecycle {
    pub fn new(resource: Arc<dyn SessionResource>) -> Self {
        Self { resource }
    }

    pub async fn stop(&self) -> Result<()> {
        self.resource.stop().await
    }
}

impl SessionExtension for SessionLifecycle {
    fn name() -> &'static str {
        "SessionLifecycle"
    }
}
