import java.time.Instant;
import java.time.ZoneId;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.TimeZone;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.orc.impl.SerializationUtils;

public class HistoricalTimezone {
  public static void main(String[] args) throws Exception {
    var results = new ArrayList<Object>();
    for (String text : new String[] {"0001-01-01T00:00:00Z", "1800-01-01T00:00:00Z", "1899-12-31T23:59:59Z", "1900-01-01T00:00:00Z", "2020-03-08T02:30:00Z", "2020-11-01T01:30:00Z", "2020-11-01T08:30:00Z", "2020-11-01T09:30:00Z", "2100-07-01T00:00:00Z", "9999-07-01T00:00:00Z", "9999-12-31T23:59:59Z"}) {
      var instant = Instant.parse(text);
      long millis = instant.toEpochMilli();
      for (String[] pair : new String[][] {{"UTC", "America/Los_Angeles"}, {"America/Los_Angeles", "UTC"}, {"America/Los_Angeles", "America/Los_Angeles"}}) {
        var writer = TimeZone.getTimeZone(pair[0]);
        var reader = TimeZone.getTimeZone(pair[1]);
        long adjustment = SerializationUtils.convertBetweenTimezones(writer, reader, millis);
        var row = new LinkedHashMap<String, Object>();
        row.put("input", text); row.put("input_millis", millis);
        row.put("writer", pair[0]); row.put("reader", pair[1]);
        row.put("writer_offset_millis", writer.getOffset(millis));
        row.put("reader_offset_millis", reader.getOffset(millis));
        row.put("reader_raw_offset_millis", reader.getRawOffset());
        row.put("reader_java_time_offset_seconds", ZoneId.of(pair[1]).getRules().getOffset(instant).getTotalSeconds());
        row.put("adjustment_millis", adjustment);
        row.put("result_millis", millis + adjustment);
        row.put("result_utc", Instant.ofEpochMilli(millis + adjustment).toString());
        results.add(row);
      }
    }
    var report = new LinkedHashMap<String,Object>();
    report.put("java_version", System.getProperty("java.version"));
    report.put("java_tzdb_versions", java.time.zone.ZoneRulesProvider.getVersions("America/Los_Angeles").keySet());
    report.put("orc_version", "2.3.0");
    report.put("rows", results);
    System.out.println(new ObjectMapper().writerWithDefaultPrettyPrinter().writeValueAsString(report));
  }
}
