use datafusion_common::{Result, not_impl_err};
use orc_rust::compression::CompressionType;

use crate::error::{DataSourceError, DataSourceResult};

/// Spark 4.2.1's ORC codec names, independent of native encoder availability.
#[derive(Debug, Default, Clone, Copy, PartialEq, Eq)]
pub enum OrcWriteCompression {
    None,
    Zlib,
    Snappy,
    Lzo,
    Lz4,
    #[default]
    Zstd,
    Brotli,
}

impl OrcWriteCompression {
    /// Resolve after merging option layers by key. Spark gives `compression`
    /// priority over `orc.compress`, even when the latter is a later layer.
    /// Only the chosen value is validated; operation values are not trimmed.
    pub fn resolve(
        compression: Option<&str>,
        orc_compress: Option<&str>,
        session_default: Option<&str>,
    ) -> DataSourceResult<Self> {
        let (key, value) = if let Some(value) = compression {
            ("compression", value)
        } else if let Some(value) = orc_compress {
            ("orc.compress", value)
        } else {
            (
                "spark.sql.orc.compression.codec",
                session_default.unwrap_or("zstd"),
            )
        };
        match value.to_lowercase().as_str() {
            "none" | "uncompressed" => Ok(Self::None),
            "zlib" => Ok(Self::Zlib),
            "snappy" => Ok(Self::Snappy),
            "lzo" => Ok(Self::Lzo),
            "lz4" => Ok(Self::Lz4),
            "zstd" => Ok(Self::Zstd),
            "brotli" => Ok(Self::Brotli),
            _ => Err(DataSourceError::InvalidOption {
                key: key.to_string(),
                value: value.to_string(),
                cause: Some(
                    "expected none, uncompressed, zlib, snappy, lzo, lz4, zstd or brotli".into(),
                ),
            }),
        }
    }

    /// CompressionKind name used by ORC. This is internal block compression.
    pub fn orc_name(self) -> &'static str {
        match self {
            Self::None => "NONE",
            Self::Zlib => "ZLIB",
            Self::Snappy => "SNAPPY",
            Self::Lzo => "LZO",
            Self::Lz4 => "LZ4",
            Self::Zstd => "ZSTD",
            Self::Brotli => "BROTLI",
        }
    }

    /// Check native capability before constructing an encoder or opening output.
    pub fn native_compression(self) -> Result<Option<CompressionType>> {
        match self {
            Self::None => Ok(None),
            Self::Zlib => Ok(Some(CompressionType::Zlib)),
            Self::Snappy => Ok(Some(CompressionType::Snappy)),
            Self::Lz4 => Ok(Some(CompressionType::Lz4)),
            Self::Zstd => Ok(Some(CompressionType::Zstd)),
            Self::Lzo | Self::Brotli => {
                not_impl_err!(
                    "ORC {} compression is not supported by the native writer",
                    self.orc_name()
                )
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use std::sync::Arc;

    use arrow::datatypes::{DataType, Field, Schema};
    use orc_rust::{ArrowReaderBuilder, ArrowWriterBuilder};

    use super::*;

    #[test]
    fn spark_names_aliases_case_and_invalid_values() -> DataSourceResult<()> {
        for (name, expected) in [
            ("none", "NONE"),
            ("UNCOMPRESSED", "NONE"),
            ("ZlIb", "ZLIB"),
            ("snappy", "SNAPPY"),
            ("lzo", "LZO"),
            ("lz4", "LZ4"),
            ("zstd", "ZSTD"),
            ("brotli", "BROTLI"),
        ] {
            assert_eq!(
                OrcWriteCompression::resolve(Some(name), None, None)?.orc_name(),
                expected
            );
        }
        for value in ["", "gzip", "deflate", " zstd", "zstd ", "\0zstd\0"] {
            let error = OrcWriteCompression::resolve(Some(value), None, None);
            assert!(
                matches!(error, Err(DataSourceError::InvalidOption { key, value: original, .. }) if key == "compression" && original == value)
            );
        }
        Ok(())
    }

    #[test]
    fn priority_selects_before_validation() -> DataSourceResult<()> {
        assert_eq!(
            OrcWriteCompression::resolve(None, None, None)?,
            OrcWriteCompression::Zstd
        );
        assert_eq!(
            OrcWriteCompression::resolve(Some("none"), Some("invalid"), Some("invalid"))?,
            OrcWriteCompression::None
        );
        assert_eq!(
            OrcWriteCompression::resolve(None, Some("snappy"), Some("invalid"))?,
            OrcWriteCompression::Snappy
        );
        assert_eq!(
            OrcWriteCompression::resolve(None, None, Some("lz4"))?,
            OrcWriteCompression::Lz4
        );
        assert!(
            matches!(OrcWriteCompression::resolve(Some(""), Some("zstd"), None), Err(DataSourceError::InvalidOption { key, .. }) if key == "compression")
        );
        assert!(
            matches!(OrcWriteCompression::resolve(None, Some(""), Some("zstd")), Err(DataSourceError::InvalidOption { key, .. }) if key == "orc.compress")
        );
        Ok(())
    }

    #[test]
    fn recognized_unavailable_codecs_report_capability_errors() -> Result<()> {
        for codec in [OrcWriteCompression::Lzo, OrcWriteCompression::Brotli] {
            assert!(matches!(
                codec.native_compression(),
                Err(datafusion_common::DataFusionError::NotImplemented(_))
            ));
        }
        Ok(())
    }

    #[test]
    fn native_supported_codecs_write_and_read_empty_orc_files() -> Result<()> {
        for codec in [
            OrcWriteCompression::None,
            OrcWriteCompression::Zlib,
            OrcWriteCompression::Snappy,
            OrcWriteCompression::Lz4,
            OrcWriteCompression::Zstd,
        ] {
            let schema = Arc::new(Schema::new(vec![Field::new("id", DataType::Int64, true)]));
            let mut bytes = vec![];
            let mut builder = ArrowWriterBuilder::new(&mut bytes, schema);
            if let Some(native) = codec.native_compression()? {
                builder = builder.with_compression(native);
            }
            builder
                .try_build()
                .map_err(|e| datafusion_common::DataFusionError::External(Box::new(e)))?
                .close()
                .map_err(|e| datafusion_common::DataFusionError::External(Box::new(e)))?;
            assert!(bytes.starts_with(b"ORC"));
            let reader = ArrowReaderBuilder::try_new(bytes::Bytes::from(bytes))
                .map_err(|e| datafusion_common::DataFusionError::External(Box::new(e)))?;
            let stored = reader
                .file_metadata()
                .compression()
                .map(|c| format!("{}", c.compression_type()).to_uppercase());
            assert_eq!(stored.as_deref().unwrap_or("NONE"), codec.orc_name());
            assert_eq!(reader.build().count(), 0);
        }
        Ok(())
    }
}
