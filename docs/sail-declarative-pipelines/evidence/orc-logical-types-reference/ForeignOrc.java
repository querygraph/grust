import java.nio.charset.StandardCharsets;
import java.sql.Timestamp;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.hadoop.hive.ql.exec.vector.BytesColumnVector;
import org.apache.hadoop.hive.ql.exec.vector.LongColumnVector;
import org.apache.hadoop.hive.ql.exec.vector.TimestampColumnVector;
import org.apache.hadoop.hive.ql.exec.vector.VectorizedRowBatch;
import org.apache.orc.OrcFile;
import org.apache.orc.TypeDescription;
import org.apache.orc.Writer;

/** Writes foreign ORC types with no Spark catalyst metadata attributes. */
public class ForeignOrc {
  public static void main(String[] args) throws Exception {
    java.util.TimeZone.setDefault(java.util.TimeZone.getTimeZone("UTC"));
    TypeDescription schema = TypeDescription.fromString(
        "struct<id:int,c:char(5),v:varchar(5),ts:timestamp>");
    try (Writer writer = OrcFile.createWriter(new Path(args[0]),
        OrcFile.writerOptions(new Configuration()).setSchema(schema).overwrite(true))) {
      VectorizedRowBatch batch = schema.createRowBatch();
      String[] chars = {"a", "é猫", "abcde"};
      String[] varchars = {"a", "é猫", "abcde"};
      for (int i = 0; i < chars.length; i++) {
        ((LongColumnVector)batch.cols[0]).vector[i] = i;
        ((BytesColumnVector)batch.cols[1]).setVal(i, chars[i].getBytes(StandardCharsets.UTF_8));
        ((BytesColumnVector)batch.cols[2]).setVal(i, varchars[i].getBytes(StandardCharsets.UTF_8));
        ((TimestampColumnVector)batch.cols[3]).set(i, Timestamp.valueOf("2020-01-02 03:04:05.123456"));
      }
      ((LongColumnVector)batch.cols[0]).vector[3] = 3;
      for (int c = 1; c <= 3; c++) {
        batch.cols[c].noNulls = false;
        batch.cols[c].isNull[3] = true;
      }
      batch.size = 4;
      writer.addRowBatch(batch);
    }
    System.out.println(schema.toJson());
  }
}
