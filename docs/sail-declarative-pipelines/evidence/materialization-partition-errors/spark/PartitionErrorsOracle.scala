package org.apache.spark.sql.pipelines.graph

import org.apache.spark.sql.classic.SparkSession
import org.apache.spark.sql.connector.catalog.{CatalogV2Util, Identifier, TableCatalog}
import org.apache.spark.sql.connector.expressions.Expressions
import org.apache.spark.sql.pipelines.logging.{FlowProgressEventLogger, PipelineEvent}
import org.apache.spark.sql.pipelines.utils.TestGraphRegistrationContext
import org.apache.spark.sql.types._
import org.apache.spark.SparkThrowable
import scala.jdk.CollectionConverters._
import org.apache.spark.sql.pipelines.graph.DatasetManager.TableMaterializationException

object PartitionErrorsOracle {
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
          override val spark: SparkSession = PartitionErrorsOracle.thisSpark
        }
        DatasetManager.materializeDatasets(graph, context)
      }
      thisSpark = spark
      val catalog = spark.sessionState.catalogManager.currentCatalog.asInstanceOf[TableCatalog]
      def partition(name: String) = catalog.loadTable(Identifier.of(Array("test_db"), name)).partitioning().toSeq
      def failure(name: String, graph: DataflowGraph, condition: String, state: String, parameters: Map[String, String]): Unit = {
        val error = try { materialize(graph); throw new AssertionError("unexpected success") }
          catch { case error: TableMaterializationException => error }
        assert(error.tableName.endsWith(name))
        val cause = error.cause.asInstanceOf[SparkThrowable]
        assert(cause.getCondition == condition)
        assert(cause.getSqlState == state)
        assert(cause.getMessageParameters.asScala.toMap == parameters)
        println("SDP_ORACLE_ERROR " + name + " " + error.getClass.getName + " " + error.cause.getClass.getName + " " + cause.getCondition + " " + cause.getSqlState + " " + cause.getMessageParameters)
      }
      spark.sql("CREATE TABLE test_db.t8(x BOOLEAN, y INT) USING parquet PARTITIONED BY (x)")
      val changed = new TestGraphRegistrationContext(spark) {
        registerFlow("t8", "t8", query = dfFlowFunc(Seq((true, 1), (false, 3)).toDF("x", "y")))
        registerTable("t8", partitionCols = Some(Seq("y")))
      }.resolveToDataflowGraph()
      failure("t8", changed, "CANNOT_UPDATE_PARTITION_COLUMNS", "42000", Map("existingPartitionColumns" -> "identity(x)", "requestedPartitionColumns" -> "identity(y)"))
      assert(partition("t8") == Seq(Expressions.identity("x")))
      val omitted = new TestGraphRegistrationContext(spark) {
        registerFlow("t8", "t8", query = dfFlowFunc(Seq((true, 1), (false, 3)).toDF("x", "y")))
        registerTable("t8")
      }.resolveToDataflowGraph()
      failure("t8", omitted, "CANNOT_UPDATE_PARTITION_COLUMNS", "42000", Map("existingPartitionColumns" -> "identity(x)", "requestedPartitionColumns" -> ""))
      assert(partition("t8") == Seq(Expressions.identity("x")))
      val conflicting = new TestGraphRegistrationContext(spark) {
        registerTable("invalid_table", query = Some(dfFlowFunc(Seq((1, 1, "x"), (2, 3, "y")).toDF("x1", "x2", "x3"))), partitionCols = Some(Seq("x2")), clusterCols = Some(Seq("x1", "x3")))
      }.resolveToDataflowGraph()
      failure("invalid_table", conflicting, "SPECIFY_CLUSTER_BY_WITH_PARTITIONED_BY_IS_NOT_ALLOWED", "42908", Map.empty)
      assert(!spark.catalog.tableExists("test_db.invalid_table"))
      println("SDP_ORACLE_PASS partition diagnostics: changed, omitted, partition+cluster; unchanged existing transform; absent conflicting target")
    } finally { spark.stop() }
  }
  private var thisSpark: SparkSession = _
}
