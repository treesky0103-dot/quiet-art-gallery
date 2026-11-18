package com.quietart.gallery;

/**
 * Deterministic, offline focal-window selection.
 * Scores each column using local visual detail + color contrast. This is a
 * saliency heuristic, NOT semantic art interpretation or guaranteed recognition.
 */
public final class FocusProjection {
    private FocusProjection() {}

    public static int bestStart(int[] rgb, int width, int height, int cropWidth) {
        if (width <= 0 || height <= 0 || cropWidth <= 0 ||
                cropWidth > width || rgb == null || rgb.length != width * height)
            throw new IllegalArgumentException("Bad image geometry");
        if (cropWidth == width) return 0;

        double[] col = new double[width];
        int[] prevRow = new int[width];
        double maxCol=0;
        for (int y=0; y<height; y++) {
            int prev=0;
            for (int x=0; x<width; x++) {
                int px=rgb[y*width+x];
                int r=(px>>16)&255, g=(px>>8)&255, b=px&255;
                int gray=(r*77+g*150+b*29)>>8;
                int chroma=Math.max(r,Math.max(g,b))-Math.min(r,Math.min(g,b));
                double edgeH=x>0?Math.abs(gray-prev):0;
                double edgeV=y>0?Math.abs(gray-prevRow[x]):0;
                // Contrast and detail dominate; saturation is a smaller cue.
                col[x]+=edgeH+edgeV+0.12*chroma;
                prev=gray;
                prevRow[x]=gray;
            }
        }
        double[] prefix = new double[width+1];
        for(int x=0;x<width;x++) {
            prefix[x+1]=prefix[x]+col[x];
            maxCol+=col[x];
        }
        int best=(width-cropWidth)/2;
        double mean=(maxCol/width);
        double bestScore=Double.NEGATIVE_INFINITY;
        int steps=width-cropWidth;
        for (int left=0;left<=steps;left++) {
            double center=(left+cropWidth*0.5-width*0.5)/(Math.max(1,width*0.5));
            double centerPenalty=mean*cropWidth*0.15*center*center;
            double score=prefix[left+cropWidth]-prefix[left]-centerPenalty;
            if (score > bestScore+1e-7) {
                bestScore=score; best=left;
            } else if (Math.abs(score-bestScore)<1e-7) {
                // Uniform areas favor a central crop (rather than the left edge).
                if (Math.abs(left-steps/2.0)<Math.abs(best-steps/2.0)) best=left;
            }
        }
        return best;
    }
}
