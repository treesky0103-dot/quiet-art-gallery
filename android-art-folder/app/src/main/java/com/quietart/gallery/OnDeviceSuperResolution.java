package com.quietart.gallery;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.Color;

import org.tensorflow.lite.Interpreter;
import java.io.InputStream;
import java.nio.ByteBuffer;
import java.nio.ByteOrder;
import java.nio.FloatBuffer;
import java.util.ArrayList;
import java.util.List;
import java.util.function.BooleanSupplier;

/**
 * Real-ESRGAN x4v3, fully local TensorFlow Lite CPU inference.
 * Works on small source images, using overlapping 128px tiles. A too-large
 * source, model/runtime failure or cancelled frame returns null; caller
 * always displays the unmodified original instead.
 *
 * Trained-model super resolution can hallucinate details; never rewrite originals.
 */
public final class OnDeviceSuperResolution implements AutoCloseable {
    private static final int TILE=128, SCALE=4, OVERLAP=16;
    private static final int STEP=TILE-2*OVERLAP;
    private static final int MAX_TILES=36;
    private static final long MAX_OUTPUT_PIXELS=6_400_000;
    private static final String MODEL="real_esrgan_x4v3.tflite";
    private final Context context;
    private Interpreter interpreter;
    private ByteBuffer inputBytes, outputBytes;
    private FloatBuffer inputFloats,outputFloats;
    private boolean unavailable=false;

