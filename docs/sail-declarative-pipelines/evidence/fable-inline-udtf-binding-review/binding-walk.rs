        plan: &spec::QueryPlan,
        cte_scope: &HashSet<String>,
    ) -> Result<(), BindingError> {
        use spec::QueryNode as N;
        match &plan.node {
            N::Read {
                read_type,
                is_streaming,
            } => self.read(read_type, *is_streaming, cte_scope),
            // Leaves without query inputs; literal rows and an inline table
            // function still carry expressions.
            N::LocalRelation { .. }
            | N::CachedLocalRelation { .. }
            | N::CachedRemoteRelation { .. }
            | N::Range(_)
            | N::Empty { .. } => Ok(()),
            N::Values(rows) => rows.iter().try_for_each(|row| self.exprs(row, cte_scope)),
            N::CommonInlineUserDefinedTableFunction(function) => {
                self.exprs(&function.arguments, cte_scope)
            }
            // Constructs whose resolution executes a helper plan.
            N::Tail { .. } => Err(BindingError::Tail),
            N::Pivot(pivot) if pivot.values.is_empty() => Err(BindingError::PivotInference),
            N::StatSummary { .. } => Err(BindingError::StatHelper("summary")),
            N::StatDescribe { .. } => Err(BindingError::StatHelper("describe")),
            N::StatCrosstab { .. } => Err(BindingError::StatHelper("crosstab")),
