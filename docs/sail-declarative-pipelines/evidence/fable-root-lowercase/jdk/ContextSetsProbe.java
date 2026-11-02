import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Locale;

/** Context oracles for String.toLowerCase(Locale.ROOT): (1) the review-shaped enumeration (7 symbols, suffix length
 *  0..5, frames "AΣ"+s and "A"+s+"Σ", deduplicated in order), (2) a seeded xorshift64* random set over a wider
 *  alphabet, both reported as counts and FNV-1a hashes of the outputs in order; (3) named strings with outputs. */
public final class ContextSetsProbe {
    static final int[] ALPHABET = {
        0x41, 0x61, 0x31, 0x2E, 0x27, 0x5F, 0x2D, 0x22, 0x2C, 0x3A, 0x20, 0x09, 0x0A, 0x2019, 0x2018, 0x00B7, 0x2027, 0x066B,
        0x0301, 0x0345, 0x037A, 0x200D, 0x200C, 0x00AD, 0x200B, 0x2060, 0xFE0F, 0x0391, 0x03A3, 0x03C3, 0x03C2, 0x03B1, 0x0130, 0x0131, 0x0049, 0x0069,
        0x02B0, 0x02C0, 0x02E0, 0x1D2C, 0x2160, 0x2170, 0x24B6, 0x24D0, 0x00B2, 0x0660, 0x1C90, 0x10D0, 0x10400, 0x10428, 0x10570, 0x10597, 0x1C89, 0x1C8A,
        0x3042, 0x30A2, 0x4E00, 0xFF21, 0xFF41, 0xFF10, 0xFFFF, 0xFFFE,
    };
    private static long fnv(long h, byte[] b) { for (byte x : b) { h ^= (x & 0xFFL); h *= 0x100000001b3L; } return h; }
    private static String cps(String s) {
        StringBuilder sb = new StringBuilder("["); s.codePoints().forEach(cp -> { if (sb.length() > 1) sb.append(','); sb.append(cp); }); return sb.append(']').toString();
    }
    private static String utf16(String s) {
        StringBuilder sb = new StringBuilder("["); for (int i = 0; i < s.length(); i++) { if (i > 0) sb.append(','); sb.append((int) s.charAt(i)); } return sb.append(']').toString();
    }
    public static void main(String[] args) {
        Locale root = Locale.ROOT;
        // (1) enumeration
        int[] symbols = {0x41, 0x31, 0x2E, 0x27, 0x5F, 0x0301, 0x200D};
        LinkedHashSet<String> enumeration = new LinkedHashSet<>();
        for (int n = 0; n <= 5; n++) {
            int total = 1; for (int k = 0; k < n; k++) total *= symbols.length;
            for (int t = 0; t < total; t++) {
                StringBuilder suffix = new StringBuilder(); int v = t;
                int[] digits = new int[n];
                for (int k = n - 1; k >= 0; k--) { digits[k] = v % symbols.length; v /= symbols.length; }
                for (int k = 0; k < n; k++) suffix.appendCodePoint(symbols[digits[k]]);
                enumeration.add("AΣ" + suffix); enumeration.add("A" + suffix + "Σ");
            }
        }
        long h1 = 0xcbf29ce484222325L; int mismatchCount = 0;
        for (String s : enumeration) { h1 = fnv(h1, s.toLowerCase(root).getBytes(StandardCharsets.UTF_8)); h1 = fnv(h1, new byte[]{0}); }
        // (2) seeded random
        long state = 0x9E3779B97F4A7C15L; int count = 40000; long h2 = 0xcbf29ce484222325L;
        for (int i = 0; i < count; i++) {
            state ^= state >>> 12; state ^= state << 25; state ^= state >>> 27; long r = state * 0x2545F4914F6CDD1DL;
            int len = 1 + (int) Long.remainderUnsigned(r, 8);
            StringBuilder sb = new StringBuilder();
            for (int k = 0; k < len; k++) {
                state ^= state >>> 12; state ^= state << 25; state ^= state >>> 27; long q = state * 0x2545F4914F6CDD1DL;
                int cp = ALPHABET[(int) Long.remainderUnsigned(q, ALPHABET.length)];
                if (cp >= 0xD800 && cp <= 0xDFFF) sb.append((char) cp); else sb.appendCodePoint(cp);
            }
            h2 = fnv(h2, sb.toString().toLowerCase(root).getBytes(StandardCharsets.UTF_8)); h2 = fnv(h2, new byte[]{0});
        }
        // (3) named strings
        StringBuilder named = new StringBuilder("[");
        for (String s : args) {
            if (named.length() > 1) named.append(',');
            named.append("{\"input\":").append(utf16(s)).append(",\"lower\":").append(utf16(s.toLowerCase(root))).append('}');
        }
        named.append(']');
        System.out.println("{\"java_runtime_version\":\"" + System.getProperty("java.runtime.version") + "\",\"enumeration_count\":" + enumeration.size()
            + ",\"enumeration_fnv1a64\":\"" + Long.toHexString(h1) + "\",\"random_count\":" + count + ",\"random_seed\":\"9e3779b97f4a7c15\",\"random_fnv1a64\":\"" + Long.toHexString(h2)
            + "\",\"named\":" + named + "}");
    }
}
