//! Inclusive integer range without materializing the full range.

use super::*;

pub(super) fn register(builder: &mut RegistryBuilder) -> Result<()> {
    let mut metadata = definition("tvf.range", "value", ProcedureMode::Table);
    metadata.outputs[0].value_type = ValueType::Integer;
    metadata.streaming = Streaming::Incremental;
    metadata.arguments = [
        ("start", None),
        ("end", None),
        ("step", Some(Value::Int(1))),
    ]
    .into_iter()
    .map(|(name, default)| Argument {
        field: Field {
            name: name.into(),
            value_type: ValueType::Integer,
            nullable: false,
        },
        default,
    })
    .collect();
    builder.register(metadata, Arc::new(RangeProvider))
}

struct RangeProvider;

impl ProcedureProvider for RangeProvider {
    fn open<'a>(
        &'a self,
        args: ValidatedArguments,
        invocation: Invocation<'a>,
    ) -> Result<Box<dyn ProcedureCursor + 'a>> {
        let [Value::Int(start), Value::Int(end), Value::Int(step)] = args.positional() else {
            return Err(ProcedureError::InvalidArguments(
                "range expects integer start, end and step".into(),
            ));
        };
        if *step == 0 {
            return Err(ProcedureError::InvalidArguments(
                "range step must not be zero".into(),
            ));
        }
        // Widen all arithmetic. Even the full i64 domain has a representable
        // i128 count, and incrementing past i64::MAX cannot wrap into output.
        let (start, end, step) = (i128::from(*start), i128::from(*end), i128::from(*step));
        let remaining = if step > 0 && start <= end || step < 0 && start >= end {
            (end - start).abs() / step.abs() + 1
        } else {
            0
        };
        Ok(Box::new(RangeCursor {
            next: start,
            step,
            remaining,
            execution: invocation.execution,
        }))
    }
}

struct RangeCursor<'a> {
    next: i128,
    step: i128,
    remaining: i128,
    execution: &'a ExecutionContext,
}

impl ProcedureCursor for RangeCursor<'_> {
    fn next_batch(&mut self) -> Result<Option<ProcedureBatch>> {
        self.execution.checkpoint()?;
        if self.remaining == 0 {
            return Ok(None);
        }
        let count = usize::try_from(
            self.remaining
                .min(self.execution.limits().batch_rows as i128),
        )
        .map_err(|_| ProcedureError::Numerical("range batch length overflow".into()))?;
        let bytes = count
            .checked_mul(size_of::<Vec<Value>>() + size_of::<Value>())
            .ok_or(ProcedureError::BudgetExceeded {
                resource: "memory",
                limit: self.execution.limits().memory_bytes,
            })?;
        let reservation = self.execution.reserve(bytes)?;
        let mut rows = Vec::new();
        rows.try_reserve_exact(count)?;
        for _ in 0..count {
            self.execution.charge_work(1)?;
            let value = i64::try_from(self.next).map_err(|_| {
                ProcedureError::Numerical("range value exceeds integer domain".into())
            })?;
            let mut row = Vec::new();
            row.try_reserve_exact(1)?;
            row.push(Value::Int(value));
            rows.push(row);
            self.next += self.step;
            self.remaining -= 1;
        }
        Ok(Some(ProcedureBatch::new(rows, reservation)))
    }
}
