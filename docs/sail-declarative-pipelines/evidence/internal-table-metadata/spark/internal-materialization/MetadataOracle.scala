package org.apache.spark.sql.pipelines.graph

import org.apache.spark.sql.classic.SparkSession
import org.apache.spark.sql.connector.catalog.{CatalogV2Util, Identifier, TableCatalog}
import org.apache.spark.sql.connector.expressions.Expressions
import org.apache.spark.sql.pipelines.logging.{FlowProgressEventLogger, PipelineEvent}
import org.apache.spark.sql.pipelines.utils.TestGraphRegistrationContext
import org.apache.spark.sql.types._

object MetadataOracle {
  def main(args: Array[String]): Unit = {
    val spark = org.apache.spark.sql.SparkSession.builder().master("local[2]")
      .appName("SDP internal metadata oracle").config("spark.ui.enabled", "false")
      .config("spark.sql.warehouse.dir", args(0) + "/warehouse").getOrCreate()
      .asInstanceOf[SparkSession]
    import spark.implicits._
    try {
      assert(spark.version == "4.2.1")
      spark.sql("CREATE DATABASE IF NOT EXISTS test_db")
      def materialize(graph: DataflowGraph): Unit = {
        val context = new PipelineUpdateContext {
          override val unresolvedGraph = graph
          override val storageRoot = args(0) + "/state"
          override val refreshTables: TableFilter = AllTables
          override val fullRefreshTables: TableFilter = NoTables
          override val resetCheckpointFlows: FlowFilter = AllFlows
          override val eventCallback: PipelineEvent => Unit = _ => ()
          override def flowProgressEventLogger = new FlowProgressEventLogger(eventCallback)
          override val spark: SparkSession = MetadataOracle.thisSpark
        }
        DatasetManager.materializeDatasets(graph, context)
      }
      thisSpark = spark
      val multiple = new TestGraphRegistrationContext(spark) {
        registerFlow("t1", "t1", query = dfFlowFunc(Seq(1, 2, 3).toDF("x")))
        registerFlow("t2", "t2", query = dfFlowFunc(Seq("a", "b").toDF("y")))
        registerTable("t1")
        registerTable("t2")
      }.resolveToDataflowGraph()
      assert(multiple.tables.forall(_.isStreamingTable))
      materialize(multiple)
      val catalog = spark.sessionState.catalogManager.currentCatalog.asInstanceOf[TableCatalog]
      def table(name: String) = catalog.loadTable(Identifier.of(Array("test_db"), name))
      assert(table("t1").columns() sameElements CatalogV2Util.structTypeToV2Columns(new StructType().add("x", IntegerType)))
      assert(table("t2").columns() sameElements CatalogV2Util.structTypeToV2Columns(new StructType().add("y", StringType)))
      assert(spark.table("test_db.t1").count() == 0)
      assert(spark.table("test_db.t2").count() == 0)
      println("SDP_ORACLE_PASS multiple: streaming table kinds; exact nullable INT/STRING columns; zero rows")
      val partitioned = new TestGraphRegistrationContext(spark) {
        registerTable("a", query = Some(dfFlowFunc(Seq((1, 1), (2, 3)).toDF("x1", "x2"))),
          specifiedSchema = Some(new StructType().add("x1", IntegerType).add("x2", IntegerType)),
          partitionCols = Some(Seq("x2")))
      }.resolveToDataflowGraph()
      assert(partitioned.tables.forall(_.isStreamingTable))
      materialize(partitioned)
      assert(table("a").columns() sameElements CatalogV2Util.structTypeToV2Columns(new StructType().add("x1", IntegerType).add("x2", IntegerType)))
      assert(table("a").partitioning().toSeq == Seq(Expressions.identity("x2")))
      assert(spark.table("test_db.a").count() == 0)
      println("SDP_ORACLE_PASS partition columns with user schema: exact columns; identity x2; zero rows")
    } finally { spark.stop() }
  }
  private var thisSpark: SparkSession = _
}
