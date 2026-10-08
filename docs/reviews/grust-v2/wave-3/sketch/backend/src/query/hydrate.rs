//! The list ordinal, never graph identity, determines the returned path order.
use super::*;
impl Emitter<'_, '_> {
    #[allow(clippy::too_many_arguments)]
    pub(super) fn hydrate(
        &mut self,
        input: &Node,
        entities: &Node,
        identities: &Expr,
        identity: &Expr,
        group: &Expr,
        value: &Expr,
        row: Slot,
        output: Slot,
    ) -> Result<String, EmitError> {
        let child = self.node(input)?;
        let source = self.node(entities)?;
        let input_env = environment(&input.fields, "i.");
        let entity_env = environment(&entities.fields, "e.");
        let ids = self.expression(identities, &input_env)?;
        let identity = self.expression(identity, &entity_env)?;
        let group = self.expression(group, &entity_env)?;
        let value_sql = self.expression(value, &entity_env)?;
        let ty = LogicalType::List(Box::new(
            value
                .ty
                .clone()
                .ok_or_else(|| refusal("untyped hydrated entity"))?,
        ));
        let empty = format!("CAST(array() AS {})", data_type(&ty)?);
        let columns = input
            .fields
            .iter()
            .map(|f| format!("i.{}", slot(f.slot)))
            .collect::<Vec<_>>()
            .join(", ");
        Ok(format!("SELECT {columns}, CASE WHEN {ids} IS NULL THEN CAST(NULL AS {list_type}) ELSE coalesce(h.`@items`,{empty}) END AS {output} FROM {child} i LEFT JOIN (SELECT p.`@row`, transform(array_sort(collect_list(named_struct('pos',p.`@pos`,'value',{value_sql}))),x -> x.value) AS `@items` FROM (SELECT i.{row} AS `@row`, q.`@pos`, q.`@id` FROM {child} i LATERAL VIEW posexplode({ids}) q AS `@pos`,`@id`) p JOIN {source} e ON p.`@id`.identity={identity} AND p.`@id`.group={group} GROUP BY p.`@row`) h ON i.{row}=h.`@row`",list_type=data_type(&ty)?,output=slot(output),row=slot(row)))
    }
}
