import org.apache.spark.sql.types.StructType;
import org.apache.spark.SparkThrowable;
import java.nio.file.*;
import java.util.*;

public class MergeOracle {
    public static void main(String[] args) throws Exception {
        for (String line : Files.readAllLines(Paths.get(args[0]))) {
            if (line.isBlank() || line.startsWith("#")) continue;
            String[] parts = line.split("\\|\\|");
            StructType left = StructType.fromDDL(parts[0].trim());
            StructType right = StructType.fromDDL(parts[1].trim());
            System.out.println("CASE " + line);
            try {
                StructType merged = left.merge(right, true);
                System.out.println("  OK " + merged.toDDL());
            } catch (Throwable t) {
                System.out.println("  CLASS " + t.getClass().getName());
                System.out.println("  MESSAGE " + t.getMessage().replace("\n", "\\n"));
                if (t instanceof SparkThrowable) {
                    SparkThrowable st = (SparkThrowable) t;
                    System.out.println("  CONDITION " + st.getCondition());
                    System.out.println("  SQLSTATE " + st.getSqlState());
                    System.out.println("  PARAMS " + new TreeMap<>(st.getMessageParameters()));
                }
                Throwable c = t.getCause();
                System.out.println("  CAUSE " + (c == null ? "null" : c.getClass().getName() + ": " + c.getMessage().replace("\n", "\\n")));
            }
        }
    }
}
