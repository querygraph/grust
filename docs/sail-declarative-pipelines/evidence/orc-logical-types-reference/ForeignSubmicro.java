import java.sql.Timestamp;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.hive.ql.exec.vector.LongColumnVector;
import org.apache.hadoop.hive.ql.exec.vector.TimestampColumnVector;
import org.apache.orc.OrcFile;
import org.apache.orc.TypeDescription;

public class ForeignSubmicro {
  public static void main(String[] args) throws Exception {
    java.util.TimeZone.setDefault(java.util.TimeZone.getTimeZone("UTC"));
    var schema = TypeDescription.fromString("struct<id:int,ts:timestamp>");
    try (var writer = OrcFile.createWriter(new Path(args[0]), OrcFile.writerOptions(new Configuration()).setSchema(schema).overwrite(true))) {
      var batch = schema.createRowBatch();
      String[] values = {"2020-01-02 03:04:05.123456789", "1969-12-31 23:59:58.123456789", "1970-01-01 00:00:00.000000001"};
      for (int i = 0; i < values.length; i++) {
        ((LongColumnVector)batch.cols[0]).vector[i] = i;
        ((TimestampColumnVector)batch.cols[1]).set(i, Timestamp.valueOf(values[i]));
      }
      ((LongColumnVector)batch.cols[0]).vector[3] = 3;
      batch.cols[1].noNulls = false;
      batch.cols[1].isNull[3] = true;
      batch.size = 4;
      writer.addRowBatch(batch);
    }
  }
}
