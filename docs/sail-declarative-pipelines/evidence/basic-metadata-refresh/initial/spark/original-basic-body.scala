
    materializeGraph(
      new TestGraphRegistrationContext(spark) {
        registerMaterializedView(
          "a",
          specifiedSchema = Option(
            new StructType()
              .add("x", IntegerType, nullable = false, "comment1")
              .add("x2", IntegerType, nullable = true, "comment2")
          ),
          comment = Option("p-comment"),
          query = dfFlowFunc(Seq((1, 1), (2, 3)).toDF("x", "x2"))
        )
      }.resolveToDataflowGraph(),
      storageRoot = storageRoot
    )

    val identifier = Identifier.of(Array(TestGraphRegistrationContext.DEFAULT_DATABASE), "a")
    val catalog = spark.sessionState.catalogManager.currentCatalog.asInstanceOf[TableCatalog]
    val catalogTable = catalog.loadTable(identifier)

    assert(
      catalogTable.columns() sameElements CatalogV2Util.structTypeToV2Columns(
        new StructType()
          .add("x", IntegerType, nullable = false, "comment1")
          .add("x2", IntegerType, nullable = true, "comment2")
      )
    )
    assert(catalogTable.properties().get(TableCatalog.PROP_COMMENT) == "p-comment")

    materializeGraph(
      new TestGraphRegistrationContext(spark) {
        registerMaterializedView(
          "a",
          specifiedSchema = Option(
            new StructType()
              .add("x", IntegerType, nullable = false, "comment3")
              .add("x2", IntegerType, nullable = true, "comment4")
          ),
          comment = Option("p-comment"),
          query = dfFlowFunc(Seq((1, 1), (2, 3)).toDF("x", "x2"))
        )
      }.resolveToDataflowGraph(),
      storageRoot = storageRoot
    )
    val catalogTable2 = catalog.loadTable(identifier)
    assert(
      catalogTable2.columns() sameElements CatalogV2Util.structTypeToV2Columns(
        new StructType()
          .add("x", IntegerType, nullable = false, "comment3")
          .add("x2", IntegerType, nullable = true, "comment4")
      )
    )
    assert(catalogTable2.properties().get(TableCatalog.PROP_COMMENT) == "p-comment")

    materializeGraph(
      new TestGraphRegistrationContext(spark) {
        registerMaterializedView(
          "a",
          specifiedSchema = Option(
            new StructType()
              .add("x", IntegerType, nullable = false)
              .add("x2", IntegerType, nullable = true)
          ),
          comment = Option("p-comment"),
          query = dfFlowFunc(Seq((1, 1), (2, 3)).toDF("x", "x2"))
        )
      }.resolveToDataflowGraph(),
      storageRoot = storageRoot
    )

    val catalogTable3 = catalog.loadTable(identifier)
    assert(
      catalogTable3.columns() sameElements CatalogV2Util.structTypeToV2Columns(
        new StructType()
          .add("x", IntegerType, nullable = false, comment = null)
          .add("x2", IntegerType, nullable = true, comment = null)
      )
    )
    assert(catalogTable3.properties().get(TableCatalog.PROP_COMMENT) == "p-comment")
