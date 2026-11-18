package com.quietart.gallery;

import android.graphics.Bitmap;
import android.graphics.Color;
import android.content.Context;
import androidx.test.ext.junit.runners.AndroidJUnit4;
import androidx.test.platform.app.InstrumentationRegistry;
import org.junit.Test;
import org.junit.runner.RunWith;
import static org.junit.Assert.*;

@RunWith(AndroidJUnit4.class)
public final class ModelAndCropTest {
    @Test
    public void realEsrganRunsOfflineOnSmallImage() {
        Context context=InstrumentationRegistry.getInstrumentation().getTargetContext();
        Bitmap source=Bitmap.createBitmap(64,64,Bitmap.Config.ARGB_8888);
        source.eraseColor(Color.rgb(75,110,150));
        OnDeviceSuperResolution model=new OnDeviceSuperResolution(context);
        Bitmap result=null;
        try {
            result=model.improve(source,()->true);
            assertNotNull("TFLite model must actually infer",result);
            assertEquals(256,result.getWidth());
            assertEquals(256,result.getHeight());
            int center=result.getPixel(128,128);
            assertTrue("Generated RGB is nonempty",Color.red(center)+Color.green(center)+Color.blue(center)>0);
        } finally {
            if(result!=null)result.recycle();
            model.close();
            source.recycle();
        }
    }

    @Test
    public void cropPreservesUnchangedOriginal() {
        Bitmap wide=Bitmap.createBitmap(360,160,Bitmap.Config.ARGB_8888);
        wide.eraseColor(Color.rgb(92,60,25));
        Bitmap cropped=SmartArtworkCrop.crop(wide,600,1000);
        assertNotNull(cropped);
        assertEquals("Portrait crop width",96,cropped.getWidth());
        assertEquals("Crop retains full artwork height",160,cropped.getHeight());
        assertEquals("Original remains 360 px",360,wide.getWidth());
        if(cropped!=wide) cropped.recycle();
        wide.recycle();
    }
}
