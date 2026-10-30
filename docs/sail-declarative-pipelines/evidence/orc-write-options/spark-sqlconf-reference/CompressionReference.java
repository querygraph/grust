import java.util.Base64;
import java.nio.charset.StandardCharsets;
import org.apache.spark.sql.internal.SQLConf;
public class CompressionReference {
 public static void main(String[] args) {
  String key="spark.sql.orc.compression.codec";
  for(String arg:args) {
   SQLConf conf=new SQLConf(); conf.setConfString(key,"snappy");
   String value=new String(Base64.getDecoder().decode(arg),StandardCharsets.UTF_8);
   String outcome="accepted";
   try {conf.setConfString(key,value);} catch(Exception e) {outcome=e.getClass().getName();}
   String raw=Base64.getEncoder().encodeToString(conf.getConfString(key).getBytes(StandardCharsets.UTF_8));
   System.out.println("CASE\t"+arg+"\t"+outcome+"\t"+conf.orcCompressionCodec()+"\t"+raw);
  }
 }
}