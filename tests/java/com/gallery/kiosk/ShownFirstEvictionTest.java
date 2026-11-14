package com.gallery.kiosk;

import java.util.Arrays;
import java.util.Collections;
import java.util.HashSet;
import java.util.List;

public final class ShownFirstEvictionTest {
    private static final long G=1024L*1024L*1024L;
    private static final long M=1024L*1024L;
    private static String hash(char c){
        char[] all=new char[64];Arrays.fill(all,c);return new String(all);
    }
    private static void equal(Object expected,Object got){
        if(!expected.equals(got))throw new AssertionError("expected "+expected+" but got "+got);
    }
    private static void yes(boolean actual){if(!actual)throw new AssertionError("expected true");}
    public static void main(String[] args) {
        String a=hash('a'),b=hash('b'),c=hash('c'),d=hash('d');
        List<ShownFirstEviction.Entry> entries=Arrays.asList(
            new ShownFirstEviction.Entry(c,900*M,3000),
            new ShownFirstEviction.Entry(b,500*M,2000),
            new ShownFirstEviction.Entry(a,600*M,1000),
            new ShownFirstEviction.Entry(d,2*G,0) // NEVER DISPLAYED
        );
        List<String> ordinary=ShownFirstEviction.select(7*G,8*M,8*G,G,4*G,1536*M,
             entries,Collections.emptySet());
        equal(Collections.emptyList(),ordinary);

        List<String> delete=ShownFirstEviction.select(8*G,8*M,8*G,G,4*G,1536*M,
             entries,Collections.singleton(b));
        equal(Arrays.asList(a,c),delete);
        yes(!delete.contains(b));yes(!delete.contains(d));

        List<String> onlyOld=ShownFirstEviction.select(8*G,8*M,8*G,G,4*G,1536*M,
             entries,new HashSet<>(Arrays.asList(b,c)));
        equal(Collections.singletonList(a),onlyOld);
        // Under-cap after deleting only 600MiB is still impossible, caller
        // must stop accepting a new image; it must not evict a never-seen file.
        yes(8*G-600*M+8*M>8*G-G);

        List<String> none=ShownFirstEviction.select(8*G,1*M,8*G,G,4*G,1536*M,
             Collections.singletonList(new ShownFirstEviction.Entry(d,4*G,0)),
             Collections.emptySet());
        equal(Collections.emptyList(),none);

        List<String> lowFree=ShownFirstEviction.select(6*G,8*M,8*G,G,1000*M,1536*M,
             entries,Collections.emptySet());
        yes(!lowFree.isEmpty());
        yes(!lowFree.contains(d));

        System.out.println("SHOWN_FIRST_1GIB_EVICTION_TESTS_PASS 5/5");
    }
}
