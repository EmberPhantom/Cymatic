package com.cymatic.client.input

import android.content.Context
import android.graphics.PointF
import android.util.DisplayMetrics
import android.view.WindowManager
import kotlinx.coroutines.channels.Channel
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.sqrt

class GazeManager(private val context: Context) {

    private val displayMetrics = DisplayMetrics()
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
    
    // Calibration
    private var calibrationOffset = FloatArray(3)
    
    init {
        val windowManager = context.getSystemService(Context.WINDOW_SERVICE) as WindowManager
        windowManager.defaultDisplay.getMetrics(displayMetrics)
        screenWidth = displayMetrics.widthPixels
        screenHeight = displayMetrics.heightPixels
    }
    
    fun update(gazeDirection: FloatArray, dt: Float = 1f/60f) {
        this.gazeDirection = gazeDirection.copyOf()
        projectToScreen()
        if (currentTarget != null) {
            dwellTimer += dt
        } else {
            dwellTimer = 0f
        }
    }
    fun update(gazeDirection: FloatArray) = update(gazeDirection, 1f/60f)
    
    private fun projectToScreen() {
        // Convert gaze direction (normalized) to screen coordinates
        // Assuming gaze direction is in world space, forward is -Z
        val yaw = atan2(gazeDirection[0], -gazeDirection[2])
        val pitch = asin(-gazeDirection[1] / sqrt(
            gazeDirection[0] * gazeDirection[0] +
            gazeDirection[1] * gazeDirection[1] +
            gazeDirection[2] * gazeDirection[2]
        ))

        // Map to screen coordinates (normalized -1 to 1) - use Float PI for type safety
        val piF = PI.toFloat()
        val normalizedX = yaw / (piF / 2f) // Approximate
        val normalizedY = pitch / (piF / 4f)
        
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
    
    fun getReticlePosition(): PointF = reticlePosition
    
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