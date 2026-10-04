package com.cymatic.client.handtracking

import android.content.Context
import android.graphics.PointF
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.media.ImageReader
import android.util.Log
import com.cymatic.client.util.PreferencesManager
import com.google.mediapipe.tasks.components.containers.Category
import com.google.mediapipe.tasks.components.containers.NormalizedLandmark
import com.google.mediapipe.tasks.vision.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarkerOptions
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarkerResult
import kotlinx.coroutines.channels.Channel

class HandTrackingManager(private val context: Context) {

    private var handLandmarker: HandLandmarker? = null
    private var imageReader: ImageReader? = null
    private var usbCamera: UsbDevice? = null
    private var isTracking = false
    private var isUvcSupported = false

    // Hand data
    private var leftHandLandmarks: List<PointF>? = null
    private var rightHandLandmarks: List<PointF>? = null
    private var leftHandConfidence = 0f
    private var rightHandConfidence = 0f
    private var leftHandGesture = HandGesture.NONE
    private var rightHandGesture = HandGesture.NONE

    // Callbacks
    private val handDataChannel = Channel<HandTrackingData>(10)
    private var onHandDataUpdate: ((HandTrackingData) -> Unit)? = null

    // MediaPipe model path - optional asset, guard missing
    private val modelPath = "hand_landmarker.task"

    enum class HandGesture {
        NONE, PINCH, OPEN_PALM, FIST, POINT, SWIPE_LEFT, SWIPE_RIGHT, SWIPE_UP, SWIPE_DOWN
    }

    data class HandTrackingData(
        val leftHand: HandData?,
        val rightHand: HandData?,
        val timestamp: Long
    )

    data class HandData(
        val landmarks: List<PointF>,  // 21 landmarks
        val confidence: Float,
        val gesture: HandGesture,
        val worldPosition: PointF? = null
    )

    init {
        // Hand tracking is OPTIONAL (AGENTS.md): the MediaPipe tasks-vision
        // dependency stays, but nothing initializes unless the user enabled
        // the feature flag AND a UVC camera is present.
        if (!isFlagEnabled()) {
            Log.d("HandTracking", "disabled by feature flag (optional)")
        } else {
            checkUvcSupport()
            // Hand tracking is optional - only init if UVC available and model present
            if (isUvcSupported) {
                initializeHandLandmarker()
            }
        }
    }

    /** Feature-flag gate (PreferencesManager.userPreferences.handTrackingEnabled). */
    private fun isFlagEnabled(): Boolean {
        return try {
            PreferencesManager(context).isHandTrackingEnabled
        } catch (e: Exception) {
            Log.w("HandTracking", "prefs unavailable, treating as disabled")
            false
        }
    }

    private fun checkUvcSupport() {
        try {
            val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
            val deviceList = usbManager.deviceList
            for (device in deviceList.values) {
                if (isUvcCamera(device)) {
                    usbCamera = device
                    isUvcSupported = true
                    Log.d("HandTracking", "UVC Camera found: ${device.deviceName}")
                    break
                }
            }
        } catch (e: SecurityException) {
            Log.w("HandTracking", "USB permission not granted, UVC check skipped")
        } catch (e: Exception) {
            Log.w("HandTracking", "UVC check failed", e)
        }
        if (!isUvcSupported) {
            Log.w("HandTracking", "No UVC camera found. Hand tracking disabled (optional).")
        }
    }

    private fun isUvcCamera(device: UsbDevice): Boolean {
        return device.deviceClass == 0x0E ||
                device.deviceName.lowercase().contains("uvc") ||
                device.deviceName.lowercase().contains("camera")
    }

    private fun initializeHandLandmarker() {
        // Guard: model asset may be missing in debug builds - fail gracefully
        try {
            // Check asset exists before creating landmarker
            try {
                context.assets.open(modelPath).close()
            } catch (e: Exception) {
                Log.w("HandTracking", "Model asset missing: $modelPath, hand tracking disabled (optional)")
                return
            }
            val options = HandLandmarkerOptions.builder()
                .setBaseOptions(
                    BaseOptions.builder()
                        .setModelAssetPath(modelPath)
                        .build()
                )
                .setRunningMode(RunningMode.LIVE_STREAM)
                .setNumHands(2)
                .setMinHandDetectionConfidence(0.5f)
                .setMinHandPresenceConfidence(0.5f)
                .setMinTrackingConfidence(0.5f)
                .setResultListener { result, _, timestampMs ->
                    onHandLandmarksDetected(result, timestampMs)
                }
                .build()
            handLandmarker = HandLandmarker.createFromOptions(context, options)
            Log.d("HandTracking", "MediaPipe Hand Landmarker initialized")
        } catch (e: Exception) {
            Log.e("HandTracking", "Failed to initialize hand landmarker (optional)", e)
            handLandmarker = null
        }
    }

