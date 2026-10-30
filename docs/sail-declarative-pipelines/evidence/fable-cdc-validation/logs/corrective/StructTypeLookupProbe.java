import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import org.apache.spark.sql.types.DataTypes;
import org.apache.spark.sql.types.Metadata;
import org.apache.spark.sql.types.StructField;
import org.apache.spark.sql.types.StructType;

/** Direct oracle for StructType.getFieldIndex and getFieldIndexCaseInsensitive on the pinned Spark jars.
 *  Spec format: repeated cases of  N, N field names, M, M query names  (one per line, raw). */
public final class StructTypeLookupProbe {
    private static String json(String s) {
        StringBuilder b = new StringBuilder("\"");
        s.codePoints().forEach(cp -> {
            if (cp == '"' || cp == '\\') b.append('\\').appendCodePoint(cp);
            else if (cp < 0x20) b.append(String.format("\\u%04x", cp));
            else b.appendCodePoint(cp);
        });
        return b.append('"').toString();
    }
    private static int index(scala.Option<Object> option) {
        return option.isDefined() ? ((Number) option.get()).intValue() : -1;
    }
    public static void main(String[] args) throws Exception {
        List<String> lines = Files.readAllLines(Path.of(args[0]), StandardCharsets.UTF_8);
        StringBuilder out = new StringBuilder();
        java.util.Properties info = new java.util.Properties();
        try (java.io.InputStream in = StructType.class.getClassLoader().getResourceAsStream("spark-version-info.properties")) {
            if (in != null) info.load(in);
        }
        out.append("{\"spark_version\":").append(json(info.getProperty("version", "unknown")))
           .append(",\"spark_revision\":").append(json(info.getProperty("revision", "unknown"))).append(",\"cases\":[");
        int i = 0; boolean firstCase = true;
        while (i < lines.size()) {
            int n = Integer.parseInt(lines.get(i++).trim());
            StructField[] fields = new StructField[n];
            List<String> names = new ArrayList<>();
            for (int k = 0; k < n; k++) { String name = lines.get(i++); names.add(name); fields[k] = new StructField(name, DataTypes.IntegerType, true, Metadata.empty()); }
            StructType schema = new StructType(fields);
            int m = Integer.parseInt(lines.get(i++).trim());
            if (!firstCase) out.append(','); firstCase = false;
            out.append("{\"fields\":[");
            for (int k = 0; k < n; k++) { if (k > 0) out.append(','); out.append(json(names.get(k))); }
            out.append("],\"queries\":[");
            for (int k = 0; k < m; k++) {
                String q = lines.get(i++);
                if (k > 0) out.append(',');
                out.append("{\"name\":").append(json(q)).append(",\"exact\":").append(index(schema.getFieldIndex(q)))
                   .append(",\"insensitive\":").append(index(schema.getFieldIndexCaseInsensitive(q))).append('}');
            }
            out.append("]}");
        }
        out.append("]}");
        System.out.println(out);
    }
}
