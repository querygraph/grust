public class DigitBlocks {
    public static void main(String[] a) {
        StringBuilder sb = new StringBuilder(); int n = 0;
        for (int c = 0; c <= 0xFFFF; c++) {
            if (Character.digit((char) c, 10) == 0) {
                boolean block = true;
                for (int d = 0; d < 10; d++) if (Character.digit((char) (c + d), 10) != d) block = false;
                if (block) { n++; sb.append(c).append(','); }
            }
        }
        int total = 0; for (int c = 0; c <= 0xFFFF; c++) if (Character.digit((char) c, 10) >= 0) total++;
        System.out.println(System.getProperty("java.version") + " blocks=" + n + " digits=" + total + " starts=" + sb);
    }
}