    private fun onHandLandmarksDetected(
        result: HandLandmarkerResult,
        timestampMs: Long
    ) {
        try {
            // Correct API: result.landmarks() and result.handedness() (or deprecated handednesses())
            val allLandmarks: List<List<NormalizedLandmark>> = try {
                result.landmarks()
            } catch (_: Exception) {
                emptyList()
            }
            val allHandedness: List<List<Category>> = try {
                result.handedness()
            } catch (_: Exception) {
                @Suppress("DEPRECATION")
                try { result.handednesses() } catch (_: Exception) { emptyList() }
            }

            var leftLandmarks: List<NormalizedLandmark>? = null
            var rightLandmarks: List<NormalizedLandmark>? = null

            for (i in allLandmarks.indices) {
                val categories = allHandedness.getOrNull(i) ?: continue
                val top = categories.firstOrNull() ?: continue
                val label = try { top.categoryName() } catch (_: Exception) { "" }
                val lm = allLandmarks[i]
                when {
                    label.equals("Left", ignoreCase = true) -> leftLandmarks = lm
                    label.equals("Right", ignoreCase = true) -> rightLandmarks = lm
                }
            }

            leftHandLandmarks = leftLandmarks?.let { convertLandmarks(it) }
            rightHandLandmarks = rightLandmarks?.let { convertLandmarks(it) }

            leftHandConfidence = leftLandmarks?.let { calculateConfidence(it) } ?: 0f
            rightHandConfidence = rightLandmarks?.let { calculateConfidence(it) } ?: 0f

            leftHandGesture = leftLandmarks?.let { detectGesture(it) } ?: HandGesture.NONE
            rightHandGesture = rightLandmarks?.let { detectGesture(it) } ?: HandGesture.NONE

            val data = HandTrackingData(
                leftHand = leftHandLandmarks?.let { HandData(it, leftHandConfidence, leftHandGesture) },
                rightHand = rightHandLandmarks?.let { HandData(it, rightHandConfidence, rightHandGesture) },
                timestamp = timestampMs
            )
            handDataChannel.trySend(data)
            onHandDataUpdate?.invoke(data)
        } catch (e: Exception) {
            Log.e("HandTracking", "Failed to parse hand landmarks", e)
        }
    }

    private fun convertLandmarks(landmarks: List<NormalizedLandmark>): List<PointF> {
        return landmarks.map { PointF(it.x(), it.y()) }
    }

    // Legacy overload for NormalizedLandmarkList (kept for compatibility, not used after fix)
    @Suppress("unused")
    private fun convertLandmarksLegacy(landmarks: com.google.mediapipe.tasks.components.containers.NormalizedLandmarkList): List<PointF> {
        return landmarks.landmarks.map { PointF(it.x(), it.y()) }
    }

    private fun calculateConfidence(landmarks: List<NormalizedLandmark>): Float {
        // NormalizedLandmark has no score; use visibility/presence if available, else average 1f
        if (landmarks.isEmpty()) return 0f
        // Use presence as proxy if present, else return 1f scaled
        var sum = 0f
        var count = 0
        for (lm in landmarks) {
            val vis = try { lm.visibility().orElse(1.0f) } catch (_: Exception) { 1.0f }
            sum += vis
            count++
        }
        return if (count > 0) (sum / count).coerceIn(0f, 1f) else 0f
    }

    private fun detectGesture(landmarks: List<NormalizedLandmark>): HandGesture {
        if (landmarks.size < 21) return HandGesture.NONE
        val thumbTip = landmarks[4]
        val indexTip = landmarks[8]
        val middleTip = landmarks[12]
        val ringTip = landmarks[16]
        val pinkyTip = landmarks[20]

        val thumbIp = landmarks[3]
        val indexPip = landmarks[6]
        val middlePip = landmarks[10]
        val ringPip = landmarks[14]
        val pinkyPip = landmarks[18]

        val thumbIndexDist = distance(thumbTip, indexTip)

        val thumbExtended = thumbTip.y() < thumbIp.y()
        val indexExtended = indexTip.y() < indexPip.y()
        val middleExtended = middleTip.y() < middlePip.y()
        val ringExtended = ringTip.y() < ringPip.y()
        val pinkyExtended = pinkyTip.y() < pinkyPip.y()

        val extendedCount = listOf(indexExtended, middleExtended, ringExtended, pinkyExtended).count { it }

        if (thumbIndexDist < 0.05f) return HandGesture.PINCH
        if (extendedCount == 0 && !thumbExtended) return HandGesture.FIST
        if (extendedCount >= 4 && indexExtended && middleExtended) return HandGesture.OPEN_PALM
        if (indexExtended && !middleExtended && !ringExtended && !pinkyExtended) return HandGesture.POINT
        return HandGesture.NONE
    }

    private fun distance(p1: NormalizedLandmark, p2: NormalizedLandmark): Float {
        val dx = p1.x() - p2.x()
        val dy = p1.y() - p2.y()
        val dz = p1.z() - p2.z()
        return kotlin.math.sqrt(dx * dx + dy * dy + dz * dz)
    }

    fun startTracking() {
        if (!isFlagEnabled()) {
            Log.d("HandTracking", "start refused: disabled by feature flag (optional)")
            return
        }
        if (!isUvcSupported || handLandmarker == null) {
            Log.w("HandTracking", "Cannot start: UVC not supported or landmarker not initialized (optional)")
            return
        }
        isTracking = true
        Log.d("HandTracking", "Hand tracking started")
    }

    fun stopTracking() {
        isTracking = false
        Log.d("HandTracking", "Hand tracking stopped")
    }

    fun setOnHandDataUpdate(listener: (HandTrackingData) -> Unit) {
        onHandDataUpdate = listener
    }

    fun getLeftHandData(): HandData? = leftHandLandmarks?.let { HandData(it, leftHandConfidence, leftHandGesture) }
    fun getRightHandData(): HandData? = rightHandLandmarks?.let { HandData(it, rightHandConfidence, rightHandGesture) }

    fun isTracking(): Boolean = isTracking
    fun isUvcAvailable(): Boolean = isUvcSupported

    fun dispose() {
        stopTracking()
        try { handLandmarker?.close() } catch (_: Exception) {}
        try { imageReader?.close() } catch (_: Exception) {}
        try { handDataChannel.close() } catch (_: Exception) {}
    }
}
