package com.quietart.gallery;

import android.app.Activity;
import android.content.Intent;
import android.content.SharedPreferences;
import android.content.UriPermission;
import android.database.Cursor;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Matrix;
import android.media.ExifInterface;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.provider.DocumentsContract;
import android.view.Gravity;
import android.view.View;
import android.view.WindowManager;
import android.widget.Button;
import android.widget.FrameLayout;
import android.widget.ImageView;
import android.widget.LinearLayout;
import android.widget.TextView;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.LocalDate;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Random;
import java.util.Set;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** Local, offline slideshow of the user's selected Art folder. */
public class MainActivity extends Activity {
    private static final int REQUEST_FOLDER = 2001;
    private static final long PERIOD = 30000L;
    private static final String[] COLUMNS = {
        DocumentsContract.Document.COLUMN_DOCUMENT_ID,
        DocumentsContract.Document.COLUMN_DISPLAY_NAME,
        DocumentsContract.Document.COLUMN_MIME_TYPE
    };
    private final Handler ui = new Handler(Looper.getMainLooper());
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private final List<Picture> pictures = new ArrayList<>();
    private final Map<String, String> labels = new HashMap<>();
    private SharedPreferences prefs;
    private Uri tree;
    private FrameLayout frame;
    private ImageView artwork;
    private TextView caption;
    private TextView state;
    private LinearLayout menu;
    private String day = "";
    private String signature = "";
    private int index = 0;
    private int token = 0;
    private boolean active = false;
    private boolean destroyed = false;

