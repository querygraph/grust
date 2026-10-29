import java.lang.reflect.Field;
import java.math.BigInteger;
import java.nio.file.Files;
import java.nio.file.Path;
import java.text.SimpleDateFormat;
import java.time.Instant;
import java.time.LocalDate;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.TimeZone;
import java.util.TreeMap;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.apache.orc.impl.SerializationUtils;

// One-profile mechanism proof. Private fields are used only to export Java's
// normalized historical table. Every offset assertion uses public TimeZone.
public class JavaPortableCycleProof {
  static final long DAY = 86_400_000L;
  static final long PERIOD = 146_097L * DAY;
  static final long ANCHOR = Instant.parse("2400-01-01T00:00:00Z").toEpochMilli();
  static final TimeZone ZONE = TimeZone.getTimeZone("America/Los_Angeles");
  static final TimeZone UTC = TimeZone.getTimeZone("UTC");
  static final List<long[]> HISTORICAL = new ArrayList<>();
  static final List<long[]> CYCLE = new ArrayList<>();
  static int raw;
  static long comparisons;

  static Object field(String name) throws Exception {
    Field f = Class.forName("sun.util.calendar.ZoneInfo").getDeclaredField(name);
    f.setAccessible(true);
    return f.get(ZONE);
  }

  static long floorOffset(List<long[]> rows, long key) {
    int low=0, high=rows.size();
    while (low<high) {
      int mid=low+(high-low)/2;
      if (rows.get(mid)[0]<=key) low=mid+1; else high=mid;
    }
    if (low==0) throw new IllegalArgumentException("before first profile row");
    return rows.get(low-1)[1];
  }

  static long portable(long millis) {
    if (HISTORICAL.isEmpty() || millis<HISTORICAL.get(0)[0]) return raw;
    if (millis<=HISTORICAL.get(HISTORICAL.size()-1)[0]) return floorOffset(HISTORICAL,millis);
    return floorOffset(CYCLE,Math.floorMod(millis-ANCHOR,PERIOD));
  }

  static void check(long millis) {
    long actual=ZONE.getOffset(millis), got=portable(millis);
    if (actual!=got) throw new AssertionError(Instant.ofEpochMilli(millis)+": "+actual+" != "+got);
    comparisons++;
  }

  static long adjustment(boolean utcWriter, long millis) {
    long writer=utcWriter?0:portable(millis);
    long reader=utcWriter?portable(millis):0;
    long candidate=Math.addExact(millis,writer-reader);
    return writer-(utcWriter?portable(candidate):0);
  }

  static Object boundary(long micros) {
    long millis=Math.floorDiv(micros,1000);
    check(millis);
    long toZone=adjustment(true,millis), toUtc=adjustment(false,millis);
    long javaToZone=SerializationUtils.convertBetweenTimezones(UTC,ZONE,millis);
    long javaToUtc=SerializationUtils.convertBetweenTimezones(ZONE,UTC,millis);
    if (toZone!=javaToZone || toUtc!=javaToUtc) throw new AssertionError("ORC adjustment mismatch");
    BigInteger result=BigInteger.valueOf(micros).add(BigInteger.valueOf(toZone).multiply(BigInteger.valueOf(1000)));
    var row=new LinkedHashMap<String,Object>();
    row.put("input_micros",micros); row.put("instant_at_floor_millis",Instant.ofEpochMilli(millis).toString());
    row.put("offset_millis",portable(millis)); row.put("mapped_future_instant",millis<HISTORICAL.get(0)[0]?null:Instant.ofEpochMilli(ANCHOR+Math.floorMod(millis-ANCHOR,PERIOD)).toString());
    row.put("utc_to_la_adjustment_millis",toZone); row.put("la_to_utc_adjustment_millis",toUtc);
    row.put("utc_to_la_result_micros",result.toString());
    row.put("utc_to_la_result_fits_i64",result.bitLength()<64);
    return row;
  }

