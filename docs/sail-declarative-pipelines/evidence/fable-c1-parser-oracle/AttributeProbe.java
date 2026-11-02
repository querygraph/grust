import java.io.*; import java.nio.charset.StandardCharsets; import java.util.*;
public class AttributeProbe { public static void main(String[] args) throws Exception {
var reader=new BufferedReader(new InputStreamReader(System.in, StandardCharsets.UTF_8));
for(String line;(line=reader.readLine())!=null;) { String name=new String(HexFormat.of().parseHex(line),StandardCharsets.UTF_8);
try { var parts=org.apache.spark.sql.catalyst.util.AttributeNameParser$.MODULE$.parseAttributeName(name).iterator(); var result=new ArrayList<String>(); while(parts.hasNext()) result.add(HexFormat.of().formatHex(parts.next().getBytes(StandardCharsets.UTF_8))); System.out.println("OK:"+String.join(",",result)); } catch(Exception e) {System.out.println("ERR");} }
} }
