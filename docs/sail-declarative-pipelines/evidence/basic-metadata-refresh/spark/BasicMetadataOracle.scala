package org.apache.spark.sql.pipelines.graph

import org.apache.spark.sql.classic.SparkSession
import org.apache.spark.sql.connector.catalog.{CatalogV2Util, Identifier, TableCatalog}
import org.apache.spark.sql.connector.expressions.Expressions
import org.apache.spark.sql.pipelines.logging.{FlowProgressEventLogger, PipelineEvent}
import org.apache.spark.sql.pipelines.utils.TestGraphRegistrationContext
import org.apache.spark.sql.types._

object BasicMetadataOracle {
  def main(args: Array[String]): Unit = {
    val spark = org.apache.spark.sql.SparkSession.builder().master("local[2]")
      .appName("SDP internal metadata oracle").config("spark.ui.enabled", "false")
      .config("spark.sql.warehouse.dir", args(0) + "/warehouse").getOrCreate()
      .asInstanceOf[SparkSession]
    import spark.implicits._
    try {
      assert(spark.version == "4.2.1")
      spark.sql("CREATE DATABASE IF NOT EXISTS test_db")
      def materializeGraph(graph: DataflowGraph, storageRoot: String): Unit = {
        val context = new PipelineUpdateContext {
          override val unresolvedGraph = graph
          override val storageRoot = args(0) + "/state"
          override val refreshTables: TableFilter = AllTables
          override val fullRefreshTables: TableFilter = NoTables
          override val resetCheckpointFlows: FlowFilter = AllFlows
          override val eventCallback: PipelineEvent => Unit = _ => ()
          override def flowProgressEventLogger = new FlowProgressEventLogger(eventCallback)
          override val spark: SparkSession = BasicMetadataOracle.thisSpark
        }
        DatasetManager.materializeDatasets(graph, context)
      }
      thisSpark = spark
      def sql(text: String): org.apache.spark.sql.classic.DataFrame = spark.sql(text)
      val storageRoot = args(0) + "/state"

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

      assert(spark.table("test_db.a").count() == 0)
      println("SDP_ORACLE_PASS original basic body: three exact schema/comment states; stable table comment; zero rows")
      locally {

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

      assert(spark.table("test_db.t2").count() == 0)
      println("SDP_ORACLE_PASS original existing schema body: SQL-created INT schema unchanged; zero rows")
      }
    } finally { spark.stop() }
  }
  private var thisSpark: SparkSession = _
}
