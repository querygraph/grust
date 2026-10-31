import java.math.BigDecimal;
public class SdpDecimalDigits {
 public static void main(String[] args) {
  var starts=new java.util.ArrayList<Integer>();
  for(int i=0;i<=65535;i++)if(Character.digit((char)i,10)==0) starts.add(i);
  for(int i=0;i<=65535;i++) {
   int expected=-1;
   for(int start:starts)if(i>=start&&i<start+10)expected=i-start;
   if(expected!=Character.digit((char)i,10))throw new AssertionError(i);
  }
  System.out.println("{\"java_version\":\""+System.getProperty("java.version")+"\",\"starts\":"+starts+",\"bmp_mapping_verified\":true}");
 }
}
