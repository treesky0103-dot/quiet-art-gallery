package com.gallery.kiosk;

import android.content.ContentValues;
import android.content.Context;
import android.database.Cursor;
import android.database.sqlite.SQLiteDatabase;
import android.database.sqlite.SQLiteOpenHelper;

import java.io.File;
import java.util.ArrayList;
import java.util.List;

/** Indexed record of cache files that were ACTUALLY placed on the gallery
 * screen. This DB is independent of the 90-day artwork identity history in
 * WebView IndexedDB. Removing a cached JPEG must not remove any seen record. */
public final class ShownImageLedger extends SQLiteOpenHelper {
    public ShownImageLedger(Context context){super(context,"quiet-gallery-displayed-cache-v1.db",null,1);}
    @Override public void onCreate(SQLiteDatabase db){
        db.execSQL("CREATE TABLE shown (urlhash TEXT PRIMARY KEY NOT NULL, first_shown_ms INTEGER NOT NULL)");
        db.execSQL("CREATE INDEX idx_shown_first ON shown(first_shown_ms)");
    }
    @Override public void onUpgrade(SQLiteDatabase db,int oldVersion,int newVersion){
        // Keep historical display facts; this schema has no upgrades yet.
        throw new IllegalStateException("Unsupported display ledger schema");
    }
    public synchronized void recordDisplayed(String hash){
        if(hash==null||!hash.matches("[0-9a-f]{64}"))return;
        ContentValues row=new ContentValues();
        row.put("urlhash",hash);
        row.put("first_shown_ms",System.currentTimeMillis());
        getWritableDatabase().insertWithOnConflict("shown",null,row,SQLiteDatabase.CONFLICT_IGNORE);
    }
    public synchronized List<ShownFirstEviction.Entry> displayedFiles(File imageDir){
        List<ShownFirstEviction.Entry> found=new ArrayList<>();
        try(Cursor cursor=getReadableDatabase().rawQuery(
                "SELECT urlhash,first_shown_ms FROM shown ORDER BY first_shown_ms ASC",null)){
            while(cursor.moveToNext()){
                String hash=cursor.getString(0);
                if(hash==null||!hash.matches("[0-9a-f]{64}"))continue;
                File file=new File(imageDir,hash+".img");
                if(file.isFile()&&file.length()>0)
                    found.add(new ShownFirstEviction.Entry(hash,file.length(),cursor.getLong(1)));
            }
        }
        return found;
    }
    public synchronized void remove(String hash){
        if(hash!=null&&hash.matches("[0-9a-f]{64}"))
            getWritableDatabase().delete("shown","urlhash=?",new String[]{hash});
    }
    public synchronized int count(){
        try(Cursor c=getReadableDatabase().rawQuery("SELECT COUNT(*) FROM shown",null)){
            return c.moveToFirst()?c.getInt(0):0;
        }
    }
    public synchronized void clear(){getWritableDatabase().delete("shown",null,null);}
}