    public OnDeviceSuperResolution(Context context) {
        this.context=context.getApplicationContext();
    }
    public static boolean eligible(Bitmap bitmap, int viewW, int viewH) {
        if (bitmap==null || bitmap.isRecycled() || viewW<=0 || viewH<=0) return false;
        int w=bitmap.getWidth(),h=bitmap.getHeight();
        if(w<=0||h<=0||((long)w*h*SCALE*SCALE)>MAX_OUTPUT_PIXELS) return false;
        int nX=tileOffsets(w).size(),nY=tileOffsets(h).size();
        if(nX*nY>MAX_TILES) return false;
        // Only upscale when pixels will be visibly enlarged.
        double displayScale=ImageScaleRules.scaleFor(w,h,viewW,viewH);
        return displayScale>1.15;
    }
    private static List<Integer> tileOffsets(int length) {
        List<Integer> starts=new ArrayList<>();
        if(length<=TILE){starts.add(0);return starts;}
        int last=length-TILE;
        starts.add(0);
        int cursor=STEP;
        while(cursor<last) {
            starts.add(cursor);
            cursor+=STEP;
        }
        if(starts.get(starts.size()-1)!=last) starts.add(last);
        return starts;
    }
    private static int split(List<Integer> list,int index,int length) {
        if(index<=0)return 0;
        if(index>=list.size())return length;
        return (list.get(index-1)+list.get(index)+TILE)/2;
    }
    private void loadInterpreter() throws Exception {
        if(interpreter!=null || unavailable)return;
        ByteBuffer model;
        try(InputStream stream=context.getAssets().open(MODEL)) {
            java.io.ByteArrayOutputStream temp=new java.io.ByteArrayOutputStream();
            byte[] chunk=new byte[8192];
            int count;
            while((count=stream.read(chunk))>=0) {
                if(count>0) temp.write(chunk,0,count);
                if(temp.size()>10_000_000) throw new IllegalStateException("Model unexpectedly large");
            }
            byte[] arr=temp.toByteArray();
            if(arr.length<100_000)throw new IllegalStateException("Missing model bytes");
            model=ByteBuffer.allocateDirect(arr.length).order(ByteOrder.nativeOrder());
            model.put(arr).rewind();
        }
        Interpreter.Options options=new Interpreter.Options();
        options.setNumThreads(2);
        interpreter=new Interpreter(model,options);
        int[] inShape=interpreter.getInputTensor(0).shape();
        int[] outShape=interpreter.getOutputTensor(0).shape();
        if(inShape.length!=4 || inShape[0]!=1 || inShape[1]!=TILE ||
                inShape[2]!=TILE || inShape[3]!=3 ||
                outShape.length!=4 || outShape[0]!=1 ||
                outShape[1]!=TILE*SCALE || outShape[2]!=TILE*SCALE ||
                outShape[3]!=3) {
            close();
            unavailable=true;
            throw new IllegalStateException("Unrecognized model input/output shape");
        }
        inputBytes=ByteBuffer.allocateDirect(TILE*TILE*3*4).order(ByteOrder.nativeOrder());
        outputBytes=ByteBuffer.allocateDirect(TILE*TILE*SCALE*SCALE*3*4).order(ByteOrder.nativeOrder());
        inputFloats=inputBytes.asFloatBuffer();
        outputFloats=outputBytes.asFloatBuffer();
    }
    public synchronized Bitmap improve(Bitmap source, BooleanSupplier stillCurrent) {
        if (unavailable || source==null || source.isRecycled() || !stillCurrent.getAsBoolean())
            return null;
        Bitmap result=null;
        try {
            int width=source.getWidth(),height=source.getHeight();
            if(((long)width*height*SCALE*SCALE)>MAX_OUTPUT_PIXELS) return null;
            List<Integer> xs=tileOffsets(width), ys=tileOffsets(height);
            if(xs.size()*ys.size()>MAX_TILES) return null;
            loadInterpreter();
            if(interpreter==null) return null;
            result=Bitmap.createBitmap(width*SCALE,height*SCALE,Bitmap.Config.ARGB_8888);
            int[] row=new int[TILE*TILE];
            for(int iy=0;iy<ys.size();iy++) {
                int startY=ys.get(iy), top=split(ys,iy,height),bottom=split(ys,iy+1,height);
                for(int ix=0;ix<xs.size();ix++) {
                    if(!stillCurrent.getAsBoolean() || Thread.currentThread().isInterrupted()) {
                        result.recycle();return null;
                    }
                    int startX=xs.get(ix),left=split(xs,ix,width),right=split(xs,ix+1,width);
                    inputFloats.clear();
                    for(int y=0;y<TILE;y++) {
                        int sy=Math.min(height-1,startY+y);
                        int count=Math.min(TILE,Math.max(0,width-startX));
                        if(count>0) source.getPixels(row,0,count,startX,sy,count,1);
                        for(int x=0;x<TILE;x++) {
                            int pixel=row[Math.min(x,count-1)];
                            inputFloats.put(((pixel>>16)&255)/255f);
                            inputFloats.put(((pixel>>8)&255)/255f);
                            inputFloats.put((pixel&255)/255f);
                        }
                    }
                    inputBytes.rewind();outputBytes.rewind();
                    interpreter.run(inputBytes,outputBytes);
                    int segmentW=(right-left)*SCALE;
                    int segmentH=(bottom-top)*SCALE;
                    int[] pixels=new int[segmentW*segmentH];
                    int ix0=(left-startX)*SCALE,iy0=(top-startY)*SCALE;
                    for(int py=0;py<segmentH;py++) {
                        int fy=(iy0+py)*TILE*SCALE;
                        for(int px=0;px<segmentW;px++) {
                            int offset=(fy+(ix0+px))*3;
                            int r=toByte(outputFloats.get(offset));
                            int g=toByte(outputFloats.get(offset+1));
                            int b=toByte(outputFloats.get(offset+2));
                            pixels[py*segmentW+px]=Color.rgb(r,g,b);
                        }
                    }
                    result.setPixels(pixels,0,segmentW,left*SCALE,top*SCALE,segmentW,segmentH);
                }
            }
            if(!stillCurrent.getAsBoolean()) {
                result.recycle();return null;
            }
            return result;
        }catch(Exception | LinkageError | OutOfMemoryError error) {
            if(result!=null && !result.isRecycled()) result.recycle();
            // Never suspend the slideshow because of an unsupported model/device.
            if(error instanceof LinkageError || error instanceof IllegalStateException)
                unavailable=true;
            return null;
        }
    }
    private static int toByte(float value) {
        if(!Float.isFinite(value))return 0;
        return Math.max(0,Math.min(255,Math.round(value*255f)));
    }
    @Override public synchronized void close() {
        if(interpreter!=null) {
            interpreter.close();
            interpreter=null;
        }
        inputBytes=null;outputBytes=null;inputFloats=null;outputFloats=null;
    }
}
