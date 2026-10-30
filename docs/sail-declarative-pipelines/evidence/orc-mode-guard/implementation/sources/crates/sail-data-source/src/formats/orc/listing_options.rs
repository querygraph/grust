use datafusion::catalog::Session;
use sail_common_datafusion::datasource::OptionLayer;
use sail_common_datafusion::extension::SessionExtension;

use crate::error::{DataSourceError, DataSourceResult};
use crate::options::r#gen::{OrcListingReadOptions, OrcListingReadPartialOptions};
use crate::options::{BuildPartialOptions, PartialOptions, ResolveOptions};

/// Immutable defaults captured by a session configuration snapshot.
///
/// Frontends replace the extension when their configuration changes. Already
/// resolved listing options and earlier session snapshots retain their values.
/// These planning defaults are separate from the physical reader descriptor.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub struct OrcListingSessionDefaults {
    pub merge_schema: bool,
}

impl SessionExtension for OrcListingSessionDefaults {
    fn name() -> &'static str {
        "ORC listing defaults"
    }
}

/// Immutable session modes inspected only when an ORC read is planned.
///
/// Keeping unsupported values here does not reject unrelated workloads that
/// store Spark runtime settings. Read options may override positional evolution,
/// but provider selection comes only from the session implementation setting.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct OrcReadSessionModes {
    pub implementation: String,
    pub force_positional_evolution: bool,
}

impl Default for OrcReadSessionModes {
    fn default() -> Self {
        Self {
            implementation: "native".to_string(),
            force_positional_evolution: false,
        }
    }
}

impl SessionExtension for OrcReadSessionModes {
    fn name() -> &'static str {
        "ORC read modes"
    }
}

impl OrcReadSessionModes {
    fn validate_implementation(&self) -> DataSourceResult<()> {
        let cause = match self.implementation.as_str() {
            "native" => return Ok(()),
            "hive" => "the Hive ORC reader is not supported",
            _ => "expected native or hive",
        };
        Err(DataSourceError::InvalidOption {
            key: "spark.sql.orc.impl".to_string(),
            value: self.implementation.clone(),
            cause: Some(cause.to_string()),
        })
    }
}

