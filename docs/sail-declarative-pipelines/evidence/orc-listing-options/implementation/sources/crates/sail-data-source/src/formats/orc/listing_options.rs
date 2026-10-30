use datafusion::catalog::Session;
use sail_common_datafusion::datasource::OptionLayer;
use sail_common_datafusion::extension::SessionExtension;

use crate::error::DataSourceResult;
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

impl ResolveOptions for OrcListingReadOptions {
    fn resolve(ctx: &dyn Session, options: Vec<OptionLayer>) -> DataSourceResult<Self> {
        let mut partial = OrcListingReadPartialOptions::initialize();
        if let Some(defaults) = ctx.config().get_extension::<OrcListingSessionDefaults>() {
            partial.merge_schema = Some(defaults.merge_schema);
        }
        for layer in options {
            partial.merge(layer.build_partial_options()?);
        }
        partial.finalize()
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
}
