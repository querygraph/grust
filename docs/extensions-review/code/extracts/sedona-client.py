from pyspark.sql.connect.session import SparkSession
from pyspark.sql import functions as F
spark = SparkSession.builder.remote("sc://127.0.0.1:50051").create()
try:
    row = spark.sql("""SELECT
        ST_AsText(ST_Point(1.0, 2.0)) AS wkt,
        ST_Distance(ST_Point(0.0, 0.0), ST_Point(3.0, 4.0)) AS distance
    """).first()
    print(row)
    assert row.distance == 5.0
    points = spark.range(0, 17, numPartitions=4).selectExpr(
        "id", "ST_Point(CAST(id AS DOUBLE), 2.0) AS geom")
    rows = points.repartition(4, "id").selectExpr(
        "id", "ST_AsText(geom) AS wkt",
        "ST_Distance(geom, ST_Point(0.0, 2.0)) AS distance"
    ).orderBy("id").collect()
    assert [r.distance for r in rows] == [float(i) for i in range(17)]
    print("Sedona: 17 geometry rows survived the shuffle")
finally:
    spark.stop()
