package com.gallery.kiosk;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

/** Pure, deterministic deletion planner. Never evicts a file without a real
 * recorded display timestamp. It does not touch the independent 90-day
 * artwork identity log. */
public final class ShownFirstEviction {
    public static final class Entry {
        public final String hash;
        public final long bytes;
        public final long firstShownAt;
        public Entry(String hash,long bytes,long firstShownAt){
            this.hash=hash;this.bytes=bytes;this.firstShownAt=firstShownAt;
        }
    }
    private ShownFirstEviction(){}
    public static List<String> select(
            long cacheBytes,long incomingBytes,long maxBytes,long batchBytes,
            long diskFreeBytes,long reserveBytes,
            List<Entry> entries,Set<String> protectedHashes){
        if(incomingBytes<0||cacheBytes<0||maxBytes<=0||batchBytes<=0||
           diskFreeBytes<0||reserveBytes<0)throw new IllegalArgumentException("invalid cache budget");
        if(cacheBytes+incomingBytes<=maxBytes && diskFreeBytes>=incomingBytes+reserveBytes)
            return Collections.emptyList();
        // Crossing 8 GiB evicts a whole 1 GiB batch, rather than removing a
        // few JPEGs after every picture is downloaded.
        long byQuota=Math.max(0L,maxBytes-batchBytes);
        long byFree=Math.max(0L,cacheBytes+diskFreeBytes-reserveBytes-incomingBytes);
        long target=Math.min(byQuota,byFree);
        List<Entry> ordered=new ArrayList<>(entries);
        ordered.sort(Comparator.comparingLong((Entry e)->e.firstShownAt).thenComparing(e->e.hash));
        Set<String> protect=protectedHashes==null?Collections.emptySet():protectedHashes;
        Set<String> used=new HashSet<>();
        List<String> victims=new ArrayList<>();
        long remaining=cacheBytes;
        for(Entry e:ordered){
            if(remaining<=target)break;
            if(e==null||e.hash==null||!e.hash.matches("[0-9a-f]{64}")||
               e.firstShownAt<=0||e.bytes<=0||protect.contains(e.hash)||!used.add(e.hash))
                continue;
            victims.add(e.hash);
            remaining=Math.max(0L,remaining-e.bytes);
        }
        return victims; // an insufficient result is not permission to evict unseen images
    }
}
