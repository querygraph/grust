import java.nio.file.Files;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.hadoop.conf.Configuration;
import org.apache.hadoop.fs.Path;
import org.apache.orc.OrcFile;
import org.apache.orc.Reader;
import org.apache.orc.TypeDescription;

public class InspectOrc {
  static Map<String,Object> type(TypeDescription t) {
    Map<String,Object> result = new LinkedHashMap<>();
    result.put("id", t.getId());
    result.put("category", t.getCategory().toString());
    Map<String,String> attributes = new LinkedHashMap<>();
    for (String key : t.getAttributeNames()) attributes.put(key, t.getAttributeValue(key));
    result.put("attributes", attributes);
    if (t.getCategory() == TypeDescription.Category.STRUCT) result.put("field_names", t.getFieldNames());
    if (t.getCategory() == TypeDescription.Category.CHAR || t.getCategory() == TypeDescription.Category.VARCHAR) result.put("maximum_length", t.getMaxLength());
    if (t.getChildren() != null) {
      List<Object> children = new ArrayList<>();
      for (TypeDescription child : t.getChildren()) children.add(type(child));
      result.put("children", children);
    }
    return result;
  }
  public static void main(String[] args) throws Exception {
    List<Object> results = new ArrayList<>();
    try (var paths = Files.walk(java.nio.file.Path.of(args[0]))) {
      for (var path : paths.filter(p -> p.toString().endsWith(".orc")).sorted().toList()) {
        try (Reader reader = OrcFile.createReader(new Path(path.toString()), OrcFile.readerOptions(new Configuration()))) {
          Map<String,Object> result = new LinkedHashMap<>();
          result.put("path", path.toString());
          result.put("schema", type(reader.getSchema()));
          result.put("writer_version", reader.getWriterVersion().toString());
          result.put("compression", reader.getCompressionKind().toString());
          List<Object> stripeZones = new ArrayList<>();
          try (var rows = (org.apache.orc.impl.RecordReaderImpl)reader.rows()) {
            for (var stripe : reader.getStripes()) {
              var footer = rows.readStripeFooter(stripe);
              stripeZones.add(footer.hasWriterTimezone() ? footer.getWriterTimezone() : null);
            }
          }
          result.put("stripe_writer_timezones", stripeZones);
          results.add(result);
        }
      }
    }
    System.out.println(new ObjectMapper().writerWithDefaultPrettyPrinter().writeValueAsString(results));
  }
}
