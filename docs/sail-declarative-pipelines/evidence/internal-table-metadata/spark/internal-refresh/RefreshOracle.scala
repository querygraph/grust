package org.apache.spark.sql.pipelines.graph

import org.apache.spark.sql.classic.SparkSession
import org.apache.spark.sql.connector.catalog.{CatalogV2Util, Identifier, TableCatalog}
import org.apache.spark.sql.connector.expressions.Expressions
import org.apache.spark.sql.pipelines.logging.{FlowProgressEventLogger, PipelineEvent}
import org.apache.spark.sql.pipelines.utils.TestGraphRegistrationContext
import org.apache.spark.sql.types._

object RefreshOracle {
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
          override val spark: SparkSession = RefreshOracle.thisSpark
        }
        DatasetManager.materializeDatasets(graph, context)
      }
      thisSpark = spark
      def definition(initial: Boolean): DataflowGraph = new TestGraphRegistrationContext(spark) {
        if (initial) {
          registerTable("target", query = Some(dfFlowFunc(Seq((7, 8)).toDF("id", "retained"))),
            specifiedSchema = Some(new StructType().add("id", IntegerType, true, "old").add("retained", IntegerType)))
        } else {
          registerTable("target", query = Some(dfFlowFunc(Seq((9, "x")).toDF("id", "added"))),
            specifiedSchema = Some(new StructType().add("id", IntegerType, true, "new").add("added", StringType)),
            properties = Map("user.key" -> "value"))
        }
      }.resolveToDataflowGraph()
      materialize(definition(true))
      spark.sql("INSERT INTO test_db.target VALUES (7, 8)")
      materialize(definition(false))
      val catalog = spark.sessionState.catalogManager.currentCatalog.asInstanceOf[TableCatalog]
      val table = catalog.loadTable(Identifier.of(Array("test_db"), "target"))
      val schema = CatalogV2Util.v2ColumnsToStructType(table.columns())
      assert(schema.fieldNames.toSeq == Seq("id", "retained", "added"))
      assert(schema("id").getComment() == Some("old"))
      assert(table.properties().get("user.key") == "value")
      assert(spark.table("test_db.target").count() == 1)
      println("SDP_ORACLE_PASS ordinary refresh: rows retained; fields appended; left comments retained; properties updated")
    } finally { spark.stop() }
  }
  private var thisSpark: SparkSession = _
}