  public static void main(String[] args) throws Exception {
    long[] packed=(long[])field("transitions");
    int[] offsets=(int[])field("offsets");
    raw=(Integer)field("rawOffset");
    for (long p:packed) HISTORICAL.add(new long[]{p>>12,offsets[(int)(p&15)]});

    // Scan daily only for this known Los Angeles profile, then independently
    // require equality with every public ZoneRules recurring transition.
    CYCLE.add(new long[]{0,ZONE.getOffset(ANCHOR)});
    long previous=ANCHOR;
    int previousOffset=ZONE.getOffset(previous);
    for (long end=ANCHOR+DAY;end<=ANCHOR+PERIOD;end+=DAY) {
      int next=ZONE.getOffset(end);
      if (next!=previousOffset) {
        long low=previous,high=end;
        while (low+1<high) {
          long mid=low+(high-low)/2;
          if (ZONE.getOffset(mid)==previousOffset) low=mid; else high=mid;
        }
        CYCLE.add(new long[]{high-ANCHOR,next});
      }
      previous=end; previousOffset=next;
    }
    var expected=new TreeMap<Long,Integer>();
    for (int year=2400;year<2800;year++) for (var rule:ZONE.toZoneId().getRules().getTransitionRules()) {
      var transition=rule.createTransition(year);
      expected.put(transition.getInstant().toEpochMilli()-ANCHOR,transition.getOffsetAfter().getTotalSeconds()*1000);
    }
    if (expected.size()!=CYCLE.size()-1) throw new AssertionError("cycle transition count");
    for (int i=1;i<CYCLE.size();i++) {
      long[] row=CYCLE.get(i);
      if (!Long.valueOf(row[1]).equals(expected.get(row[0])==null?null:Long.valueOf(expected.get(row[0])))) throw new AssertionError("cycle transition mismatch");
    }

    for (long[] row:HISTORICAL) for (int delta:new int[]{-1,0,1}) check(row[0]+delta);
    for (long t=ANCHOR;t<ANCHOR+PERIOD;t+=DAY) {check(t);check(t+DAY/2);}
    long maxMillis=Math.floorDiv(Long.MAX_VALUE,1000),minMillis=Math.floorDiv(Long.MIN_VALUE,1000);
    for (int baseYear:new int[]{2000,2400,9600,10000,292000,294000}) {
      long base=LocalDate.of(baseYear,1,1).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli();
      for (long[] row:CYCLE) for (int delta:new int[]{-1,0,1}) {
        long t=base+row[0]+delta;
        if (t>HISTORICAL.get(HISTORICAL.size()-1)[0] && t<=maxMillis && t>=minMillis) check(t);
      }
    }
    var boundaries=new ArrayList<Object>();
    for (String date:new String[]{"0001-07-01T00:00:00Z","1582-10-04T23:59:59Z","1582-10-15T00:00:00Z","1899-12-31T23:59:59Z","1900-01-01T00:00:00Z","2037-11-01T08:59:59Z","2037-11-01T09:00:00Z","2100-03-14T09:59:59Z","2100-03-14T10:00:00Z","2100-07-01T00:00:00Z","9999-07-01T00:00:00Z","9999-12-31T23:59:59Z","+10000-01-01T07:59:59Z","+10000-07-01T00:00:00Z"}) boundaries.add(boundary(Math.multiplyExact(Instant.parse(date).toEpochMilli(),1000)));
    for (long micros:new long[]{Long.MIN_VALUE,Long.MIN_VALUE+1,Long.MIN_VALUE+999,Long.MIN_VALUE+86_400_000_000L,Long.MAX_VALUE-86_400_000_000L,Long.MAX_VALUE-999,Long.MAX_VALUE-1,Long.MAX_VALUE}) boundaries.add(boundary(micros));

    var parser=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",Locale.US);parser.setTimeZone(ZONE);
    long orcEpochSeconds=parser.parse("2015-01-01 00:00:00").getTime()/1000;
    var profile=new LinkedHashMap<String,Object>();
    profile.put("zone",ZONE.getID());profile.put("raw_prefix_offset_millis",raw);
    profile.put("orc_epoch_seconds",orcEpochSeconds);profile.put("explicit_transitions",HISTORICAL);
    profile.put("future_cycle_anchor_millis",ANCHOR);profile.put("future_cycle_period_millis",PERIOD);profile.put("future_cycle",CYCLE);
    var report=new LinkedHashMap<String,Object>();
    report.put("java_version",System.getProperty("java.version"));report.put("tzdb_versions",java.time.zone.ZoneRulesProvider.getVersions(ZONE.getID()).keySet());
    report.put("profile",profile);report.put("public_timezone_offset_comparisons",comparisons);
    report.put("cycle_transition_count",CYCLE.size()-1);report.put("zone_rules_cycle_transitions_verified",expected.size());report.put("boundary_cases",boundaries);
    report.put("scope","One Los Angeles profile mechanism proof; no assertion that daily sampling exports arbitrary zones. No Rust build/runtime measurement.");
    Files.writeString(Path.of(args[0]),new ObjectMapper().writerWithDefaultPrettyPrinter().writeValueAsString(report)+"\n");
    System.out.println("PASS: "+comparisons+" public TimeZone offset comparisons; "+(CYCLE.size()-1)+" cycle transitions; "+boundaries.size()+" ORC boundary comparisons");
  }
}
