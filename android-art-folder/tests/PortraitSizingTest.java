import com.quietart.gallery.ImageScaleRules;

public final class PortraitSizingTest {
    private static int checks;
    private static void eq(String description, double expected, double actual) {
        if (Math.abs(expected-actual)>1e-6)
            throw new AssertionError(description+" expected="+expected+" actual="+actual);
        checks++;
        System.out.println("PASS "+description+" scale="+actual);
    }
    private static void invalid(String description, int a, int b, int c, int d) {
        try {
            ImageScaleRules.scaleFor(a,b,c,d);
            throw new AssertionError(description+" failed to reject invalid geometry");
        } catch (IllegalArgumentException expected) {
            checks++;
            System.out.println("PASS "+description);
        }
    }
    public static void main(String[] args) {
        eq("Small portrait must reach 75% screen height",1.92,
                ImageScaleRules.scaleFor(300,500,800,1280));
        eq("Already >75% medium portrait stays native size",1.0,
                ImageScaleRules.scaleFor(800,1100,800,1280));
        eq("At exactly 75% stays native size",1.0,
                ImageScaleRules.scaleFor(600,960,800,1280));
        eq("Large portrait reduces to fit screen",0.64,
                ImageScaleRules.scaleFor(1200,2000,800,1280));
        eq("Wider portrait does not crop when 75% cannot fit",800.0/700,
                ImageScaleRules.scaleFor(700,800,800,1280));
        eq("Landscape retains fit inside rule",0.5,
                ImageScaleRules.scaleFor(1600,900,800,1280));
        eq("Square retains fit inside rule",8.0,
                ImageScaleRules.scaleFor(100,100,800,1280));
        eq("Tiny portrait scales to 75%",2.4,
                ImageScaleRules.scaleFor(200,400,800,1280));
        eq("Portrait above native 75% is not enlarged on large tablet",1.0,
                ImageScaleRules.scaleFor(1000,1900,2000,2400));
        invalid("Reject zero image height",200,0,800,1280);
        invalid("Reject zero viewport width",200,400,0,1280);
        System.out.println("ALL "+checks+" geometry cases passed");
    }
}
