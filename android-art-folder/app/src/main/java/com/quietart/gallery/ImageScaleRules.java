package com.quietart.gallery;

/** Pure calculation of how to display artwork inside the tablet viewport. */
public final class ImageScaleRules {
    private static final double PORTRAIT_MIN_HEIGHT_FRACTION = 0.75;

    private ImageScaleRules() {}

    /**
     * Returns the uniform scale applied to bitmap pixels, not a new bitmap.
     * Portrait images smaller than 75% of screen height are enlarged to that
     * height, when possible without cropping. Portrait images already
     * at least 75% tall are not unnecessarily enlarged. Oversize originals
     * are reduced to fit. Landscape and square images always fit inside.
     */
    public static double scaleFor(int imageWidth, int imageHeight, int viewWidth, int viewHeight) {
        if (imageWidth <= 0 || imageHeight <= 0 || viewWidth <= 0 || viewHeight <= 0)
            throw new IllegalArgumentException("Image and viewport dimensions must be positive");
        double fit = Math.min((double)viewWidth / imageWidth, (double)viewHeight / imageHeight);
        if (imageHeight <= imageWidth) return fit;
        double minScale = Math.max(1.0,
                PORTRAIT_MIN_HEIGHT_FRACTION * viewHeight / imageHeight);
        // If a portrait is too wide for 75% height, avoid cropping and fit width.
        return Math.min(fit, minScale);
    }
}
