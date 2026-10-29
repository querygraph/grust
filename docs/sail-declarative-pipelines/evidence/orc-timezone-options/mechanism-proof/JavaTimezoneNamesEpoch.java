import java.nio.file.Files;
import java.nio.file.Path;
import java.text.SimpleDateFormat;
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Set;
import java.util.TimeZone;
import com.fasterxml.jackson.databind.ObjectMapper;

public class JavaTimezoneNamesEpoch {
  public static void main(String[] args) throws Exception {
    var names=Set.of(TimeZone.getAvailableIDs());
    var rows=new ArrayList<Object>();
    for (String name:new String[]{"UTC","GMT","UT","Z","GMT+05:45","GMT+5","GMT+530","GMT+05:30","GMT-00:00","+05:30","-05:00","UTC+05:30","Etc/GMT+5","America/Los_Angeles","america/los_angeles","PST","EST","IST","Asia/Katmandu","Not/AZone",""," GMT","GMT+24:00","GMT+23:59","GMT+05:60","GMT+00530","GMT+0","GMT-0","GMT+00:00","Australia/Lord_Howe","Pacific/Chatham","Europe/Dublin","Africa/Windhoek","Africa/Casablanca"}) {
      var zone=TimeZone.getTimeZone(name);
      var formatter=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.US);
      formatter.setTimeZone(zone);
      var row=new LinkedHashMap<String,Object>();
      row.put("requested",name);row.put("available_id",names.contains(name));row.put("resolved_id",zone.getID());
      row.put("raw_offset_millis",zone.getRawOffset());
      row.put("orc_2015_epoch_seconds",formatter.parse("2015-01-01 00:00:00").getTime()/1000);
      row.put("timezone_class",zone.getClass().getName());rows.add(row);
    }
    var report=new LinkedHashMap<String,Object>();report.put("java_version",System.getProperty("java.version"));
    report.put("tzdb_versions",java.time.zone.ZoneRulesProvider.getVersions("America/Los_Angeles").keySet());
    report.put("note","Empty input here tests TimeZone.getTimeZone itself; ORC intercepts absent/empty writer metadata and retains its current writer zone.");report.put("rows",rows);
    Files.writeString(Path.of(args[0]),new ObjectMapper().writerWithDefaultPrettyPrinter().writeValueAsString(report)+"\n");
  }
}
