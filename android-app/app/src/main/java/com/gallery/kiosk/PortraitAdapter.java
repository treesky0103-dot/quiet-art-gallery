package com.gallery.kiosk;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.graphics.Color;
import android.graphics.Matrix;

import java.io.File;
import java.io.FileOutputStream;
import java.io.IOException;

/** CPU-only portrait smart-crop + quality-preserving scale, no external APIs. */
public final class PortraitAdapter {
    private static final int OUTPUT_W = 1000;
    private static final int OUTPUT_H = 1667;
    private static final float ASPECT = (float) OUTPUT_W / OUTPUT_H;
    private PortraitAdapter(){}

    public static boolean convert(File source, File target) {
        Bitmap original=null, window=null, rendered=null;
        try {
            BitmapFactory.Options bounds=new BitmapFactory.Options();
            bounds.inJustDecodeBounds=true;
            BitmapFactory.decodeFile(source.getAbsolutePath(),bounds);
            if(bounds.outWidth<320 || bounds.outHeight<430)return false;
            BitmapFactory.Options decode=new BitmapFactory.Options();
            int max=Math.max(bounds.outWidth,bounds.outHeight);
            decode.inSampleSize=1;
            while(max/decode.inSampleSize>3000)decode.inSampleSize*=2;
            decode.inPreferredConfig=Bitmap.Config.ARGB_8888;
            original=BitmapFactory.decodeFile(source.getAbsolutePath(),decode);
            if(original==null)return false;
            int w=original.getWidth(),h=original.getHeight();
            int cw=Math.min(w,Math.round(h*ASPECT));
            int ch=Math.min(h,Math.round(w/ASPECT));
            if(cw<380 || ch<630 || (float)OUTPUT_W/cw>2.9f)return false;
            // The crop must preserve the correct display aspect without padding.
            int x=0,y=0;
            if(cw<w)x=focusOffset(original,true,cw);
            if(ch<h)y=focusOffset(original,false,ch);
            window=Bitmap.createBitmap(original,x,y,cw,ch);
            rendered=Bitmap.createScaledBitmap(window,OUTPUT_W,OUTPUT_H,true);
            if(rendered==null)return false;
            try(FileOutputStream output=new FileOutputStream(target,false)){
                if(!rendered.compress(Bitmap.CompressFormat.JPEG,82,output))throw new IOException("Bitmap compress failed");
                output.flush();
            }
            BitmapFactory.Options check=new BitmapFactory.Options();
            check.inJustDecodeBounds=true;
            BitmapFactory.decodeFile(target.getAbsolutePath(),check);
            return check.outWidth==OUTPUT_W && check.outHeight==OUTPUT_H && target.length()>12000;
        }catch(Exception e){
            if(target.exists())target.delete();
            return false;
        }finally{
            if(rendered!=null&&rendered!=window&&!rendered.isRecycled())rendered.recycle();
            if(window!=null&&window!=original&&!window.isRecycled())window.recycle();
            if(original!=null&&!original.isRecycled())original.recycle();
        }
    }
    /** Low-cost edge/saturation saliency sliding window. Not semantic object detection. */
    private static int focusOffset(Bitmap image, boolean horizontal, int cropSize) {
        int length=horizontal?image.getWidth():image.getHeight();
        int end=length-cropSize;
        if(end<=0)return 0;
        Bitmap small=Bitmap.createScaledBitmap(image,96,96,true);
        try{
            final int side=96;
            int[] data=new int[side*side];
            small.getPixels(data,0,side,0,0,side,side);
            double[] relevance=new double[side];
            for(int j=1;j<side-1;j++)for(int i=1;i<side-1;i++){
                int rgb=data[j*side+i];
                double brightness=0.299*Color.red(rgb)+0.587*Color.green(rgb)+0.114*Color.blue(rgb);
                int right=data[j*side+i+1],bottom=data[(j+1)*side+i];
                double grad=Math.abs(brightness-(0.299*Color.red(right)+0.587*Color.green(right)+0.114*Color.blue(right)))+
                    Math.abs(brightness-(0.299*Color.red(bottom)+0.587*Color.green(bottom)+0.114*Color.blue(bottom)));
                double saturation=Math.max(Color.red(rgb),Math.max(Color.green(rgb),Color.blue(rgb)))-
                    Math.min(Color.red(rgb),Math.min(Color.green(rgb),Color.blue(rgb)));
                double energy=grad*.82+saturation*.18;
                relevance[horizontal?i:j]+=energy;
            }
            int width=Math.max(1,Math.min(side,Math.round(((float)cropSize/length)*side)));
            double[] cumulative=new double[side+1];
            for(int k=0;k<side;k++)cumulative[k+1]=cumulative[k]+relevance[k];
            double best=Double.NEGATIVE_INFINITY;int start=0;
            for(int k=0;k<=side-width;k++){
                double center=((double)k+width/2.0)/side;
                double score=(cumulative[k+width]-cumulative[k])*(1.0-.12*Math.abs(center-.5));
                if(score>best){best=score;start=k;}
            }
            return Math.max(0,Math.min(end,Math.round((float)start/side*length)));
        }finally{small.recycle();}
    }
}
