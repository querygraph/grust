    }

    pub(crate) async fn metadata_delete_paths(
        &self,
        session: &dyn Session,
        predicate: &Expr,
    ) -> Result<Option<Vec<String>>> {
        if self.snapshot.is_none() {
            return Ok(Some(Vec::new()));
        }
        let table_url = Url::parse(&self.table_uri)
            .map_err(|error| datafusion::common::DataFusionError::External(Box::new(error)))?;
        let object_store = get_object_store_from_session(session, &table_url)?;
        let store_ctx = StoreContext::new(object_store, &table_url)?;
        let manifests = self.load_manifest_list(&store_ctx).await?;
        let files = self
            .load_data_files_with_seq(&[], &store_ctx, &manifests)
            .await?;
        let selected = crate::datasource::copy_on_write::select_copy_on_write_files(
