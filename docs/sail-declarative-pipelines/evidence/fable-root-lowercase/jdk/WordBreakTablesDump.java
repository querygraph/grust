import java.lang.reflect.Field;
import java.lang.reflect.Method;
import java.text.BreakIterator;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Dumps the compiled word-break tables of BreakIterator.getWordInstance(Locale.ROOT) on this JDK:
 *  state tables, end/lookahead flags, category count and the category of every code point, as ranges.
 *  Needs --add-opens java.base/sun.text=ALL-UNNAMED. */
public final class WordBreakTablesDump {
    private static boolean isCased(int ch) {
        int type = Character.getType(ch);
        if (type == Character.LOWERCASE_LETTER || type == Character.UPPERCASE_LETTER || type == Character.TITLECASE_LETTER) return true;
        return (ch >= 0x02B0 && ch <= 0x02B8) || (ch >= 0x02C0 && ch <= 0x02C1) || (ch >= 0x02E0 && ch <= 0x02E4) || ch == 0x0345 || ch == 0x037A
            || (ch >= 0x1D2C && ch <= 0x1D61) || (ch >= 0x2160 && ch <= 0x217F) || (ch >= 0x24B6 && ch <= 0x24E9);
    }
    public static void main(String[] args) throws Exception {
        BreakIterator it = BreakIterator.getWordInstance(Locale.ROOT);
        Class<?> cls = it.getClass();
        while (!cls.getName().equals("sun.text.RuleBasedBreakIterator")) cls = cls.getSuperclass();
        Field f;
        f = cls.getDeclaredField("stateTable"); f.setAccessible(true); short[] state = (short[]) f.get(it);
        f = cls.getDeclaredField("backwardsStateTable"); f.setAccessible(true); short[] back = (short[]) f.get(it);
        f = cls.getDeclaredField("endStates"); f.setAccessible(true); boolean[] end = (boolean[]) f.get(it);
        f = cls.getDeclaredField("lookaheadStates"); f.setAccessible(true); boolean[] look = (boolean[]) f.get(it);
        f = cls.getDeclaredField("numCategories"); f.setAccessible(true); int num = (Integer) f.get(it);
        f = cls.getDeclaredField("checksum"); f.setAccessible(true); long checksum = (Long) f.get(it);
        Method lookup = cls.getDeclaredMethod("lookupCategory", int.class); lookup.setAccessible(true);
        StringBuilder sb = new StringBuilder();
        sb.append("{\"iterator_class\":\"").append(it.getClass().getName()).append("\",\"checksum\":\"").append(Long.toHexString(checksum)).append("\",");
        sb.append("\"java_runtime_version\":\"").append(System.getProperty("java.runtime.version")).append("\",");
        sb.append("\"num_categories\":").append(num).append(",\"num_states\":").append(end.length).append(",");
        sb.append("\"state_table\":["); for (int i = 0; i < state.length; i++) { if (i > 0) sb.append(','); sb.append(state[i]); } sb.append("],");
        sb.append("\"backwards_state_table\":["); for (int i = 0; i < back.length; i++) { if (i > 0) sb.append(','); sb.append(back[i]); } sb.append("],");
        sb.append("\"end_states\":["); for (int i = 0; i < end.length; i++) { if (i > 0) sb.append(','); sb.append(end[i] ? 1 : 0); } sb.append("],");
        sb.append("\"lookahead_states\":["); for (int i = 0; i < look.length; i++) { if (i > 0) sb.append(','); sb.append(look[i] ? 1 : 0); } sb.append("],");
        // category ranges over all code points (surrogate code points included as-is: the BMP table covers them)
        sb.append("\"category_ranges\":[");
        int start = 0; int current = (Integer) lookup.invoke(it, 0); boolean first = true;
        for (int cp = 1; cp <= 0x110000; cp++) {
            int cat = cp <= 0x10FFFF ? (Integer) lookup.invoke(it, cp) : Integer.MIN_VALUE;
            if (cat != current) {
                if (!first) sb.append(','); first = false;
                sb.append('[').append(start).append(',').append(cp - 1).append(',').append(current).append(']');
                start = cp; current = cat;
            }
        }
        sb.append("],");
        // ConditionalSpecialCasing.isCased, replicated over Character.getType of this JDK
        sb.append("\"cased_ranges\":[");
        int cs = -1; boolean cfirst = true;
        for (int cp = 0; cp <= 0x110000; cp++) {
            boolean cased = cp <= 0x10FFFF && isCased(cp);
            if (cased && cs < 0) cs = cp;
            if (!cased && cs >= 0) { if (!cfirst) sb.append(','); cfirst = false; sb.append('[').append(cs).append(',').append(cp - 1).append(']'); cs = -1; }
        }
        sb.append("]}");
        System.out.println(sb);
    }
}
