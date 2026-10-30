import java.lang.reflect.*;
import java.nio.charset.StandardCharsets;
import java.util.Base64;
public class BooleanProbe {
 public static void main(String[] args) throws Exception {
  System.out.println("PID\t" + ProcessHandle.current().pid());
  System.out.println("JAVA\t" + System.getProperty("java.runtime.version"));
  Class<?> klass = Class.forName("scala.collection.StringOps$");
  Object singleton = klass.getField("MODULE$").get(null);
  Method method = klass.getMethod("toBoolean$extension", String.class);
  for (String encoded : args) {
   String value = new String(Base64.getDecoder().decode(encoded), StandardCharsets.UTF_8);
   for (boolean trim : new boolean[]{false, true}) {
    try {
     Object result = method.invoke(singleton, trim ? value.trim() : value);
     System.out.println(encoded + "\t" + trim + "\tOK\t" + result);
    } catch (InvocationTargetException e) {
     Throwable cause = e.getCause();
     System.out.println(encoded + "\t" + trim + "\tERROR\t" + cause.getClass().getName());
    }
   }
  }
 }
}
