//! Deterministic overload selection; no implicit coercions.
use crate::ResolveError;
use grust_functions::{
    ArgumentType, FunctionDescriptor, FunctionKind, FunctionName, FunctionRegistry, NullSemantics,
    ReturnType,
};
use grust_lpg::LogicalType;
use grust_resolved_plan::query::Expr;
use std::collections::HashMap;
pub fn numeric(ty: &LogicalType) -> bool {
    matches!(
        ty,
        LogicalType::Int32
            | LogicalType::Int64
            | LogicalType::Float32
            | LogicalType::Float64
            | LogicalType::Decimal { .. }
    )
}
pub fn bind(
    registry: &dyn FunctionRegistry,
    name: &FunctionName,
    kind: FunctionKind,
    args: &[Expr],
) -> Result<(FunctionDescriptor, LogicalType, bool), ResolveError> {
    let mut candidates = Vec::new();
    for f in registry.lookup(name, kind) {
        if args.len() < f.signature.arguments.len()
            || (f.signature.variadic.is_none() && args.len() != f.signature.arguments.len())
        {
            continue;
        }
        let mut variables = HashMap::new();
        let mut score = 0;
        let mut valid = true;
        for (i, arg) in args.iter().enumerate() {
            let pattern = f
                .signature
                .arguments
                .get(i)
                .or(f.signature.variadic.as_ref())
                .expect("arity checked");
            match pattern {
                ArgumentType::Exact(expected) => {
                    if arg.ty.as_ref().is_some_and(|ty| ty != expected) {
                        valid = false;
                    }
                    score += 4;
                }
                ArgumentType::Numeric => {
                    if !arg.ty.as_ref().is_some_and(numeric) {
                        valid = false;
                    }
                    score += 2;
                }
                ArgumentType::Variable(id) => {
                    if let Some(ty) = &arg.ty {
                        if variables.get(id).is_some_and(|v| v != ty) {
                            valid = false;
                        } else {
                            variables.insert(*id, ty.clone());
                        }
                    }
                    score += 3;
                }
                ArgumentType::Any => {}
            }
        }
        if !valid {
            continue;
        }
        let result = match &f.signature.result {
            ReturnType::Exact(ty) => Some(ty.clone()),
            ReturnType::Argument(i) => args.get(*i).and_then(|a| a.ty.clone()),
            ReturnType::ListArgument(i) => args
                .get(*i)
                .and_then(|a| a.ty.clone())
                .map(|ty| LogicalType::List(Box::new(ty))),
            ReturnType::Variable(id) => variables.get(id).cloned(),
        };
        if let Some(ty) = result {
            let nullable = match f.nulls {
                NullSemantics::NonNull => false,
                NullSemantics::Strict => args.iter().any(|a| a.nullable),
                NullSemantics::ProviderDefined => true,
            };
            candidates.push((score, f.clone(), ty, nullable));
        }
    }
    candidates.sort_by_key(|c| std::cmp::Reverse(c.0));
    match candidates.as_slice() {
        [] => Err(ResolveError::NoOverload(name.clone())),
        [first, second, ..] if first.0 == second.0 => {
            Err(ResolveError::AmbiguousOverload(name.clone()))
        }
        [first, ..] => Ok((first.1.clone(), first.2.clone(), first.3)),
    }
}
