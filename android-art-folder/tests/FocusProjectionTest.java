import com.quietart.gallery.FocusProjection;

public final class FocusProjectionTest {
    private static void check(boolean ok,String test) {
        if (!ok) throw new AssertionError(test);
        System.out.println("PASS "+test);
    }
    public static void main(String[] args) {
        final int w=360, h=150, cw=100;
        int[] blank=new int[w*h];
        java.util.Arrays.fill(blank,0xff666666);
        int center=FocusProjection.bestStart(blank,w,h,cw);
        check(Math.abs(center-130)<=1,"uniform image -> centered crop");
        int[] left=blank.clone();
        for(int y=10;y<h-10;y++)for(int x=8;x<60;x++)
            left[y*w+x]=((x+y)&1)==0?0xff000000:0xffffffff;
        int lx=FocusProjection.bestStart(left,w,h,cw);
        check(lx<70,"high contrast left subject -> left focal crop, got "+lx);
        int[] right=blank.clone();
        for(int y=10;y<h-10;y++)for(int x=300;x<348;x++)
            right[y*w+x]=((x+y)&1)==0?0xff000000:0xffffffff;
        int rx=FocusProjection.bestStart(right,w,h,cw);
        check(rx>195,"high contrast right subject -> right focal crop, got "+rx);
        check(FocusProjection.bestStart(blank,w,h,w)==0,"full width -> no crop");
        try {
            FocusProjection.bestStart(blank,w,h,w+1);
            throw new AssertionError("Invalid width accepted");
        } catch(IllegalArgumentException expected) {
            System.out.println("PASS invalid crop rejected");
        }
        System.out.println("ALL focal projection cases passed");
    }
}
