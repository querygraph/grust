
    sql(s"CREATE TABLE ${TestGraphRegistrationContext.DEFAULT_DATABASE}.t2(x INT)")
    val catalog = spark.sessionState.catalogManager.currentCatalog.asInstanceOf[TableCatalog]
    val identifier = Identifier.of(Array(TestGraphRegistrationContext.DEFAULT_DATABASE), "t2")
    val table = catalog.loadTable(identifier)
    assert(
      table.columns() sameElements CatalogV2Util.structTypeToV2Columns(
        new StructType().add("x", IntegerType)
      )
    )

    materializeGraph(
      new TestGraphRegistrationContext(spark) {
        registerFlow("t2", "t2", query = dfFlowFunc(Seq(1, 2, 3).toDF("x")))
        registerTable("t2")
      }.resolveToDataflowGraph(),
      storageRoot = storageRoot
    )

    val table2 = catalog.loadTable(identifier)
    assert(
      table2.columns() sameElements CatalogV2Util
        .structTypeToV2Columns(new StructType().add("x", IntegerType))
    )
