import java.net.URL;
import java.util.Arrays;
import java.util.Locale;
import java.util.stream.Collectors;
import org.apache.spark.sql.types.DataTypes;
import org.apache.spark.sql.types.StructType;
import scala.Option;

/** Direct helper oracle only; this does not construct or execute a CDC flow. */
public final class KernelProbe {
    private static String quote(String value) {
        return "\"" + value.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }

    private static String strings(String[] values) {
        return Arrays.stream(values).map(KernelProbe::quote).collect(Collectors.joining(",", "[", "]"));
    }

    private static String cps(String value) {
        return value.codePoints().mapToObj(cp -> String.format(Locale.ROOT, "U+%04X", cp))
            .collect(Collectors.joining(" "));
    }

    private static String codepoint(int cp) {
        return new String(Character.toChars(cp));
    }

    private static String index(Option<Object> option) {
        return option.isDefined() ? option.get().toString() : "null";
    }

    private static StructType schema(String[] fields) {
        StructType result = new StructType();
        for (String field : fields) {
            result = result.add(field, DataTypes.IntegerType, true);
        }
        return result;
    }

    private static Integer linearLowercaseMatch(String[] fields, String query, boolean last) {
        Integer found = null;
        for (int i = 0; i < fields.length; i++) {
            if (fields[i].toLowerCase(Locale.ROOT).equals(query.toLowerCase(Locale.ROOT))) {
                found = i;
                if (!last) return found;
            }
        }
        return found;
    }

    private static void lookups(String label, String[] fields, String... queries) {
        StructType schema = schema(fields);
        for (String query : queries) {
            System.out.println("{\"kind\":\"lookup\",\"case\":" + quote(label)
                + ",\"fields\":" + strings(fields) + ",\"query\":" + quote(query)
                + ",\"exact_index\":" + index(schema.getFieldIndex(query))
                + ",\"insensitive_index\":" + index(schema.getFieldIndexCaseInsensitive(query))
                + ",\"first_root_lowercase_match\":" + linearLowercaseMatch(fields, query, false)
                + ",\"last_root_lowercase_match\":" + linearLowercaseMatch(fields, query, true) + "}");
        }
    }

    private static void lowercase(String label, String left, String right) {
        String lowerLeft = left.toLowerCase(Locale.ROOT);
        String lowerRight = right.toLowerCase(Locale.ROOT);
        StructType oneField = schema(new String[] {left});
        System.out.println("{\"kind\":\"lowercase\",\"case\":" + quote(label)
            + ",\"left_codepoints\":" + quote(cps(left))
            + ",\"right_codepoints\":" + quote(cps(right))
            + ",\"left_lower_codepoints\":" + quote(cps(lowerLeft))
            + ",\"right_lower_codepoints\":" + quote(cps(lowerRight))
            + ",\"root_lowercase_equal\":" + lowerLeft.equals(lowerRight)
            + ",\"equals_ignore_case\":" + left.equalsIgnoreCase(right)
            + ",\"spark_insensitive_index\":" + index(oneField.getFieldIndexCaseInsensitive(right)) + "}");
    }

    private static void origin(Class<?> cls) {
        URL origin = cls.getProtectionDomain().getCodeSource().getLocation();
        System.out.println("{\"kind\":\"class_origin\",\"class\":" + quote(cls.getName())
            + ",\"url\":" + quote(origin.toString()) + "}");
    }

    public static void main(String[] args) {
        System.out.println("{\"kind\":\"runtime\",\"java_version\":" + quote(System.getProperty("java.version"))
            + ",\"java_runtime_version\":" + quote(System.getProperty("java.runtime.version"))
            + ",\"java_vendor\":" + quote(System.getProperty("java.vendor"))
            + ",\"java_home\":" + quote(System.getProperty("java.home")) + "}");
        origin(StructType.class);
        origin(scala.Option.class);
        lookups("exact_duplicate_small", new String[] {"a", "A", "a"}, "a", "A", "missing");
        lookups("case_collision_two", new String[] {"a", "A"}, "a", "A");
        lookups("case_collision_two_reversed", new String[] {"A", "a"}, "a", "A");
        lookups("case_collision_four", new String[] {"a", "A", "b", "c"}, "a", "A");
        lookups("case_collision_five", new String[] {"a", "A", "b", "c", "d"}, "a", "A");
        lookups("case_collision_five_reordered", new String[] {"b", "c", "d", "a", "A"}, "a", "A");
        lookups("case_collision_five_reversed", new String[] {"A", "a", "b", "c", "d"}, "a", "A");
        lookups("exact_duplicate_large", new String[] {"a", "b", "c", "d", "e", "a"}, "a", "A");
        lookups("three_case_spellings_large", new String[] {"name", "Name", "NAME", "id", "seq", "extra"}, "name", "Name", "NAME");
        lookups("unique_control", new String[] {"id", "Name", "age"}, "NAME", "age", "missing");
        lowercase("vithkuqi", codepoint(0x10570), codepoint(0x10597));
        lowercase("cyrillic_tje", codepoint(0x1c89), codepoint(0x1c8a));
        lowercase("dotted_capital_i_vs_i", "\u0130", "i");
        lowercase("capital_i_vs_dotless_i", "I", "\u0131");
        lowercase("dotted_capital_i_vs_expansion", "\u0130", "i\u0307");
        lowercase("single_sigma_vs_final_sigma", "\u03a3", "\u03c2");
        lowercase("single_sigma_vs_sigma", "\u03a3", "\u03c3");
        lowercase("contextual_final_sigma", "A\u03a3", "a\u03c2");
        lowercase("contextual_nonfinal_sigma", "A\u03a3A", "a\u03c3a");
        lowercase("contextual_nonfinal_vs_final_sigma", "A\u03a3A", "a\u03c2a");
        lowercase("accented_e", "\u00c9", "\u00e9");
        lowercase("sharp_s", "\u1e9e", "\u00df");
    }
}