impl ResolveOptions for OrcListingReadOptions {
    fn resolve(ctx: &dyn Session, options: Vec<OptionLayer>) -> DataSourceResult<Self> {
        let mut partial = OrcListingReadPartialOptions::initialize();
        if let Some(defaults) = ctx.config().get_extension::<OrcListingSessionDefaults>() {
            partial.merge_schema = Some(defaults.merge_schema);
        }
        if let Some(modes) = ctx.config().get_extension::<OrcReadSessionModes>() {
            modes.validate_implementation()?;
            partial.force_positional_evolution = Some(modes.force_positional_evolution);
        }
        for layer in options {
            partial.merge(layer.build_partial_options()?);
        }
        let options = partial.finalize()?;
        if options.force_positional_evolution {
            return Err(DataSourceError::InvalidOption {
                key: "orc.force.positional.evolution".to_string(),
                value: "true".to_string(),
                cause: Some("forced positional ORC schema evolution is not supported".to_string()),
            });
        }
        Ok(options)
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use datafusion::prelude::{SessionConfig, SessionContext};

    use super::*;
    use crate::error::DataSourceError;
    use crate::options::option_list;

    #[test]
    fn ordinary_sessions_default_to_no_merge_or_glob() -> DataSourceResult<()> {
        let ctx = SessionContext::new();
        let options = OrcListingReadOptions::resolve(&ctx.state(), vec![])?;
        assert!(!options.merge_schema);
        assert_eq!(options.path_glob_filter, None);
        Ok(())
    }

    #[test]
    fn session_defaults_then_layers_preserve_explicit_false_and_empty_glob() -> DataSourceResult<()>
    {
        let config = SessionConfig::new()
            .with_extension(Arc::new(OrcListingSessionDefaults { merge_schema: true }));
        let ctx = SessionContext::new_with_config(config);
        assert!(OrcListingReadOptions::resolve(&ctx.state(), vec![])?.merge_schema);

        let table = || OptionLayer::TablePropertyList {
            items: vec![
                ("option.mergeSchema".into(), "false".into()),
                ("option.path_glob_filter".into(), "table-*.orc".into()),
            ],
        };
        let options = OrcListingReadOptions::resolve(&ctx.state(), vec![table()])?;
        assert!(!options.merge_schema);
        assert_eq!(options.path_glob_filter.as_deref(), Some("table-*.orc"));

        let options = OrcListingReadOptions::resolve(
            &ctx.state(),
            vec![
                table(),
                option_list(&[
                    ("MERGE_SCHEMA", "TrUe"),
                    ("pathGlobFilter", "operation-*.orc"),
                ]),
                option_list(&[("mergeSchema", "false"), ("path_glob_filter", "")]),
            ],
        )?;
        assert!(!options.merge_schema);
        assert_eq!(options.path_glob_filter, None);
        Ok(())
    }

    #[test]
    fn invalid_merge_values_report_the_option_and_original_value() {
        let ctx = SessionContext::new();
        for value in [
            "",
            "yes",
            "1",
            "0",
            " true ",
            "\0true\0",
            "\u{a0}true\u{a0}",
        ] {
            let result = OrcListingReadOptions::resolve(
                &ctx.state(),
                vec![option_list(&[("mergeSchema", value)])],
            );
            assert!(matches!(result,
                Err(DataSourceError::InvalidOption { key, value: invalid, .. })
                    if key == "mergeSchema" && invalid == value
            ));
        }
    }

    #[test]
    fn strict_merge_booleans_follow_scala_case_matching() -> DataSourceResult<()> {
        let ctx = SessionContext::new();
        for (value, expected) in [("TrUe", true), ("FALSE", false), ("FALſE", false)] {
            let options = OrcListingReadOptions::resolve(
                &ctx.state(),
                vec![option_list(&[("mergeSchema", value)])],
            )?;
            assert_eq!(options.merge_schema, expected);
        }
        Ok(())
    }

    fn mode_context(implementation: &str, force_positional_evolution: bool) -> SessionContext {
        SessionContext::new_with_config(SessionConfig::new().with_extension(Arc::new(
            OrcReadSessionModes {
                implementation: implementation.to_string(),
                force_positional_evolution,
            },
        )))
    }

    #[test]
    fn implementation_is_an_exact_session_choice_at_the_read_boundary() -> DataSourceResult<()> {
        let native = mode_context("native", false);
        OrcListingReadOptions::resolve(&native.state(), vec![])?;
        for implementation in ["hive", "NATIVE", " native ", "unknown"] {
            let ctx = mode_context(implementation, false);
            assert!(matches!(
                OrcListingReadOptions::resolve(&ctx.state(), vec![]),
                Err(DataSourceError::InvalidOption { key, value, .. })
                    if key == "spark.sql.orc.impl" && value == implementation
            ));
        }
        Ok(())
    }

    #[test]
    fn operation_implementation_does_not_select_the_provider() -> DataSourceResult<()> {
        let native = mode_context("native", false);
        OrcListingReadOptions::resolve(
            &native.state(),
            vec![option_list(&[("spark.sql.orc.impl", "hive")])],
        )?;
        let hive = mode_context("hive", false);
        assert!(
            OrcListingReadOptions::resolve(
                &hive.state(),
                vec![option_list(&[("spark.sql.orc.impl", "native")])],
            )
            .is_err()
        );
        Ok(())
    }

    #[test]
    fn forced_position_is_checked_after_case_insensitive_layer_overrides() -> DataSourceResult<()> {
        let ctx = mode_context("native", true);
        assert!(OrcListingReadOptions::resolve(&ctx.state(), vec![]).is_err());
        let table = || OptionLayer::TablePropertyList {
            items: vec![(
                "option.ORC.FORCE.POSITIONAL.EVOLUTION".into(),
                "false".into(),
            )],
        };
        OrcListingReadOptions::resolve(&ctx.state(), vec![table()])?;
        assert!(
            OrcListingReadOptions::resolve(
                &ctx.state(),
                vec![
                    table(),
                    option_list(&[("orc.force.positional.evolution", "TrUe")]),
                ],
            )
            .is_err()
        );
        let options = OrcListingReadOptions::resolve(
            &ctx.state(),
            vec![option_list(&[("ORC.FORCE.POSITIONAL.EVOLUTION", "false")])],
        )?;
        assert!(!options.force_positional_evolution);
        Ok(())
    }

    #[test]
    fn forced_position_uses_orc_java_boolean_and_no_invented_key_aliases() -> DataSourceResult<()> {
        let ctx = mode_context("native", true);
        for value in ["false", "FALSE", " true ", "yes", "1", ""] {
            let options = OrcListingReadOptions::resolve(
                &ctx.state(),
                vec![option_list(&[("orc.force.positional.evolution", value)])],
            )?;
            assert!(!options.force_positional_evolution);
        }
        let native = mode_context("native", false);
        OrcListingReadOptions::resolve(
            &native.state(),
            vec![option_list(&[
                ("spark.hadoop.orc.force.positional.evolution", "true"),
                ("forcePositionalEvolution", "true"),
            ])],
        )?;
        Ok(())
    }
}
