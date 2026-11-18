package com.quietart.gallery;

import android.graphics.Bitmap;
import android.graphics.Color;
import android.media.FaceDetector;

/** Conservative local crop for landscape artworks; originals are not modified. */
public final class SmartArtworkCrop {
    private SmartArtworkCrop() {}

    public static Bitmap crop(Bitmap input, int displayW, int displayH) {
        if (input == null || input.isRecycled() ||
                displayW <= 0 || displayH <= 0 ||
                input.getWidth() <= input.getHeight())
            return input;
        int srcW=input.getWidth(), srcH=input.getHeight();
        int cropW=Math.max(1, Math.min(srcW, Math.round(srcH * (float)displayW/displayH)));
        if (cropW >= srcW * 0.92) return input;

        Bitmap thumb=null, faceImage=null;
        try {
            int tw=Math.max(2,Math.min(320,srcW));
            int th=Math.max(2,Math.round((float)srcH*tw/srcW));
            // FaceDetector supports even widths and RGB_565.
            tw&=~1;
            thumb=Bitmap.createScaledBitmap(input,tw,th,true);
            int[] pixels=new int[tw*th];
            thumb.getPixels(pixels,0,tw,0,0,tw,th);
            int sampleWidth=Math.max(1,Math.min(tw,Math.round((float)cropW*tw/srcW)));
            int left=FocusProjection.bestStart(pixels,tw,th,sampleWidth);
            int cropX=Math.max(0,Math.min(srcW-cropW,Math.round(left*(float)srcW/tw)));

            // Prioritize recognizable faces, while avoiding splitting a group.
            try {
                faceImage=thumb.copy(Bitmap.Config.RGB_565,false);
                if(faceImage!=null) {
                    FaceDetector.Face[] faces=new FaceDetector.Face[8];
                    int n=new FaceDetector(faceImage.getWidth(),faceImage.getHeight(),faces.length)
                            .findFaces(faceImage,faces);
                    if (n>0) {
                        float min=Float.MAX_VALUE,max=-Float.MAX_VALUE,sum=0;
                        float total=0;
                        for(int i=0;i<n;i++) {
                            if(faces[i]==null)continue;
                            android.graphics.PointF mid=new android.graphics.PointF();
                            faces[i].getMidPoint(mid);
                            float weight=Math.max(0.01f,faces[i].confidence());
                            min=Math.min(min,mid.x);max=Math.max(max,mid.x);
                            sum+=mid.x*weight;total+=weight;
                        }
                        if(total>0) {
                            if((max-min) > sampleWidth * 0.76f) return input;
                            float focus=sum/total * srcW/tw;
                            cropX=Math.max(0,Math.min(srcW-cropW,Math.round(focus-cropW*0.5f)));
                        }
                    }
                }
            } catch(RuntimeException ignored) {
                // Some devices do not support legacy face detection.
            }
            return Bitmap.createBitmap(input,cropX,0,cropW,srcH);
        } catch(RuntimeException | OutOfMemoryError ignored) {
            return input;
        } finally {
            if(faceImage!=null && !faceImage.isRecycled())faceImage.recycle();
            if(thumb!=null && thumb!=input && !thumb.isRecycled())thumb.recycle();
        }
    }
}