    private static class Picture {
        final String id, path;
        final Uri uri;
        Picture(String id, String path, Uri uri) {
            this.id=id; this.path=path; this.uri=uri;
        }
    }
    private static class Folder {
        final String id, prefix;
        Folder(String id,String prefix) {this.id=id;this.prefix=prefix;}
    }
    private static class Scan {
        final List<Picture> images = new ArrayList<>();
        final Map<String,String> captions = new HashMap<>();
    }
    private final Runnable tick = new Runnable() {
        @Override public void run() {
            if (!active || destroyed || tree == null) return;
            if (!today().equals(day)) {
                reload();
            } else {
                nextPicture();
                ui.postDelayed(this, PERIOD);
            }
        }
    };
    private static String today() { return LocalDate.now().toString(); }
    private int dp(int value) {
        return (int)(getResources().getDisplayMetrics().density * value + 0.5f);
    }
    private void hideSystemBars() {
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_FULLSCREEN |
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION |
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN |
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION |
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
    }
    @Override public void onCreate(Bundle stateBundle) {
        super.onCreate(stateBundle);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        prefs=getSharedPreferences("quiet_art_local", MODE_PRIVATE);
        buildInterface();
        String saved=prefs.getString("tree", "");
        if (!saved.isEmpty()) {
            Uri stored=Uri.parse(saved);
            for (UriPermission perm:getContentResolver().getPersistedUriPermissions()) {
                if (perm.isReadPermission() && stored.equals(perm.getUri())) {
                    tree=stored;
                    break;
                }
            }
        }
        if (tree!=null) reload();
        else status("태블릿에 이미지를 넣은 후 Art 폴더를 선택하세요.");
    }
    private void buildInterface() {
        frame=new FrameLayout(this);
        frame.setBackgroundColor(Color.BLACK);
        artwork=new ImageView(this);
        artwork.setBackgroundColor(Color.BLACK);
        artwork.setScaleType(ImageView.ScaleType.MATRIX);
        frame.addView(artwork, new FrameLayout.LayoutParams(-1,-1));
        artwork.setOnClickListener(v->menu.setVisibility(menu.getVisibility()==View.VISIBLE?View.GONE:View.VISIBLE));
        caption=new TextView(this);
        caption.setTextColor(Color.WHITE);
        caption.setTextSize(14);
        caption.setGravity(Gravity.CENTER);
        caption.setBackgroundColor(0xAA000000);
        caption.setPadding(dp(14),dp(8),dp(14),dp(8));
        FrameLayout.LayoutParams cap=new FrameLayout.LayoutParams(-1,-2,Gravity.BOTTOM);
        cap.setMargins(dp(12),0,dp(12),dp(14));
        frame.addView(caption,cap);
        caption.setVisibility(View.GONE);
        menu=new LinearLayout(this);
        menu.setOrientation(LinearLayout.VERTICAL);
        menu.setPadding(dp(14),dp(12),dp(14),dp(14));
        menu.setBackgroundColor(0xDD101010);
        FrameLayout.LayoutParams mp=new FrameLayout.LayoutParams(-1,-2,Gravity.TOP);
        mp.setMargins(dp(12),dp(34),dp(12),0);
        frame.addView(menu,mp);
        TextView title=new TextView(this);
        title.setText("고요한 미술관");
        title.setTextSize(21);
        title.setTextColor(Color.WHITE);
        menu.addView(title);
        state=new TextView(this);
        state.setTextColor(0xFFE0E0E0);
        state.setTextSize(13);
        state.setPadding(0,dp(10),0,dp(8));
        menu.addView(state);
        LinearLayout buttons=new LinearLayout(this);
        buttons.setOrientation(LinearLayout.HORIZONTAL);
        menu.addView(buttons);
        Button select=new Button(this);
        select.setAllCaps(false);
        select.setText("Art 폴더 선택");
        buttons.addView(select,new LinearLayout.LayoutParams(0,-2,1));
        select.setOnClickListener(v->chooseFolder());
        Button refresh=new Button(this);
        refresh.setAllCaps(false);
        refresh.setText("새로고침");
        buttons.addView(refresh,new LinearLayout.LayoutParams(0,-2,1));
        refresh.setOnClickListener(v->{if (tree!=null) reload();});
        setContentView(frame);
        hideSystemBars();
    }
    private void status(String message) {
        state.setText(message);
        menu.setVisibility(View.VISIBLE);
    }
    private void chooseFolder() {
        Intent i=new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        i.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        startActivityForResult(i, REQUEST_FOLDER);
    }
    @Override protected void onActivityResult(int request,int result,Intent data) {
        super.onActivityResult(request,result,data);
        if (request!=REQUEST_FOLDER || result!=RESULT_OK || data==null || data.getData()==null) return;
        try {
            Uri selected=data.getData();
            getContentResolver().takePersistableUriPermission(selected,Intent.FLAG_GRANT_READ_URI_PERMISSION);
            tree=selected;
            prefs.edit().putString("tree",selected.toString()).apply();
            reload();
        } catch (Exception ex) {
            status("폴더 접근 권한을 받지 못했습니다. 다시 선택하세요.");
        }
    }
    private void reload() {
        if (tree==null) return;
        ui.removeCallbacks(tick);
        int myToken=++token;
        Uri source=tree;
        status("Art 폴더의 이미지 목록을 읽는 중입니다…");
        io.execute(()->{
            try {
                Scan result=scan(source);
                ui.post(()->{
                    if (destroyed || token!=myToken || !source.equals(tree)) return;
                    if (result.images.isEmpty()) {
                        status("전시할 이미지가 없습니다. Art 폴더를 확인하세요.");
                        return;
                    }
                    install(result);
                });
            } catch (Exception e) {
                ui.post(()->{
                    if (!destroyed && token==myToken)
                        status("폴더 읽기에 실패했습니다: "+e.getClass().getSimpleName());
                });
            }
        });
    }
    private Scan scan(Uri selected) throws Exception {
        Scan result=new Scan();
        ArrayDeque<Folder> pending=new ArrayDeque<>();
        Set<String> visited=new HashSet<>();
        pending.add(new Folder(DocumentsContract.getTreeDocumentId(selected),""));
        while (!pending.isEmpty()) {
            Folder dir=pending.removeFirst();
            if (!visited.add(dir.id)) continue;
            Uri children=DocumentsContract.buildChildDocumentsUriUsingTree(selected,dir.id);
            try (Cursor c=getContentResolver().query(children,COLUMNS,null,null,null)) {
                if (c==null) continue;
                int idCol=c.getColumnIndex(DocumentsContract.Document.COLUMN_DOCUMENT_ID);
                int nameCol=c.getColumnIndex(DocumentsContract.Document.COLUMN_DISPLAY_NAME);
                int mimeCol=c.getColumnIndex(DocumentsContract.Document.COLUMN_MIME_TYPE);
                if (idCol<0 || nameCol<0 || mimeCol<0) continue;
                while (c.moveToNext()) {
                    String id=c.getString(idCol), name=c.getString(nameCol), mime=c.getString(mimeCol);
                    if (id==null || name==null) continue;
                    String relative=dir.prefix+name;
                    if (DocumentsContract.Document.MIME_TYPE_DIR.equals(mime)) {
                        pending.addLast(new Folder(id,relative+"/"));
                    } else {
                        Uri file=DocumentsContract.buildDocumentUriUsingTree(selected,id);
                        if (imageType(name,mime)) result.images.add(new Picture(id,relative,file));
                        if (dir.prefix.isEmpty() && name.equalsIgnoreCase("metadata.csv")) {
                            try (InputStream input=getContentResolver().openInputStream(file)) {
                                if (input!=null) parseMetadata(input,result.captions);
                            } catch (Exception ignored) {}
                        }
                    }
                }
            }
        }
        return result;
    }
    private static boolean imageType(String name,String mime) {
        String l=name.toLowerCase(Locale.ROOT);
        return l.endsWith(".jpg") || l.endsWith(".jpeg") || l.endsWith(".png") ||
               l.endsWith(".webp") || l.endsWith(".bmp") || l.endsWith(".gif") ||
               l.endsWith(".heic") || l.endsWith(".heif") || l.endsWith(".avif") ||
               (mime!=null && mime.startsWith("image/"));
    }
    private static List<String> csvRow(String raw) {
        List<String> result=new ArrayList<>();
        StringBuilder field=new StringBuilder();
        boolean quote=false;
        for (int i=0;i<raw.length();i++) {
            char c=raw.charAt(i);
            if (c=='"') {
                if (quote && i+1<raw.length() && raw.charAt(i+1)=='"') { field.append('"'); i++; }
                else quote=!quote;
            } else if (c==',' && !quote) {
                result.add(field.toString().trim());field.setLength(0);
            } else field.append(c);
        }
        result.add(field.toString().trim());
        return result;
    }
    private static void parseMetadata(InputStream stream,Map<String,String> out) throws Exception {
        ByteArrayOutputStream bytes=new ByteArrayOutputStream();
        byte[] buffer=new byte[8192];
        int n;
        while ((n=stream.read(buffer))!=-1) {
            if (bytes.size()+n>20*1024*1024) return;
            bytes.write(buffer,0,n);
        }
        String text=new String(bytes.toByteArray(),StandardCharsets.UTF_8).replace("\r","");
        String[] rows=text.split("\n");
        if (rows.length<2) return;
        List<String> headers=csvRow(rows[0].replace("\uFEFF",""));
        int path=-1, artist=-1, title=-1,year=-1;
        for (int i=0;i<headers.size();i++) {
            String col=headers.get(i).toLowerCase(Locale.ROOT);
            if (col.equals("relative_path") || col.equals("filename")) path=i;
            if (col.equals("artist")) artist=i;
            if (col.equals("title")) title=i;
            if (col.equals("year")) year=i;
        }
        if (path<0) return;
        for (int i=1;i<rows.length;i++) {
            List<String> r=csvRow(rows[i]);
            if (r.size()<=path || r.get(path).isEmpty()) continue;
            List<String> fragments=new ArrayList<>();
            if (artist>=0 && artist<r.size() && !r.get(artist).isEmpty()) fragments.add(r.get(artist));
            if (title>=0 && title<r.size() && !r.get(title).isEmpty()) fragments.add(r.get(title));
            if (year>=0 && year<r.size() && !r.get(year).isEmpty()) fragments.add(r.get(year));
            if (!fragments.isEmpty()) out.put(r.get(path).replace('\\','/'),String.join(" · ",fragments));
        }
    }
    private void install(Scan scan) {
        pictures.clear();
        pictures.addAll(scan.images);
        labels.clear();
        labels.putAll(scan.captions);
        pictures.sort(Comparator.comparing(p->p.path));
        long signatureHash=1125899906842597L;
        for (Picture p:pictures) signatureHash=31L*signatureHash+p.path.hashCode();
        signature=tree.toString()+":"+pictures.size()+":"+signatureHash;
        day=today();
        long salt=prefs.getLong("salt",0);
        if (salt==0) {
            salt=new java.security.SecureRandom().nextLong();
            if (salt==0) salt=1;
            prefs.edit().putLong("salt",salt).apply();
        }
        Collections.shuffle(pictures,new Random(salt ^ day.hashCode() ^ signature.hashCode()));
        boolean same=day.equals(prefs.getString("day","")) && signature.equals(prefs.getString("signature",""));
        index=same?Math.max(0,prefs.getInt("next",0)):0;
        prefs.edit().putString("day",day).putString("signature",signature).putInt("next",index).apply();
        menu.setVisibility(View.GONE);
        nextPicture();
        if (active) ui.postDelayed(tick,PERIOD);
    }
    private void nextPicture() {
        if (pictures.isEmpty()) return;
        if (index>=pictures.size()) index=0;
        Picture current=pictures.get(index++);
        prefs.edit().putInt("next",index).apply();
        int myToken=token;
        io.execute(()->{
            Bitmap loaded=null;
            try { loaded=loadBitmap(current.uri); } catch (Exception | OutOfMemoryError ignored) {}
            Bitmap fresh=loaded;
            ui.post(()->{
                if (destroyed || myToken!=token) {
                    if (fresh!=null) fresh.recycle();
                    return;
                }
                if (fresh==null) {
                    ui.removeCallbacks(tick);
                    if (active) ui.postDelayed(tick,800);
                    return;
                }
                Bitmap previous=null;
                if (artwork.getDrawable() instanceof android.graphics.drawable.BitmapDrawable)
                    previous=((android.graphics.drawable.BitmapDrawable)artwork.getDrawable()).getBitmap();
                artwork.setImageBitmap(fresh);
                artwork.post(()->showWithPortraitSizeRule(fresh));
                if (previous!=null && previous!=fresh && !previous.isRecycled()) previous.recycle();
                String text=labels.get(current.path);
                caption.setText(text==null?"":text);
                caption.setVisibility(text==null || text.isEmpty()?View.GONE:View.VISIBLE);
            });
        });
    }
    /**
     * Portrait sizing: preserve source aspect ratio, never crop.
     * If the portrait is smaller than 75% of display height at 1:1,
     * enlarge it only to 75%, as long as the screen width permits.
     * Otherwise use its natural size, downscaling when it would overflow.
     * Landscape and square images retain their original fit-inside behavior.
     */
    private void showWithPortraitSizeRule(Bitmap bitmap) {
        if (destroyed || bitmap == null || bitmap.isRecycled()) return;
        if (!(artwork.getDrawable() instanceof android.graphics.drawable.BitmapDrawable)) return;
        Bitmap shown=((android.graphics.drawable.BitmapDrawable)artwork.getDrawable()).getBitmap();
        if (shown != bitmap) return;
        int width=artwork.getWidth(), height=artwork.getHeight();
        if (width <= 0 || height <= 0) {
            artwork.post(()->showWithPortraitSizeRule(bitmap));
            return;
        }
        double scale=ImageScaleRules.scaleFor(
            bitmap.getWidth(),bitmap.getHeight(),width,height);
        Matrix matrix=new Matrix();
        matrix.setScale((float)scale,(float)scale);
        matrix.postTranslate(
            (float)((width-bitmap.getWidth()*scale)/2.0),
            (float)((height-bitmap.getHeight()*scale)/2.0)
        );
        artwork.setImageMatrix(matrix);
    }

