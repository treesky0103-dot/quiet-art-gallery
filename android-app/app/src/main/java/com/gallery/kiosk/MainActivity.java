package com.gallery.kiosk;

import android.app.Activity;
import android.content.Intent;
import android.graphics.Color;
import android.graphics.BitmapFactory;
import android.net.Uri;
import android.os.Bundle;
import android.os.Handler;
import android.os.Looper;
import android.os.SystemClock;
import android.view.View;
import android.view.WindowManager;
import android.webkit.JavascriptInterface;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebResourceResponse;
import android.webkit.WebSettings;
import android.webkit.WebView;
import android.webkit.WebViewClient;

import org.json.JSONArray;
import org.json.JSONObject;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.File;
import java.io.FileInputStream;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.io.OutputStream;
import java.io.IOException;
import java.net.HttpURLConnection;
import java.net.URL;
import java.net.URLEncoder;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashMap;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final String ORIGIN = "appassets.gallery";
    private static final int EXPORT_CSV_REQUEST = 1002;
    private static final int IMPORT_CSV_REQUEST = 1003;
    private static final int MAX_IMPORT_BYTES = 128 * 1024 * 1024;
    private static final int MAX_JSON_BYTES = 4 * 1024 * 1024;
    private static final int MAX_IMAGE_BYTES = 8 * 1024 * 1024;
    private static final int MIN_IMAGE_SHORT_SIDE = 1000;
    private static final int MIN_IMAGE_LONG_SIDE = 1400;
    private static boolean acceptableResolution(File image) {
        BitmapFactory.Options opt = new BitmapFactory.Options();
        opt.inJustDecodeBounds = true;
        BitmapFactory.decodeFile(image.getAbsolutePath(), opt);
        int w=opt.outWidth,h=opt.outHeight;
        return w>0&&h>0&&Math.min(w,h)>=MIN_IMAGE_SHORT_SIDE&&Math.max(w,h)>=MIN_IMAGE_LONG_SIDE;
    }
    private static final long MAX_IMAGE_CACHE = 100L * 1024 * 1024;
    private static final long CLEAN_TO = 80L * 1024 * 1024;
    private final ExecutorService io = Executors.newSingleThreadExecutor();
    private WebView web;
    private File imageDir;
    private File exportFile;
    private File importFile;
    private long lastApiMs = 0L;
    private final Handler galleryClock = new Handler(Looper.getMainLooper());
    private Runnable galleryTicker;
    private long galleryDeadline;
    private static final long ART_INTERVAL_MS = 30000L;

    @Override public void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON);
        getWindow().setStatusBarColor(Color.BLACK);
        getWindow().setNavigationBarColor(Color.BLACK);
        imageDir = new File(getCacheDir(), "gallery-images");
        if (!imageDir.exists()) imageDir.mkdirs();
        importFile = new File(getCacheDir(), "gallery-import.csv");
        if (importFile.exists()) importFile.delete();
        File[] stale = imageDir.listFiles((folder,name)->name.endsWith(".part"));
        if (stale != null) for (File f : stale) f.delete();
        web = new WebView(this);
        web.setBackgroundColor(Color.rgb(17, 16, 15));
        web.setOverScrollMode(View.OVER_SCROLL_NEVER);
        WebSettings settings = web.getSettings();
        settings.setJavaScriptEnabled(true);
        settings.setDomStorageEnabled(true);
        settings.setAllowFileAccess(false);
        settings.setAllowContentAccess(false);
        settings.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
        settings.setJavaScriptCanOpenWindowsAutomatically(false);
        settings.setMediaPlaybackRequiresUserGesture(true);
        web.setWebChromeClient(new WebChromeClient());
        web.addJavascriptInterface(new Bridge(), "GalleryAndroid");
        web.setWebViewClient(new WebViewClient() {
            @Override public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
                Uri u=request.getUrl();
                return !("https".equals(u.getScheme()) && ORIGIN.equals(u.getHost()));
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView v, WebResourceRequest request) {
                Uri uri = request.getUrl();
                if (!"https".equals(uri.getScheme()) || !ORIGIN.equals(uri.getHost())) return null;
                String path = uri.getPath();
                if (path != null && path.equals("/art-image")) return artworkResponse(uri.getQueryParameter("u"));
                if (path != null && path.equals("/import-history")) {
                    try {
                        if (!importFile.isFile() || importFile.length() > MAX_IMPORT_BYTES) return response(404,"text/plain",new byte[0]);
                        return new WebResourceResponse("text/csv","UTF-8",200,"OK",Collections.singletonMap("Cache-Control","no-store"),new FileInputStream(importFile));
                    }catch(IOException e){return response(404,"text/plain",new byte[0]);}
                }
                String assetPath = (path == null || path.equals("/")) ? "index.html" : path.substring(1);
                boolean offlineImage=assetPath.matches("offline/fallback-(?:[0-9]|1[0-5])\\.jpg");
                if (!offlineImage && !Arrays.asList("index.html", "app.js", "core.js", "style.css", "icon-192.png", "icon-512.png", "manifest.webmanifest", "sw.js", "offline-deck.json").contains(assetPath))
                    return response(404, "text/plain", new byte[0]);
                try {
                    InputStream in = getAssets().open(assetPath);
                    String mime = assetPath.endsWith(".css") ? "text/css" : assetPath.endsWith(".js") ? "text/javascript" : assetPath.endsWith(".png") ? "image/png" : offlineImage ? "image/jpeg" : assetPath.endsWith(".json") ? "application/json" : assetPath.endsWith(".webmanifest") ? "application/manifest+json" : "text/html";
                    return new WebResourceResponse(mime, "UTF-8", 200, "OK", Collections.singletonMap("Cache-Control", "no-store"), in);
                } catch (IOException e) { return response(404, "text/plain", new byte[0]); }
            }
        });
        setContentView(web);
        immersive();
        web.loadUrl("https://" + ORIGIN + "/index.html");
    }
    private void immersive() {
        getWindow().getDecorView().setSystemUiVisibility(View.SYSTEM_UI_FLAG_FULLSCREEN |
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY |
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION | View.SYSTEM_UI_FLAG_LAYOUT_STABLE);
    }
    @Override public void onWindowFocusChanged(boolean hasFocus){super.onWindowFocusChanged(hasFocus);if(hasFocus)immersive();}
    // Native clock is anchored to uptime, rather than delayed artwork requests.
    private void stopGalleryTicker(){
        if(galleryTicker!=null)galleryClock.removeCallbacks(galleryTicker);
        galleryTicker=null;
    }
    private void startGalleryTicker(){
        stopGalleryTicker();
        galleryDeadline=SystemClock.uptimeMillis()+ART_INTERVAL_MS;
        galleryTicker=new Runnable(){
            @Override public void run(){
                if(web==null)return;
                web.evaluateJavascript("window.__galleryClockTick && window.__galleryClockTick();",null);
                galleryDeadline+=ART_INTERVAL_MS;
                long now=SystemClock.uptimeMillis();
                if(galleryDeadline<=now)galleryDeadline=now+ART_INTERVAL_MS;
                galleryClock.postAtTime(this,galleryDeadline);
            }
        };
        galleryClock.postAtTime(galleryTicker,galleryDeadline);
    }
    @Override protected void onPause(){stopGalleryTicker();super.onPause();}
    @Override protected void onResume(){super.onResume();
        if(web!=null)web.evaluateJavascript("window.__galleryForeground && window.__galleryForeground();",null);
    }
    @Override public void onBackPressed(){if(web!=null)web.evaluateJavascript("(function(){var e=document.getElementById('settings');if(e&&!e.hidden){document.getElementById('settings-done').click()}})();",null);}
    @Override protected void onDestroy(){stopGalleryTicker();if(web!=null){web.destroy();web=null;}io.shutdownNow();super.onDestroy();}

    private static WebResourceResponse response(int status, String mime, byte[] content) {
        return new WebResourceResponse(mime, "UTF-8", status, status == 200 ? "OK" : "Error", Collections.singletonMap("Cache-Control", "no-store"), new ByteArrayInputStream(content));
    }
    private static boolean safeImageUrl(String src) {
        try {
            URL u = new URL(src);
            if (!"https".equals(u.getProtocol()) || u.getPort() != -1 || u.getUserInfo() != null) return false;
            String host=u.getHost().toLowerCase(java.util.Locale.ROOT);
            return host.equals("upload.wikimedia.org") || host.equals("images.metmuseum.org") || host.equals("www.artic.edu") || host.equals("artic.edu") || host.equals("openaccess-cdn.clevelandart.org") || host.endsWith(".clevelandart.org");
        } catch(Exception e){return false;}
    }
    private static String hashUrl(String src) throws Exception {
        byte[] digest=MessageDigest.getInstance("SHA-256").digest(src.getBytes(StandardCharsets.UTF_8));
        StringBuilder b=new StringBuilder();for(byte v:digest)b.append(String.format(java.util.Locale.ROOT,"%02x",v&255));return b.toString();
    }
    private synchronized WebResourceResponse artworkResponse(String src) {
        if(src==null||!safeImageUrl(src))return response(403,"text/plain",new byte[0]);
        try {
            File f=new File(imageDir,hashUrl(src)+".img");
            if(f.isFile()&&f.length()>0){
                if(acceptableResolution(f)){f.setLastModified(System.currentTimeMillis());return new WebResourceResponse(sniffMime(f),null,200,"OK",Collections.singletonMap("Cache-Control","no-store"),new FileInputStream(f));}
                f.delete(); // Purge low-resolution cached files.
            }
            HttpURLConnection con=(HttpURLConnection)new URL(src).openConnection();
            con.setConnectTimeout(10000);con.setReadTimeout(18000);con.setInstanceFollowRedirects(false);
            con.setRequestProperty("Accept","image/jpeg,image/png,image/webp");
            try {
                if(con.getResponseCode()!=200)return response(502,"text/plain",new byte[0]);
                String mime=con.getContentType();
                if(mime==null||!(mime.toLowerCase().startsWith("image/jpeg")||mime.toLowerCase().startsWith("image/png")||mime.toLowerCase().startsWith("image/webp")))return response(415,"text/plain",new byte[0]);
                if(con.getContentLengthLong()>MAX_IMAGE_BYTES)return response(413,"text/plain",new byte[0]);
                File tmp=new File(imageDir,f.getName()+".part");int total=0;
                try(InputStream input=con.getInputStream(); FileOutputStream out=new FileOutputStream(tmp)) {
                    byte[] buf=new byte[16384];int read;
                    while((read=input.read(buf))>=0){total+=read;if(total>MAX_IMAGE_BYTES)throw new IOException("이미지 용량 제한 초과");out.write(buf,0,read);}
                    out.flush();
                }catch(Exception err){tmp.delete();throw err;}
                if(!acceptableResolution(tmp)){tmp.delete();return response(422,"text/plain",new byte[0]);}
                if(!tmp.renameTo(f)){tmp.delete();throw new IOException("캐시 저장 실패");}
                f.setLastModified(System.currentTimeMillis());
                pruneImageCache();
                return new WebResourceResponse(mime.split(";")[0],null,200,"OK",Collections.singletonMap("Cache-Control","no-store"),new FileInputStream(f));
            } finally {con.disconnect();}
        }catch(Exception e){return response(502,"text/plain",new byte[0]);}
    }
    private String sniffMime(File file) {
        try(FileInputStream in=new FileInputStream(file)) {
            byte[] b=new byte[12];if(in.read(b)<12)return "image/jpeg";
            if((b[0]&255)==0x89&&b[1]=='P'&&b[2]=='N'&&b[3]=='G')return "image/png";
            if(b[0]=='R'&&b[1]=='I'&&b[2]=='F'&&b[3]=='F'&&b[8]=='W'&&b[9]=='E'&&b[10]=='B'&&b[11]=='P')return "image/webp";
        }catch(Exception ignored){}
        return "image/jpeg";
    }
    private synchronized long cacheBytes(){long size=0;File[] files=imageDir.listFiles();if(files!=null)for(File f:files)if(f.isFile())size+=f.length();return size;}
    private synchronized void pruneImageCache() {
        if(cacheBytes()<=MAX_IMAGE_CACHE)return;
        File[] list=imageDir.listFiles((f,name)->name.endsWith(".img"));
        if(list==null)return;
        Arrays.sort(list,Comparator.comparingLong(File::lastModified));
        long sum=cacheBytes();
        for(File f:list){if(sum<=CLEAN_TO)break;long n=f.length();if(f.delete())sum-=n;}
    }
    private synchronized boolean clearImages(){File[] files=imageDir.listFiles();if(files==null)return true;boolean ok=true;for(File f:files)if(f.isFile()&&!f.delete())ok=false;return ok;}

    private String apiUrl(String type,String p) throws Exception {
        if (type.equals("cleveland")) {
            String[] parts=p.split(":",-1);if(parts.length!=2 || !Arrays.asList("Painting","Drawing","Print").contains(parts[0]))throw new IOException("유효하지 않은 작품 종류");
            int off=bounded(parts[1],0,1000000);
            return "https://openaccess-api.clevelandart.org/api/artworks/?cc0&has_image=1&type="+parts[0]+"&limit=100&skip="+off;
        }
        if(type.equals("chicago")||type.equals("chicagoMovement")){
            int page;
            String movementQuery=null;
            if(type.equals("chicagoMovement")){
                String[] parts=p.split(":",-1);
                if(parts.length!=2)throw new IOException("사조 조회 조건 오류");
                page=bounded(parts[1],1,100000);
                String[] ids={"renaissance","baroque","rococo","neoclassicism","romanticism","realism","impressionism","post-impressionism","expressionism","cubism","surrealism","abstract","contemporary"};
                String[] names={"Renaissance","Baroque","Rococo","Neoclassicism","Romanticism","Realism","Impressionism","Post-Impressionism","Expressionism","Cubism","Surrealism","Abstract Art","Contemporary Art"};
                for(int i=0;i<ids.length;i++)if(ids[i].equals(parts[0]))movementQuery=names[i];
                if(movementQuery==null)throw new IOException("허용되지 않은 사조");
            }else page=bounded(p,1,100000);
            JSONObject params=new JSONObject();
            JSONObject terms=new JSONObject().put("term",new JSONObject().put("is_public_domain",true));
            JSONObject exists=new JSONObject().put("exists",new JSONObject().put("field","image_id"));
            JSONObject q=new JSONObject().put("bool",new JSONObject().put("filter",new JSONArray().put(terms).put(exists)));
            if(movementQuery!=null){
                JSONObject mm=new JSONObject().put("query",movementQuery)
                    .put("fields",new JSONArray().put("style_title^5").put("style_titles^4").put("term_titles^2").put("artist_title").put("title"));
                q.getJSONObject("bool").put("must",new JSONArray().put(new JSONObject().put("multi_match",mm)));
            }
            params.put("query",q).put("page",page).put("limit",100);
            params.put("fields",new JSONArray().put("id").put("title").put("artist_title").put("image_id").put("is_public_domain").put("artwork_type_title").put("medium_display").put("thumbnail").put("style_title").put("style_titles").put("date_display").put("date_start"));
            return "https://api.artic.edu/api/v1/artworks/search?params="+URLEncoder.encode(params.toString(),"UTF-8");
        }
        if(type.equals("modernCommons")){
            String[] parts=p.split(":",-1);
            if(parts.length!=2)throw new IOException("현대 작품 검색 조건 오류");
            String[] ids={"2020s","2010s","contemporary","creator","century"};
            String[] cats={"2020s paintings","2010s paintings","Contemporary paintings",
                    "Paintings by Wikipedians","21st-century paintings"};
            String category=null;
            for(int i=0;i<ids.length;i++)if(ids[i].equals(parts[0]))category=cats[i];
            if(category==null)throw new IOException("허용되지 않은 현대 작품 분류");
            int off=bounded(parts[1],0,100000);
            String query="deepcategory:\""+category+"\"";
            return "https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrlimit=50&gsrsearch="+
                    URLEncoder.encode(query,"UTF-8")+"&gsroffset="+off+
                    "&prop=imageinfo&iiprop=url%7Csize%7Cmime%7Cextmetadata&iiurlwidth=2000&format=json&formatversion=2";
        }
        if(type.equals("openverseModern")){
            String[] parts=p.split(":",-1);
            if(parts.length!=2)throw new IOException("Openverse 검색 조건 오류");
            String[] terms={"digital painting","digital illustration","abstract digital artwork"};
            int idx=bounded(parts[0],0,terms.length-1),page=bounded(parts[1],1,4);
            return "https://api.openverse.org/v1/images/?q="+
                    URLEncoder.encode(terms[idx],"UTF-8")+
                    "&license=cc0%2Cpdm&source=wikimedia&page="+page+"&page_size=20";
        }
        if(type.equals("smithsonianCommons")){
            String[] parts=p.split(":",-1);
            if(parts.length!=3)throw new IOException("스미스소니언 작품 검색 인자 오류");
            String[] ids={"saam","nmaa"};
            String[][] categories={
                {"Paintings in the Smithsonian American Art Museum"},
                {"Paintings from China in the Freer Gallery",
                 "Paintings from Japan in the Freer Gallery of Art",
                 "Paintings from India in the Freer Gallery of Art"}
            };
            int museum=-1;
            for(int i=0;i<ids.length;i++)if(ids[i].equals(parts[0]))museum=i;
            if(museum<0)throw new IOException("등록되지 않은 스미스소니언 미술관");
            int catIndex=bounded(parts[1],0,categories[museum].length-1);
            int off=bounded(parts[2],0,100000);
            String query="deepcategory:\""+categories[museum][catIndex]+"\"";
            return "https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrlimit=50&gsrsearch="+
                URLEncoder.encode(query,"UTF-8")+"&gsroffset="+off+
                "&prop=imageinfo&iiprop=url%7Csize%7Cmime%7Cextmetadata&iiurlwidth=2000&format=json&formatversion=2";
        }
        if(type.equals("additionalCommons")){
            String[] parts=p.split(":",-1);
            if(parts.length!=2)throw new IOException("추가 미술관 검색 조건 오류");
            String[] ids={"rijks","nga","getty","smk","paris","london","walters","ngv","nsw","aus-nga","south-aus","queensland","auckland","dunedin","brasil-mnba","argentina-mnba","chile-mnba","peru-mali","colombia-mnc","uruguay-mnav","brasil-pina"};
            String[] cats={
                "Paintings in the Rijksmuseum Amsterdam",
                "Paintings in the National Gallery of Art (Washington, D.C.)",
                "Paintings in The J. Paul Getty Museum",
                "Paintings in Statens Museum for Kunst",
                "Paintings in Musée Carnavalet",
                "Paintings in the National Gallery, London",
                "Paintings in the Walters Art Museum",
                "Paintings in the National Gallery of Victoria",
                "Paintings in the Art Gallery of New South Wales",
                "Paintings in the National Gallery of Australia",
                "Paintings in the Art Gallery of South Australia",
                "Paintings in the Queensland Art Gallery",
                "Paintings in the Auckland Art Gallery",
                "Paintings in the Dunedin Public Art Gallery",
                "Brazilian paintings in the Museu Nacional de Belas Artes",
                "Paintings in the Museo Nacional de Bellas Artes (Argentina)",
                "Paintings in the Museo Nacional de Bellas Artes (Chile)",
                "Paintings in the Museo de Arte de Lima",
                "Paintings in the Museo Nacional de Colombia",
                "Paintings in the Museo Nacional de Artes Visuales",
                "Paintings in the Pinacoteca do Estado de São Paulo"
            };
            String category=null;
            for(int i=0;i<ids.length;i++)if(ids[i].equals(parts[0]))category=cats[i];
            if(category==null)throw new IOException("등록되지 않은 추가 미술관");
            int off=bounded(parts[1],0,100000);
            String query="deepcategory:\""+category+"\"";
            return "https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrlimit=50&gsrsearch="+
                URLEncoder.encode(query,"UTF-8")+"&gsroffset="+off+
                "&prop=imageinfo&iiprop=url%7Csize%7Cmime%7Cextmetadata&iiurlwidth=2000&format=json&formatversion=2";
        }
        if(type.equals("africanCommons")){
            String[] parts=p.split(":",-1);
            if(parts.length!=2)throw new IOException("아프리카 소장품 검색 인자 오류");
            String[] ids={"iziko","ethiopia","zimbabwe","johannesburg"};
            String[] cats={
                "Paintings in the South African National Gallery",
                "Paintings in the National Museum of Ethiopia",
                "Paintings in the National Gallery of Zimbabwe",
                "Paintings by Paul Signac in the Johannesburg Art Gallery"
            };
            String category=null;
            for(int i=0;i<ids.length;i++)if(ids[i].equals(parts[0]))category=cats[i];
            if(category==null)throw new IOException("등록되지 않은 아프리카 미술관");
            int off=bounded(parts[1],0,100000);
            String query="deepcategory:\""+category+"\"";
            return "https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrlimit=50&gsrsearch="+
                URLEncoder.encode(query,"UTF-8")+"&gsroffset="+off+
                "&prop=imageinfo&iiprop=url%7Csize%7Cmime%7Cextmetadata&iiurlwidth=2000&format=json&formatversion=2";
        }
        if(type.equals("asianCommons")){
            String[] parts=p.split(":",-1);
            if(parts.length!=2)throw new IOException("아시아 검색 인자 오류");
            String[] ids={"korea","tokyo","kyoto","nara","taipei"};
            String[] cats={"Paintings in the National Museum of Korea","Japanese paintings in the Tokyo National Museum","Paintings in the Kyoto National Museum","Paintings in the Nara National Museum","Paintings in the National Palace Museum"};
            String category=null;
            for(int i=0;i<ids.length;i++)if(ids[i].equals(parts[0]))category=cats[i];
            if(category==null)throw new IOException("허용되지 않은 박물관");
            int off=bounded(parts[1],0,100000);
            String query="deepcategory:\""+category+"\"";
            return "https://commons.wikimedia.org/w/api.php?action=query&generator=search&gsrnamespace=6&gsrlimit=50&gsrsearch="+
                URLEncoder.encode(query,"UTF-8")+"&gsroffset="+off+
                "&prop=imageinfo&iiprop=url%7Csize%7Cmime%7Cextmetadata&iiurlwidth=2000&format=json&formatversion=2";
        }
        if(type.equals("metSearch")){
            String[] parts=p.split(":",-1);if(parts.length!=2||!Arrays.asList("11","9","21","6").contains(parts[0]))throw new IOException("잘못된 검색 조건");
            int off=bounded(parts[1],0,9900);
            return "https://collectionapi.metmuseum.org/public/collection/v1.1/search?hasImages=true&departmentId="+parts[0]+"&limit=100&offset="+off;
        }
        if(type.equals("metObject")){
            int id=bounded(p,1,Integer.MAX_VALUE);
            return "https://collectionapi.metmuseum.org/public/collection/v1/objects/"+id;
        }
        throw new IOException("허용되지 않은 데이터 출처");
    }
    private static int bounded(String value,int min,int max) throws IOException {
        try{int n=Integer.parseInt(value);if(n>=min&&n<=max)return n;}catch(Exception ignored){}throw new IOException("범위를 벗어난 요청");
    }
    private static String fetchJson(String url) throws Exception {
        HttpURLConnection conn=(HttpURLConnection)new URL(url).openConnection();
        conn.setConnectTimeout(10000);conn.setReadTimeout(16000);conn.setInstanceFollowRedirects(false);
        conn.setRequestProperty("Accept","application/json");
        conn.setRequestProperty("User-Agent","QuietArtGallery/1.6.6 (https://github.com/treesky0103-dot/quiet-art-gallery; personal art display)");
        conn.setRequestProperty("AIC-User-Agent","Quiet-Art-Gallery (local personal project)");
        try{
            if(conn.getResponseCode()!=200)throw new IOException("HTTP "+conn.getResponseCode());
            ByteArrayOutputStream out=new ByteArrayOutputStream();try(InputStream in=conn.getInputStream()){
                byte[] buf=new byte[16384];int count,total=0;
                while((count=in.read(buf))!=-1){total+=count;if(total>MAX_JSON_BYTES)throw new IOException("응답 크기 제한 초과");out.write(buf,0,count);}
            }
            String json=out.toString("UTF-8");
            new JSONObject(json);return json;
        }finally{conn.disconnect();}
    }
    final class Bridge {
        @JavascriptInterface public void startArtworkClock(int intervalMs){
            // A fixed 30-second clock. Do not accept arbitrary values.
            if(intervalMs!=30000)return;
            runOnUiThread(()->{if(web!=null)startGalleryTicker();});
        }
        @JavascriptInterface public void stopArtworkClock(){
            runOnUiThread(()->stopGalleryTicker());
        }
        // Use Android's actual view transform so all pixels and hit targets rotate
        // together on tablets, regardless of CSS body/fixed positioning behavior.
        @JavascriptInterface public void setDisplayRotation(boolean upsideDown){
            runOnUiThread(()->{
                if(web!=null)web.setRotation(upsideDown ? 180f : 0f);
            });
        }
        @JavascriptInterface public void requestJson(String type,String param,String rid){
            if(type==null||param==null||rid==null||!rid.matches("[0-9]{1,12}"))return;
            io.execute(()->{
                boolean ok=false;String result;
                try{
                    long pause=1000L-(System.currentTimeMillis()-lastApiMs);
                    if(pause>0)Thread.sleep(pause);
                    lastApiMs=System.currentTimeMillis();
                    result=fetchJson(apiUrl(type,param));ok=true;
                }
                catch(Exception e){result=e.getMessage()==null?"연결 실패":e.getMessage();}
                boolean success=ok;String payload=result;
                runOnUiThread(()->{if(web!=null){String js="window.__galleryResolve("+JSONObject.quote(rid)+","+success+","+JSONObject.quote(payload)+");";web.evaluateJavascript(js,null);}});
            });
        }
        @JavascriptInterface public String cacheStats(){try{return new JSONObject().put("bytes",cacheBytes()).toString();}catch(Exception e){return "{}";}}
        @JavascriptInterface public boolean clearImageCache(){return clearImages();}
        @JavascriptInterface public void beginHistoryExport(){
            try{exportFile=new File(getCacheDir(),"gallery-export.csv");try(FileOutputStream out=new FileOutputStream(exportFile,false)){out.write(new byte[]{(byte)0xEF,(byte)0xBB,(byte)0xBF});}}
            catch(Exception e){exportFile=null;}
        }
        @JavascriptInterface public boolean appendHistoryExport(String text){
            if(exportFile==null||text==null||text.length()>1500000)return false;
            try(FileOutputStream out=new FileOutputStream(exportFile,true)){out.write(text.getBytes(StandardCharsets.UTF_8));return true;}
            catch(Exception e){return false;}
        }
        @JavascriptInterface public void pickHistoryImport(){
            runOnUiThread(()->{
                Intent intent=new Intent(Intent.ACTION_OPEN_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("*/*");
                intent.addCategory(Intent.CATEGORY_DEFAULT);
                startActivityForResult(intent,IMPORT_CSV_REQUEST);
            });
        }
        @JavascriptInterface public void finishHistoryExport(){
            if(exportFile==null)return;
            runOnUiThread(()->{
                Intent intent=new Intent(Intent.ACTION_CREATE_DOCUMENT);
                intent.addCategory(Intent.CATEGORY_OPENABLE);
                intent.setType("text/csv");
                intent.putExtra(Intent.EXTRA_TITLE,"gallery-history-"+new java.text.SimpleDateFormat("yyyyMMdd",java.util.Locale.ROOT).format(new java.util.Date())+".csv");
                startActivityForResult(intent,EXPORT_CSV_REQUEST);
            });
        }
    }
    @Override protected void onActivityResult(int requestCode,int resultCode,Intent data){
        super.onActivityResult(requestCode,resultCode,data);
        if(requestCode==IMPORT_CSV_REQUEST){
            if(resultCode!=RESULT_OK||data==null||data.getData()==null)return;
            Uri selected=data.getData();
            io.execute(()->{
                String fail=null;
                try(InputStream in=getContentResolver().openInputStream(selected);
                    FileOutputStream out=new FileOutputStream(importFile,false)){
                    if(in==null)throw new IOException("파일을 열 수 없습니다");
                    byte[] bytes=new byte[16384];int n,total=0;
                    while((n=in.read(bytes))!=-1){
                        total+=n;
                        if(total>MAX_IMPORT_BYTES)throw new IOException("CSV가 128MB를 초과합니다");
                        out.write(bytes,0,n);
                    }
                    if(total==0)throw new IOException("빈 CSV 파일입니다");
                }catch(Exception e){importFile.delete();fail=e.getMessage()==null?"파일 읽기 실패":e.getMessage();}
                String msg=fail;
                runOnUiThread(()->{
                    if(web==null)return;
                    if(msg==null)web.evaluateJavascript("window.__galleryImportReady();",null);
                    else web.evaluateJavascript("window.__galleryImportError("+JSONObject.quote(msg)+");",null);
                });
            });
            return;
        }
        if(requestCode!=EXPORT_CSV_REQUEST||resultCode!=RESULT_OK||data==null||data.getData()==null||exportFile==null)return;
        try(InputStream in=new FileInputStream(exportFile);OutputStream out=getContentResolver().openOutputStream(data.getData())){
            if(out==null)throw new IOException("파일을 열 수 없습니다");byte[] bytes=new byte[16384];int n;
            while((n=in.read(bytes))!=-1)out.write(bytes,0,n);
        }catch(Exception ignored){}
    }
}
