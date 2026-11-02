import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** Direct JDK oracle for String.toLowerCase(Locale.ROOT): exhaustive scalar hash, the simple mapping table,
 *  a per-code-point final-sigma neighbour classification, and designed context strings. No Spark involved. */
public final class RootLowercaseProbe {
    private static long fnv1a64(long hash, byte[] bytes) {
        for (byte b : bytes) { hash ^= (b & 0xFFL); hash *= 0x100000001b3L; }
        return hash;
    }
    private static String cps(String s) {
        StringBuilder sb = new StringBuilder("[");
        s.codePoints().forEach(cp -> { if (sb.length() > 1) sb.append(','); sb.append(cp); });
        return sb.append(']').toString();
    }
    private static String ranges(List<Integer> cps) {
        StringBuilder sb = new StringBuilder("[");
        int i = 0;
        while (i < cps.size()) {
            int start = cps.get(i), end = start;
            while (i + 1 < cps.size() && cps.get(i + 1) == end + 1) { end = cps.get(++i); }
            if (sb.length() > 1) sb.append(',');
            sb.append('[').append(start).append(',').append(end).append(']');
            i++;
        }
        return sb.append(']').toString();
    }
    public static void main(String[] args) {
        Locale root = Locale.ROOT;
        long hash = 0xcbf29ce484222325L;
        StringBuilder table = new StringBuilder("[");
        List<Integer> sigmaNonFinalAfter = new ArrayList<>();   // X with lower("ΑΣ"+X) keeping σ
        List<Integer> sigmaNonFinalBefore = new ArrayList<>();  // X with lower("Α"+X+"Σ") keeping σ
        List<Integer> sigmaFinalAfterAlone = new ArrayList<>();  // X with lower(X+"Σ") giving ς
        List<Integer> sigmaNonFinalAfterInternal = new ArrayList<>();  // X with lower("ΑΣ"+X+"Α") keeping σ
        List<Integer> sigmaConnector = new ArrayList<>();  // X internal singly ("ΑΣ"+X+"Α" keeps σ) but doubled breaks the word
        List<Integer> letterBefore = new ArrayList<>();  // X with lower("ΑΣ"+X+"-Α") keeping σ: X may precede a letter connector
        List<Integer> letterAfter = new ArrayList<>();   // X with lower("ΑΣ-"+X+"Α") keeping σ: X may follow a letter connector
        List<Integer> numberBefore = new ArrayList<>();  // X with lower("ΑΣ"+X+".5Α") keeping σ
        List<Integer> numberAfter = new ArrayList<>();   // X with lower("ΑΣ1."+X+"Α") keeping σ
        List<Integer> numberConnector = new ArrayList<>();  // X with lower("ΑΣ1"+X+"1Α") keeping σ
        for (int cp = 0; cp <= 0x10FFFF; cp++) {
            if (cp >= 0xD800 && cp <= 0xDFFF) continue;
            String s = new String(Character.toChars(cp));
            String lower = s.toLowerCase(root);
            hash = fnv1a64(hash, lower.getBytes(StandardCharsets.UTF_8));
            hash = fnv1a64(hash, new byte[]{0});
            int simple = Character.toLowerCase(cp);
            if (simple != cp) {
                if (table.length() > 1) table.append(',');
                table.append('[').append(cp).append(',').append(simple).append(']');
            }
            String after = ("ΑΣ" + s).toLowerCase(root);
            if (after.charAt(1) == 'σ') sigmaNonFinalAfter.add(cp);
            String before = ("Α" + s + "Σ").toLowerCase(root);
            if (before.charAt(before.length() - 1) == 'σ') sigmaNonFinalBefore.add(cp);
            String alone = (s + "\u03A3").toLowerCase(root);
            if (alone.charAt(alone.length() - 1) == '\u03C2') sigmaFinalAfterAlone.add(cp);
            String internal = ("\u0391\u03A3" + s + "\u0391").toLowerCase(root);
            if (internal.charAt(1) == '\u03C3') sigmaNonFinalAfterInternal.add(cp);
            if (internal.charAt(1) == '\u03C3') {
                String doubled = ("\u0391\u03A3" + s + s + "\u0391").toLowerCase(root);
                if (doubled.charAt(1) == '\u03C2') sigmaConnector.add(cp);
            }
            if (("\u0391\u03A3" + s + "-\u0391").toLowerCase(root).charAt(1) == '\u03C3') letterBefore.add(cp);
            if (("\u0391\u03A3-" + s + "\u0391").toLowerCase(root).charAt(1) == '\u03C3') letterAfter.add(cp);
            if (("\u0391\u03A3" + s + ".5\u0391").toLowerCase(root).charAt(1) == '\u03C3') numberBefore.add(cp);
            if (("\u0391\u03A31." + s + "\u0391").toLowerCase(root).charAt(1) == '\u03C3') numberAfter.add(cp);
            if (("\u0391\u03A31" + s + "1\u0391").toLowerCase(root).charAt(1) == '\u03C3') numberConnector.add(cp);
        }
        table.append(']');
        String[] designed = args;
        if (args.length == 1 && args[0].startsWith("@")) {
            try {
                designed = java.nio.file.Files.readAllLines(java.nio.file.Path.of(args[0].substring(1)), StandardCharsets.UTF_8).toArray(new String[0]);
            } catch (java.io.IOException e) { throw new RuntimeException(e); }
        }
        StringBuilder strings = new StringBuilder("[");
        for (String s : designed) {
            if (strings.length() > 1) strings.append(',');
            strings.append("{\"input\":").append(cps(s)).append(",\"lower\":").append(cps(s.toLowerCase(root))).append('}');
        }
        strings.append(']');
        System.out.println("{\"java_runtime_version\":\"" + System.getProperty("java.runtime.version") + "\","
            + "\"java_vendor\":\"" + System.getProperty("java.vendor") + "\","
            + "\"scalar_fnv1a64\":\"" + Long.toHexString(hash) + "\","
            + "\"simple_lowercase\":" + table + ","
            + "\"sigma_non_final_after\":" + ranges(sigmaNonFinalAfter) + ","
            + "\"sigma_non_final_before\":" + ranges(sigmaNonFinalBefore) + ","
            + "\"sigma_final_after_alone\":" + ranges(sigmaFinalAfterAlone) + ","
            + "\"sigma_non_final_after_internal\":" + ranges(sigmaNonFinalAfterInternal) + ","
            + "\"sigma_connector\":" + ranges(sigmaConnector) + ","
            + "\"letter_before\":" + ranges(letterBefore) + ","
            + "\"letter_after\":" + ranges(letterAfter) + ","
            + "\"number_before\":" + ranges(numberBefore) + ","
            + "\"number_after\":" + ranges(numberAfter) + ","
            + "\"number_connector\":" + ranges(numberConnector) + ","
            + "\"strings\":" + strings + "}");
    }
}