    private Bitmap loadBitmap(Uri uri) throws Exception {
        BitmapFactory.Options bounds=new BitmapFactory.Options();
        bounds.inJustDecodeBounds=true;
        try (InputStream in=getContentResolver().openInputStream(uri)) {
            if (in==null) return null;
            BitmapFactory.decodeStream(in,null,bounds);
        }
        if (bounds.outWidth<=0 || bounds.outHeight<=0) return null;
        int w=Math.max(1080,getResources().getDisplayMetrics().widthPixels)*2;
        int h=Math.max(1920,getResources().getDisplayMetrics().heightPixels)*2;
        int sample=1;
        while (bounds.outWidth/sample>w || bounds.outHeight/sample>h) sample*=2;
        BitmapFactory.Options opt=new BitmapFactory.Options();
        opt.inSampleSize=sample;
        opt.inPreferredConfig=Bitmap.Config.ARGB_8888;
        Bitmap result;
        try (InputStream in=getContentResolver().openInputStream(uri)) {
            if (in==null) return null;
            result=BitmapFactory.decodeStream(in,null,opt);
        } catch (OutOfMemoryError error) {
            opt.inSampleSize*=4;
            try (InputStream in=getContentResolver().openInputStream(uri)) {
                result=in==null?null:BitmapFactory.decodeStream(in,null,opt);
            }
        }
        if (result==null) return null;
        int orientation=ExifInterface.ORIENTATION_NORMAL;
        try (InputStream input=getContentResolver().openInputStream(uri)) {
            if (input!=null) orientation=new ExifInterface(input).getAttributeInt(ExifInterface.TAG_ORIENTATION,ExifInterface.ORIENTATION_NORMAL);
        } catch (Exception ignored) {}
        int degrees=orientation==ExifInterface.ORIENTATION_ROTATE_90?90:orientation==ExifInterface.ORIENTATION_ROTATE_180?180:orientation==ExifInterface.ORIENTATION_ROTATE_270?270:0;
        if (degrees!=0) {
            try {
                Matrix m=new Matrix();
                m.postRotate(degrees);
                Bitmap rotated=Bitmap.createBitmap(result,0,0,result.getWidth(),result.getHeight(),m,true);
                if (rotated!=result) result.recycle();
                result=rotated;
            } catch (OutOfMemoryError ignored) {}
        }
        return result;
    }
    @Override protected void onPause() {
        active=false;
        ui.removeCallbacks(tick);
        super.onPause();
    }
    @Override protected void onResume() {
        super.onResume();
        active=true;
        hideSystemBars();
        if (!pictures.isEmpty()) {
            ui.removeCallbacks(tick);
            ui.postDelayed(tick,PERIOD);
        }
    }
    @Override public void onWindowFocusChanged(boolean focus) {
        super.onWindowFocusChanged(focus);
        if (focus) hideSystemBars();
    }
    @Override protected void onDestroy() {
        destroyed=true;
        active=false;
        token++;
        ui.removeCallbacks(tick);
        io.shutdownNow();
        artwork.setImageDrawable(null);
        super.onDestroy();
    }
}
