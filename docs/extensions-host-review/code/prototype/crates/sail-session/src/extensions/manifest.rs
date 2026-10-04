use std::collections::HashSet;

use datafusion_common::{Result, plan_err};
use serde::Deserialize;

/// Python metadata is checked before touching any native capsule layout.
#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct Manifest {
    pub name: String,
    pub version: String,
    pub api_version: u32,
    pub datafusion_version: String,
    pub arrow_version: String,
    pub placement: String,
    /// A driver-native session quota prepaid from the host's DataFusion pool.
    #[serde(default)]
    pub memory_bytes: Option<usize>,
    pub relation_types: Vec<RelationType>,
}

#[derive(Debug, Deserialize)]
#[serde(deny_unknown_fields)]
pub(super) struct RelationType {
    pub type_url: String,
    pub accepts_bare: bool,
    pub min_inputs: usize,
    pub max_inputs: usize,
}

impl Manifest {
    pub fn validate(&self) -> Result<()> {
        if self.name.is_empty() || self.version.is_empty() {
            return plan_err!("extension name and version must not be empty");
        }
        if self.api_version != 1
            || self.datafusion_version != "55.1.0"
            || self.arrow_version != "59.3.0"
        {
            return plan_err!(
                "extension {} build mismatch: host api=1 DataFusion=55.1.0 Arrow=59.3.0; package api={} DataFusion={} Arrow={}",
                self.name,
                self.api_version,
                self.datafusion_version,
                self.arrow_version
            );
        }
        if !matches!(self.placement.as_str(), "driver" | "any") {
            return plan_err!(
                "extension {} has unsupported placement {}",
                self.name,
                self.placement
            );
        }
        if let Some(bytes) = self.memory_bytes
            && (bytes == 0 || self.placement != "driver")
        {
            return plan_err!(
                "extension {} memory_bytes must be positive and placement must be driver",
                self.name
            );
        }
        let mut urls = HashSet::new();
        for relation in &self.relation_types {
            if relation.type_url.is_empty()
                || relation.min_inputs > relation.max_inputs
                || relation.max_inputs > 16
                || !urls.insert(&relation.type_url)
            {
                return plan_err!(
                    "extension {} has invalid or duplicate relation type {}",
                    self.name,
                    relation.type_url
                );
            }
        }
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn valid() -> Manifest {
        Manifest {
            name: "fixture".into(),
            version: "1".into(),
            api_version: 1,
            datafusion_version: "55.1.0".into(),
            arrow_version: "59.3.0".into(),
            placement: "driver".into(),
            memory_bytes: None,
            relation_types: vec![],
        }
    }

    #[test]
    fn validates_before_native_layout_access() {
        assert!(valid().validate().is_ok());
        let mut manifest = valid();
        manifest.datafusion_version = "54.1.0".into();
        assert!(
            matches!(manifest.validate(), Err(error) if error.to_string().contains("fixture") && error.to_string().contains("55.1.0") && error.to_string().contains("54.1.0"))
        );
    }

    #[test]
    fn rejects_unknown_fields_and_bad_bounds() {
        assert!(serde_json::from_str::<Manifest>(r#"{"future_layout":2}"#).is_err());
        let mut manifest = valid();
        manifest.relation_types.push(RelationType {
            type_url: "x".into(),
            accepts_bare: false,
            min_inputs: 2,
            max_inputs: 1,
        });
        assert!(manifest.validate().is_err());
    }

    #[test]
    fn native_session_quota_requires_a_positive_driver_only_cap() {
        let mut manifest = valid();
        manifest.memory_bytes = Some(64);
        assert!(manifest.validate().is_ok());
        manifest.memory_bytes = Some(0);
        assert!(manifest.validate().is_err());
        manifest.memory_bytes = Some(64);
        manifest.placement = "any".into();
        assert!(manifest.validate().is_err());
    }
}
