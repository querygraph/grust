        let (plan, projections) =
            self.rewrite_projection::<TableInputRewriter>(plan, projections, state)?;
        let input_names = projections
            .iter()
            .map(|e| e.name.clone().one())
            .collect::<datafusion_common::Result<_>>()?;
        let projections = self.rewrite_named_expressions(projections, state)?;
        let input_types = projections
            .iter()
            .map(|e| e.get_type(plan.schema()))
            .collect::<datafusion_common::Result<Vec<_>>>()?;

        // Resolve the UDTF return type: use the static type if provided, otherwise call the
        // `analyze` static method on the UDTF to determine the return type dynamically.
        let return_type = match function.return_type {
            Some(rt) => rt,
            None => {
                // Get the argument types (excluding passthrough columns).
                let arg_types = &input_types[passthrough_columns..];
                // Extract literal values from argument expressions.
                // Each projection is wrapped in an Alias after `rewrite_named_expressions`,
                // so we need to unwrap the alias to get the inner expression.
                let literal_evaluator = LiteralEvaluator::new();
                let arg_literals: Vec<Option<ScalarValue>> = projections[passthrough_columns..]
                    .iter()
                    .map(|e| {
                        let inner = match e {
                            Expr::Alias(alias) => alias.expr.as_ref(),
                            other => other,
                        };
                        if inner.is_volatile() {
                            return None;
                        }
                        literal_evaluator.evaluate(inner).ok()
                    })
                    .collect();
                PySparkUdtfPayload::analyze(
                    &function.python_version,
                    &function.command,
                    function.eval_type,
                    arg_types,
                    &arg_literals,
                    kwargs,
                    &argument_is_tables,
                    self.config.pyspark_udf_config.arrow_use_large_var_types,
                )?
            }
        };

        let payload = PySparkUdtfPayload::build(
