package com.cymatic.client.input

import android.content.Context
import android.graphics.PointF
import android.os.Build
import android.util.DisplayMetrics
import android.view.WindowManager
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.sqrt

class GazeManager(private val context: Context) {

    private var screenWidth = 0
    private var screenHeight = 0
    
    // Gaze state
    private var gazeDirection = FloatArray(3)
    private var gazeOrigin = FloatArray(3)
    private var currentTarget: GazeTarget? = null
    private var dwellTimer = 0f
    private val dwellTime = 2.0f // seconds
    
    // Reticle position
    private var reticlePosition = PointF(0f, 0f)
    private var reticleVisible = false
    
    // FOV constants — proper mapping for phone VR (~90° H, 60° V gives ~50% center comfort)
    private val hfovRad = Math.toRadians(90.0).toFloat()
    private val vfovRad = Math.toRadians(60.0).toFloat()
    
    // Calibration
    private var calibrationOffset = FloatArray(3)
    
    init {
        val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            val bounds = windowManager.currentWindowMetrics.bounds
            screenWidth = bounds.width()
            screenHeight = bounds.height()
            // Fallback if bounds empty (e.g., in test)
            if (screenWidth == 0 || screenHeight == 0) {
                @Suppress("DEPRECATION")
                val dm = DisplayMetrics()
                @Suppress("DEPRECATION")
                windowManager.defaultDisplay.getMetrics(dm)
                screenWidth = dm.widthPixels
                screenHeight = dm.heightPixels
            }
        } else {
            @Suppress("DEPRECATION")
            val displayMetrics = DisplayMetrics()
            @Suppress("DEPRECATION")
            windowManager.defaultDisplay.getMetrics(displayMetrics)
            screenWidth = displayMetrics.widthPixels
            screenHeight = displayMetrics.heightPixels
        }
    }
    
    /**
     * Update gaze direction. dt should be actual frame delta for dwell timing.
     * Default 1/60 kept for callers not tracking dt.
     */
    fun update(gazeDirection: FloatArray, dt: Float = 1f/60f) {
        if (gazeDirection.size < 3) return
        // Apply calibration offset if any (subtract to keep math consistent)
        this.gazeDirection = FloatArray(3) { i -> gazeDirection[i] - (calibrationOffset.getOrNull(i) ?: 0f) }
        projectToScreen()
        if (currentTarget != null) {
            dwellTimer += dt
        } else {
            dwellTimer = 0f
        }
    }
    
    private fun projectToScreen() {
        // Gaze direction is normalized forward -Z; handle degenerate length
        val len = sqrt(
            gazeDirection[0] * gazeDirection[0] +
            gazeDirection[1] * gazeDirection[1] +
            gazeDirection[2] * gazeDirection[2]
        )
        if (len < 1e-6f) {
            reticleVisible = false
            return
        }
        val invLen = 1f / len
        val gx = gazeDirection[0] * invLen
        val gy = gazeDirection[1] * invLen
        val gz = gazeDirection[2] * invLen

        // atan2 for yaw: 0 = looking -Z, positive yaw = look +X (right)
        val yaw = atan2(gx, -gz)
        // pitch: positive = look up ( -Y is gravity down, so invert)
        val pitch = asin((-gy).coerceIn(-1f, 1f))

        // Map to NDC using actual FOV halves, not hardcoded pi/2 & pi/4
        val hfovHalf = hfovRad / 2f
        val vfovHalf = vfovRad / 2f
        val normalizedX = (yaw / hfovHalf).coerceIn(-1f, 1f)
        val normalizedY = (pitch / vfovHalf).coerceIn(-1f, 1f)
        
        // Map to screen pixels
        reticlePosition.x = ((normalizedX + 1) / 2) * screenWidth
        reticlePosition.y = ((1 - normalizedY) / 2) * screenHeight
        
        // Clamp
        reticlePosition.x = reticlePosition.x.coerceIn(0f, screenWidth.toFloat())
        reticlePosition.y = reticlePosition.y.coerceIn(0f, screenHeight.toFloat())
        
        reticleVisible = true
    }
    
    fun setTarget(target: GazeTarget?) {
        currentTarget = target
        if (target == null) {
            dwellTimer = 0f
        }
    }
    
    fun getReticlePosition(): PointF = PointF(reticlePosition.x, reticlePosition.y)
    
    fun getDwellProgress(): Float = (dwellTimer / dwellTime).coerceIn(0f, 1f)
    
    fun isDwellComplete(): Boolean = dwellTimer >= dwellTime
    
    fun getGazeDirection(): FloatArray = gazeDirection.copyOf()
    
    fun getGazeOrigin(): FloatArray = gazeOrigin.copyOf()
    
    fun calibrate(offset: FloatArray) {
        calibrationOffset = offset.copyOf()
    }
    
    fun reset() {
        currentTarget = null
        dwellTimer = 0f
        reticleVisible = false
    }
    
    data class GazeTarget(
        val id: String,
        val name: String,
        val position: FloatArray,
        val bounds: FloatArray // minX, minY, maxX, maxY
    )
    
    companion object {
        private const val PI = 3.14159265359
    }
}
