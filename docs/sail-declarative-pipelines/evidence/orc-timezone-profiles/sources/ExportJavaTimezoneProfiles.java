import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.text.SimpleDateFormat;
import java.time.*;
import java.util.*;
import java.util.function.Consumer;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.apache.orc.impl.SerializationUtils;

/** Offline pinned-JDK data exporter. No OpenJDK implementation is copied here. */
public class ExportJavaTimezoneProfiles {
  static final ObjectMapper JSON = new ObjectMapper().enable(SerializationFeature.ORDER_MAP_ENTRIES_BY_KEYS);
  static final long ANCHOR = Instant.parse("2400-01-01T00:00:00Z").toEpochMilli();
  static final long PERIOD = 146_097L * 86_400_000L;
  // Covers the i64-microsecond result domain plus two maximal i32 offset differences.
  static final long MIN = Math.floorDiv(Long.MIN_VALUE,1000)-4L*(1L<<31);
  static final long MAX = Math.floorDiv(Long.MAX_VALUE,1000)+4L*(1L<<31);
  static final Class<?> ZI;
  static final Method LAST_RULE, GET_START, GET_END, NEW_DATE;
  static final Object CALENDAR;
  static {
    try {
      ZI=Class.forName("sun.util.calendar.ZoneInfo");
      Class<?> base=Class.forName("sun.util.calendar.BaseCalendar");
      Class<?> date=Class.forName("sun.util.calendar.BaseCalendar$Date");
      CALENDAR=field(SimpleTimeZone.class,"gcal",null);
      NEW_DATE=CALENDAR.getClass().getMethod("newCalendarDate",TimeZone.class);
      GET_START=SimpleTimeZone.class.getDeclaredMethod("getStart",base,date,int.class);
      GET_END=SimpleTimeZone.class.getDeclaredMethod("getEnd",base,date,int.class);
      GET_START.setAccessible(true);GET_END.setAccessible(true);
      LAST_RULE=ZI.getMethod("getLastRuleInstance");
    } catch(Exception e) {throw new ExceptionInInitializerError(e);}
  }
  static Object field(Class<?> cls,String name,Object target) throws Exception {
    Field f=cls.getDeclaredField(name);f.setAccessible(true);return f.get(target);
  }
  static TreeMap<String,Object> object(Object... values) {
    var out=new TreeMap<String,Object>();
    for(int i=0;i<values.length;i+=2)out.put((String)values[i],values[i+1]);
    return out;
  }
  static String sha(byte[] bytes) throws Exception {
    return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));
  }
  static String identity(Object data) throws Exception {return sha(JSON.writeValueAsBytes(data));}
  static void write(Path path,Object data) throws Exception {
    Files.write(path,(JSON.writeValueAsString(data)+"\n").getBytes(StandardCharsets.UTF_8));
  }
  static long floor(List<long[]> rows,long key) {
    int low=0,high=rows.size();
    while(low<high){int mid=low+(high-low)/2;if(rows.get(mid)[0]<=key)low=mid+1;else high=mid;}
    if(low==0)throw new IllegalArgumentException("missing prefix row");
    return rows.get(low-1)[1];
  }
  static final class Cycle {
    final List<long[]> rows;
    final Map<String,Object> data;
    final String id;
    Cycle(List<long[]> rows) throws Exception {
      this.rows=rows;data=object("anchor_millis",ANCHOR,"period_millis",PERIOD,"rows",rows);id=identity(data);
    }
  }
  static final class Profile {
    final int raw;final long epoch;final List<long[]> transitions;final Cycle cycle;final int futureFixed;
    final Map<String,Object> data;final String id;
    Profile(int raw,long epoch,List<long[]> transitions,Cycle cycle) throws Exception {
      this.raw=raw;this.epoch=epoch;this.transitions=transitions;this.cycle=cycle;
      futureFixed=transitions.isEmpty()?raw:(int)transitions.get(transitions.size()-1)[1];
      data=object("raw_prefix_offset_millis",raw,"orc_epoch_seconds",epoch,"transitions",transitions,
        "future",cycle==null?object("kind","fixed","offset_millis",futureFixed):object("kind","cycle","id",cycle.id));
      id=identity(data);
    }
    long last(){return transitions.isEmpty()?Long.MIN_VALUE:transitions.get(transitions.size()-1)[0];}
    int offset(long millis) {
      if(millis<MIN||millis>MAX)throw new IllegalArgumentException("outside qualified offset domain");
      if(transitions.isEmpty()||millis<transitions.get(0)[0])return raw;
      if(millis<=last())return (int)floor(transitions,millis);
      return cycle==null?futureFixed:(int)floor(cycle.rows,Math.floorMod(millis-ANCHOR,PERIOD));
    }
  }
  record Zone(TimeZone oracle,Profile profile) {}
  static long exactBoundary(SimpleTimeZone rule,Method method,int year) throws Exception {
    return (Long)method.invoke(rule,CALENDAR,NEW_DATE.invoke(CALENDAR,(Object)null),year);
  }
  static long exactBoundaryCalls;
  static Cycle cycle(TimeZone zone,SimpleTimeZone rule) throws Exception {
    if((Integer)field(SimpleTimeZone.class,"startYear",rule)!=0||!rule.useDaylightTime())
      throw new AssertionError("unsupported non-recurring or delayed rule: "+zone.getID());
    var events=new TreeSet<Long>();
    // Include adjacent years because timezone offsets and 24:00 rule times can
    // move a local boundary across a UTC year boundary.
    for(int year=2399;year<=2800;year++)for(Method method:new Method[]{GET_START,GET_END}) {
      long t=exactBoundary(rule,method,year);exactBoundaryCalls++;
      long shifted=exactBoundary(rule,method,year+400);exactBoundaryCalls++;
      if(shifted-t!=PERIOD)throw new AssertionError("rule is not Gregorian-periodic");
      int before=zone.getOffset(t-1),after=zone.getOffset(t);
      int expected=method==GET_START?rule.getRawOffset()+rule.getDSTSavings():rule.getRawOffset();
      if(before==after||after!=expected)throw new AssertionError("unexpected recurring transition: "+zone.getID()+" "+t);
      if(t>=ANCHOR&&t<ANCHOR+PERIOD)events.add(t);
    }
    var rows=new ArrayList<long[]>();rows.add(new long[]{0,zone.getOffset(ANCHOR)});
    for(long t:events)if(t!=ANCHOR)rows.add(new long[]{t-ANCHOR,zone.getOffset(t)});
    if(zone.getOffset(ANCHOR)!=zone.getOffset(ANCHOR+PERIOD))throw new AssertionError("cycle wrap");
    return new Cycle(rows);
  }
  static long epoch(SimpleDateFormat formatter,TimeZone zone) throws Exception {
    formatter.setTimeZone(zone);long millis=formatter.parse("2015-01-01 00:00:00").getTime();
    if(millis%1000!=0)throw new AssertionError("fractional ORC epoch");return millis/1000;
  }
  static List<Long> anchors() {
    var out=new ArrayList<Long>();
    for(int year:new int[]{2000,2400,9600,10000,292000,294000})
      out.add(LocalDate.of(year,1,1).atStartOfDay(ZoneOffset.UTC).toInstant().toEpochMilli());
    return out;
  }
  static List<Long> baseline() {
    var points=new TreeSet<Long>();
    for(String date:new String[]{"0001-01-01T00:00:00Z","0001-07-01T00:00:00Z","1582-10-04T23:59:59Z","1582-10-15T00:00:00Z","1800-01-01T00:00:00Z","1899-12-31T23:59:59.999Z","1900-01-01T00:00:00Z","1900-01-01T00:00:00.001Z","1970-01-01T00:00:00Z","2015-01-01T00:00:00Z","2020-03-08T02:30:00Z","2020-11-01T01:30:00Z","2020-11-01T08:30:00Z","2020-11-01T09:30:00Z","2036-12-31T23:00:00Z","2038-09-26T02:00:00Z","2100-01-01T00:00:00Z","2100-07-01T00:00:00Z","9999-07-01T00:00:00Z","9999-12-31T23:59:59.999Z","+10000-01-01T07:59:59Z","+10000-07-01T00:00:00Z"})points.add(Instant.parse(date).toEpochMilli());
    for(long t:new long[]{MIN,MAX,Math.floorDiv(Long.MIN_VALUE,1000),Math.floorDiv(Long.MAX_VALUE,1000)})
      for(long d:new long[]{-1,0,1})if(t+d>=MIN&&t+d<=MAX)points.add(t+d);
    return new ArrayList<>(points);
  }
  static TreeSet<Long> queries(Profile profile,boolean firstCycle,List<Long> baseline,List<Long> anchors) {
    var points=new TreeSet<Long>(baseline);
    for(int i=0;i<profile.transitions.size();i++) {
      long t=profile.transitions.get(i)[0];for(int d:new int[]{-1,0,1})points.add(t+d);
      if(i>0)points.add(profile.transitions.get(i-1)[0]+(t-profile.transitions.get(i-1)[0])/2);
    }
    if(firstCycle)for(long anchor:anchors)for(int i=0;i<profile.cycle.rows.size();i++) {
      long position=profile.cycle.rows.get(i)[0];
      long end=i+1<profile.cycle.rows.size()?profile.cycle.rows.get(i+1)[0]:PERIOD;
      for(long t:new long[]{anchor+position-1,anchor+position,anchor+position+1,anchor+position+(end-position)/2})
        if(t>profile.last()&&t>=MIN&&t<=MAX)points.add(t);
    }
    return points;
  }
  static void digestRow(MessageDigest digest,Object... fields) throws Exception {
    digest.update(JSON.writeValueAsBytes(Arrays.asList(fields)));digest.update((byte)'\n');
  }
  static long conversion(Profile writer,Profile reader,long millis) {
    long w=writer.offset(millis),r=reader.offset(millis);
    return w-reader.offset(Math.addExact(millis,w-r));
  }
  static String pad(int value,int width) {
    String text=Integer.toString(value);return "0".repeat(Math.max(0,width-text.length()))+text;
  }
  static List<String> variants(int value) {
    return value<10?List.of(Integer.toString(value),pad(value,2)):List.of(Integer.toString(value));
  }
  interface CaseConsumer {void accept(String value) throws Exception;}
  static final String[] UNKNOWN={"","Z","UT","utc","gmt"," UTC","UTC ","Not/AZone","America/los_angeles","UTC+05:30","+05:30","-0530","GMT","GMT+","GMT-","GMT+05:30:15","GMT-00:00:01","GMT+23:59:59","GMT+05:30:00","GMT+00530","GMT+24:00","GMT+05:60","GMT+05:30:60","GMT+1:2:03","GMT+01:2:03","GMT+1:2","GMT+1::03","GMT+01:02:03:04","GMT+01:02\n","GMT+\u0000","GMT+１２:00"};
  static void resolverCases(SortedSet<String> names,CaseConsumer consumer) throws Exception {
    for(String sign:new String[]{"+","-"}) {
      for(int width=1,limit=10;width<=4;width++,limit*=10)
        for(int value=0;value<limit;value++)consumer.accept("GMT"+sign+pad(value,width));
      for(int hour=0;hour<24;hour++)for(String h:variants(hour))for(int minute=0;minute<60;minute++) {
        consumer.accept("GMT"+sign+h+":"+pad(minute,2));
        for(String m:variants(minute))for(int second=0;second<60;second++)
          consumer.accept("GMT"+sign+h+":"+m+":"+pad(second,2));
      }
      for(String h:new String[]{"","24","99","000","-1","A","１"})
        for(String m:new String[]{"","0","60","99","000","-1","B","０"})
          for(String s:new String[]{"","0","60","99","000","-1","C","０"})
            consumer.accept("GMT"+sign+h+":"+m+":"+s);
    }
    for(String value:UNKNOWN)consumer.accept(value);
    for(String name:names) {
      consumer.accept(name);consumer.accept(name.toLowerCase(Locale.ROOT));
      consumer.accept(name.toUpperCase(Locale.ROOT));consumer.accept(" "+name);
    }
  }

  @SuppressWarnings("unchecked")
  public static void main(String[] args) throws Exception {
    if(args.length!=3)throw new IllegalArgumentException("output-directory format-locale expected-oldmapping");
    Path out=Path.of(args[0]);Files.createDirectories(out);
    Locale locale=Locale.forLanguageTag(args[1]);Locale.setDefault(Locale.Category.FORMAT,locale);
    boolean old=Boolean.parseBoolean(args[2]);
    Class<?> zif=Class.forName("sun.util.calendar.ZoneInfoFile");
    if((Boolean)zif.getMethod("useOldMapping").invoke(null)!=old)throw new AssertionError("oldmapping JVM setting mismatch");
    TimeZone.setDefault(TimeZone.getTimeZone("UTC"));
    var formatter=new SimpleDateFormat("yyyy-MM-dd HH:mm:ss",locale);
    var available=new TreeSet<String>(Arrays.asList(TimeZone.getAvailableIDs()));
    var aliases=new TreeMap<String,String>((Map<String,String>)zif.getMethod("getAliasMap").invoke(null));
    var names=new TreeSet<>(available);names.addAll(aliases.keySet());
    var cyclesByShape=new TreeMap<String,Cycle>();var cycles=new TreeMap<String,Object>();
    var profiles=new TreeMap<String,Object>();var zones=new TreeMap<String,Object>();
    var objects=new TreeMap<String,Zone>();var sameRules=new HashMap<String,Profile>();
    for(String name:names) {
      TimeZone zone=TimeZone.getTimeZone(name);
      if(!ZI.isInstance(zone)||(Integer)field(ZI,"rawOffsetDiff",zone)!=0)throw new AssertionError("unexpected mutable/custom timezone implementation");
      int raw=(Integer)field(ZI,"rawOffset",zone);
      long[] packed=(long[])field(ZI,"transitions",zone);int[] offsets=(int[])field(ZI,"offsets",zone);
      var history=new ArrayList<long[]>();
      if(packed!=null)for(long p:packed) {
        long t=p>>12;int offset=offsets[(int)(p&15)];
        if(!history.isEmpty()&&t<=history.get(history.size()-1)[0])throw new AssertionError("non-increasing table: "+name);
        history.add(new long[]{t,offset});
      }
      SimpleTimeZone rule=(SimpleTimeZone)LAST_RULE.invoke(zone);Cycle cycle=null;
      if(rule!=null) {
        if(history.isEmpty())throw new AssertionError("recurring rule without explicit table");
        String shape=raw+":"+Arrays.toString((int[])field(ZI,"simpleTimeZoneParams",zone))+":"+rule.getDSTSavings();
        cycle=cyclesByShape.get(shape);
        if(cycle==null){cycle=cycle(zone,rule);cyclesByShape.put(shape,cycle);cycles.put(cycle.id,cycle.data);}
      }
      Profile profile=new Profile(raw,epoch(formatter,zone),history,cycle);
      String sameKey=raw+":"+field(ZI,"checksum",zone);
      Profile prior=sameRules.putIfAbsent(sameKey,profile);
      if(prior!=null&&!prior.id.equals(profile.id))throw new AssertionError("Java hasSameRules group differs in normalized behavior: "+name);
      profiles.put(profile.id,profile.data);
      zones.put(name,object("profile",profile.id,"resolved_id",zone.getID(),"available",available.contains(name)));
      objects.put(name,new Zone(zone,profile));
    }
    Profile utc=objects.get("UTC").profile();TimeZone utcOracle=TimeZone.getTimeZone("UTC");
    var configuration=object("java_runtime_version",System.getProperty("java.runtime.version"),"java_vendor",System.getProperty("java.vendor"),
      "tzdb_versions",new ArrayList<>(java.time.zone.ZoneRulesProvider.getVersions("UTC").keySet()),"legacy_id_mapping",old,
      "format_locale",locale.toLanguageTag(),"epoch_calendar",formatter.getCalendar().getClass().getName(),
      "epoch_text","2015-01-01 00:00:00","utc_epoch_seconds",utc.epoch,"offset_domain_millis",List.of(MIN,MAX));
    var artifact=object("format_version",1,"configuration",configuration,"zones",zones,"profiles",profiles,"cycles",cycles,"java_aliases",aliases);
    System.out.println("Extracted names="+names.size()+" profiles="+profiles.size()+" cycles="+cycles.size()+"; verifying public oracle");

    List<Long> baseline=baseline(),anchors=anchors();var seenCycles=new HashSet<String>();
    MessageDigest oracleDigest=MessageDigest.getInstance("SHA-256");
    MessageDigest conversionDigest=MessageDigest.getInstance("SHA-256");
    long offsetChecks=0,conversionChecks=0;var perZone=new TreeMap<String,Object>();
    for(var entry:objects.entrySet()) {
      String name=entry.getKey();Zone zone=entry.getValue();Profile profile=zone.profile();
      boolean first=profile.cycle!=null&&seenCycles.add(profile.cycle.id);
      var queries=queries(profile,first,baseline,anchors);
      for(long millis:queries) {
        int expected=zone.oracle().getOffset(millis),actual=profile.offset(millis);
        if(actual!=expected)throw new AssertionError(name+" offset "+millis+": "+actual+" != "+expected);
        digestRow(oracleDigest,name,millis,expected);offsetChecks++;
      }
      for(long millis:baseline) {
        // Guard endpoints test offset lookup only; conversion candidates may
        // intentionally extend beyond the qualified query domain.
        if(millis<MIN+(1L<<32)||millis>MAX-(1L<<32))continue;
        long a=SerializationUtils.convertBetweenTimezones(utcOracle,zone.oracle(),millis);
        long b=SerializationUtils.convertBetweenTimezones(zone.oracle(),utcOracle,millis);
        if(a!=conversion(utc,profile,millis)||b!=conversion(profile,utc,millis))throw new AssertionError("ORC conversion: "+name+" "+millis);
        digestRow(conversionDigest,name,millis,a,b);conversionChecks+=2;
      }
      perZone.put(name,object("offset_checks",queries.size(),"full_cycle_checked",first));
    }
    var verification=object("algorithm","history-boundaries-midpoints-and-first-cycle-boundaries-midpoints-v1",
      "baseline_millis",baseline,"cycle_block_starts_millis",anchors,"offset_checks",offsetChecks,
      "offset_oracle_sha256",HexFormat.of().formatHex(oracleDigest.digest()),"orc_conversion_checks",conversionChecks,
      "orc_conversion_oracle_sha256",HexFormat.of().formatHex(conversionDigest.digest()),"exact_boundary_evaluator_calls",exactBoundaryCalls,
      "recurring_rule_shapes",cyclesByShape.size(),"available_id_count",available.size(),"name_count",names.size(),"profile_count",profiles.size(),
      "cycle_count",cycles.size(),"same_rules_groups_verified",sameRules.size(),"per_zone",perZone);

    MessageDigest resolverDigest=MessageDigest.getInstance("SHA-256");long[] resolverCount={0};
    var examples=new TreeMap<String,Object>();Set<String> exampleNames=new HashSet<>(Arrays.asList(UNKNOWN));
    resolverCases(names,name->{
      TimeZone zone=TimeZone.getTimeZone(name);long epoch=epoch(formatter,zone);
      int offset=zone.getOffset(0);
      digestRow(resolverDigest,name,zone.getID(),offset,epoch);resolverCount[0]++;
      if(exampleNames.contains(name))examples.put(name,object("resolved_id",zone.getID(),"offset_at_unix_epoch_millis",offset,"orc_epoch_seconds",epoch));
    });
    var resolver=object("algorithm","compact-widths-1-through-4-all-valid-colon-forms-and-edge-names-v1",
      "case_count",resolverCount[0],"oracle_sha256",HexFormat.of().formatHex(resolverDigest.digest()),
      "examples",examples,"null_input","TimeZone.getTimeZone(String) throws NullPointerException; native ORC handles missing metadata before resolution");
    write(out.resolve("java-timezone-profiles.json"),artifact);
    write(out.resolve("java-timezone-profile-verification.json"),verification);
    write(out.resolve("java-timezone-resolver-oracle.json"),resolver);
    var provenance=object("configuration",configuration,"java_version",System.getProperty("java.version"),
      "java_vm_name",System.getProperty("java.vm.name"),"java_vm_version",System.getProperty("java.vm.version"),
      "tzdb_dat_sha256",sha(Files.readAllBytes(Path.of(System.getProperty("java.home"),"lib","tzdb.dat"))),
      "class_resources",new TreeMap<String,Object>());
    Map<String,Object> resources=(Map<String,Object>)provenance.get("class_resources");
    for(Class<?> cls:new Class<?>[]{TimeZone.class,SimpleTimeZone.class,ZI,zif,
        java.text.SimpleDateFormat.class,java.util.GregorianCalendar.class,
        Class.forName("sun.util.calendar.BaseCalendar"),Class.forName("sun.util.calendar.Gregorian"),
        Class.forName("sun.util.calendar.CalendarDate"),SerializationUtils.class}) {
      String resource="/"+cls.getName().replace('.','/')+".class";
      try(var stream=cls.getResourceAsStream(resource)){resources.put(cls.getName(),sha(stream.readAllBytes()));}
    }
    write(out.resolve("java-timezone-profile-provenance.json"),provenance);
    System.out.println("PASS offset_checks="+offsetChecks+" ORC_conversion_checks="+conversionChecks+" resolver_cases="+resolverCount[0]);
    System.out.println("profile_sha256="+sha(Files.readAllBytes(out.resolve("java-timezone-profiles.json"))));
  }
}
