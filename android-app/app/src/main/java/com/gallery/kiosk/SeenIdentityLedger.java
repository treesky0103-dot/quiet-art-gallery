package com.gallery.kiosk;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.List;

/** Synchronous 90-day identity journal. A display is claimed on native durable
 * storage BEFORE pixels are changed in the WebView. Independent of IndexedDB,
 * APK image cache, and the displayed-cache eviction ledger. */
public final class SeenIdentityLedger extends SQLiteOpenHelper {
    private static final long NINETY_DAYS_MS=90L*24*60*60*1000;
    public SeenIdentityLedger(Context ctx){super(ctx,"quiet-gallery-identity-90d-v1.db",null,1);}
    @Override public void onCreate(SQLiteDatabase db){
        db.execSQL("CREATE TABLE seen (identity_hash TEXT PRIMARY KEY NOT NULL, when_ms INTEGER NOT NULL)");
        db.execSQL("CREATE INDEX idx_seen_when ON seen(when_ms)");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int oldV,int newV){
        throw new IllegalStateException("Identity log must never be silently reset");
    }
    private String digest(String value) throws Exception {
        byte[] bytes=MessageDigest.getInstance("SHA-256").digest(value.getBytes(StandardCharsets.UTF_8));
        StringBuilder b=new StringBuilder();
        for(byte x:bytes)b.append(String.format(java.util.Locale.ROOT,"%02x",x&255));
        return b.toString();
    }
    /** All comparisons and writes occur inside one native transaction. */
    public synchronized boolean claim(List<String> keys){
        if(keys==null||keys.isEmpty()||keys.size()>12)return false;
        try {
            SQLiteDatabase db=getWritableDatabase();
            String[] digests=new String[keys.size()];
            for(int i=0;i<keys.size();i++){
                String key=keys.get(i);
                if(key==null||key.isEmpty()||key.length()>768)return false;
                digests[i]=digest(key);
            }
            long now=System.currentTimeMillis(),cutoff=now-NINETY_DAYS_MS;
            db.beginTransaction();
            try {
                for(String hash:digests){
                    try(Cursor c=db.rawQuery(
                        "SELECT when_ms FROM seen WHERE identity_hash=? LIMIT 1",
                        new String[]{hash})){
                        if(c.moveToFirst()&&c.getLong(0)>cutoff){
                            db.setTransactionSuccessful();
                            return false;
                        }
                    }
                }
                for(String hash:digests){
                    ContentValues row=new ContentValues();
                    row.put("identity_hash",hash);
                    row.put("when_ms",now);
                    db.insertWithOnConflict("seen",null,row,SQLiteDatabase.CONFLICT_REPLACE);
                }
                // Remove old records without losing records for still-active 90d.
                db.delete("seen","when_ms<?",new String[]{String.valueOf(cutoff)});
                db.setTransactionSuccessful();
                return true;
            }finally{db.endTransaction();}
        }catch(Exception e){return false;}
    }
    public synchronized boolean hasRecentlySeen(List<String> keys){
        if(keys==null||keys.isEmpty()||keys.size()>12)return false;
        try{
            SQLiteDatabase db=getReadableDatabase();
            long cutoff=System.currentTimeMillis()-NINETY_DAYS_MS;
            for(String key:keys){
                if(key==null||key.isEmpty()||key.length()>768)return true;
                try(Cursor c=db.rawQuery(
                    "SELECT when_ms FROM seen WHERE identity_hash=? LIMIT 1",
                    new String[]{digest(key)})){
                    if(c.moveToFirst()&&c.getLong(0)>cutoff)return true;
                }
            }
        }catch(Exception e){return true;} // Reject on storage failure.
        return false;
    }
}
