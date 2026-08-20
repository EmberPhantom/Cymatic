package com.cymatic.client.handtracking

import android.content.Context
import android.graphics.PointF
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.media.Image
import android.media.ImageReader
import android.os.Build
import android.util.Log
import android.util.Size
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarker
import com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarkerOptions
import com.google.mediapipe.tasks.vision.core.BaseOptions
import com.google.mediapipe.tasks.vision.core.RunningMode
import com.google.mediapipe.framework.image.MPImage
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import java.nio.ByteBuffer

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
    
    // MediaPipe model path
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
        checkUvcSupport()
        if (isUvcSupported) {
            initializeHandLandmarker()
        }
    }
    
    private fun checkUvcSupport() {
        val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
        val deviceList = usbManager.deviceList
        
        for (device in deviceList.values) {
            // Check if device is a UVC camera
            if (isUvcCamera(device)) {
                usbCamera = device
                isUvcSupported = true
                Log.d("HandTracking", "UVC Camera found: ${device.deviceName}")
                break
            }
        }
        
        if (!isUvcSupported) {
            Log.w("HandTracking", "No UVC camera found. Hand tracking disabled.")
        }
    }
    
    private fun isUvcCamera(device: UsbDevice): Boolean {
        // Check USB class for Video class (0x0E)
        return device.deviceClass == 0x0E || 
               device.deviceName.lowercase().contains("uvc") ||
               device.deviceName.lowercase().contains("camera")
    }
    
    private fun initializeHandLandmarker() {
        try {
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
                .setResultListener { result, image, timestampMs ->
                    onHandLandmarksDetected(result, timestampMs)
                }
                .build()
            
            handLandmarker = HandLandmarker.createFromOptions(context, options)
            Log.d("HandTracking", "MediaPipe Hand Landmarker initialized")
        } catch (e: Exception) {
            Log.e("HandTracking", "Failed to initialize hand landmarker", e)
        }
    }
    
    private fun onHandLandmarksDetected(
        result: com.google.mediapipe.tasks.vision.handlandmarker.HandLandmarkerResult,
        timestampMs: Long
    ) {
        val leftHand = result.handLandmarks.firstOrNull { it.handedness == "Left" }
        val rightHand = result.handLandmarks.firstOrNull { it.handedness == "Right" }
        
        // Convert landmarks to PointF list
        leftHandLandmarks = leftHand?.let { convertLandmarks(it) }
        rightHandLandmarks = rightHand?.let { convertLandmarks(it) }
        
        // Get confidence scores
        leftHandConfidence = leftHand?.let { calculateConfidence(it) } ?: 0f
        rightHandConfidence = rightHand?.let { calculateConfidence(it) } ?: 0f
        
        // Detect gestures
        leftHandGesture = leftHand?.let { detectGesture(it) } ?: HandGesture.NONE
        rightHandGesture = rightHand?.let { detectGesture(it) } ?: HandGesture.NONE
        
        // Send update
        val data = HandTrackingData(
            leftHand = leftHandLandmarks?.let { HandData(it, leftHandConfidence, leftHandGesture) },
            rightHand = rightHandLandmarks?.let { HandData(it, rightHandConfidence, rightHandGesture) },
            timestamp = timestampMs
        )
        
        handDataChannel.trySend(data)
        onHandDataUpdate?.invoke(data)
    }
    
    private fun convertLandmarks(landmarks: com.google.mediapipe.tasks.components.containers.NormalizedLandmarkList): List<PointF> {
        return landmarks.landmarks.map { PointF(it.x, it.y) }
    }
    
    private fun calculateConfidence(landmarks: com.google.mediapipe.tasks.components.containers.NormalizedLandmarkList): Float {
        return landmarks.landmarks.map { it.score ?: 0f }.average()
    }
    
    private fun detectGesture(landmarks: com.google.mediapipe.tasks.components.containers.NormalizedLandmarkList): HandGesture {
        val points = landmarks.landmarks
        
        // Thumb tip (4), Index tip (8), Middle tip (12), Ring tip (16), Pinky tip (20)
        val thumbTip = points[4]
        val indexTip = points[8]
        val middleTip = points[12]
        val ringTip = points[16]
        val pinkyTip = points[20]
        
        // Thumb IP (3), Index PIP (6), Middle PIP (10), Ring PIP (14), Pinky PIP (18)
        val thumbIp = points[3]
        val indexPip = points[6]
        val middlePip = points[10]
        val ringPip = points[14]
        val pinkyPip = points[18]
        
        // Calculate distances
        val thumbIndexDist = distance(thumbTip, indexTip)
        val thumbMiddleDist = distance(thumbTip, middleTip)
        
        // Finger extended checks (tip above PIP = extended)
        val thumbExtended = thumbTip.y < thumbIp.y
        val indexExtended = indexTip.y < indexPip.y
        val middleExtended = middleTip.y < middlePip.y
        val ringExtended = ringTip.y < ringPip.y
        val pinkyExtended = pinkyTip.y < pinkyPip.y
        
        val extendedCount = listOf(indexExtended, middleExtended, ringExtended, pinkyExtended).count { it }
        
        // Pinch: thumb and index tips close
        if (thumbIndexDist < 0.05f) {
            return HandGesture.PINCH
        }
        
        // Fist: all fingers curled
        if (extendedCount == 0 && !thumbExtended) {
            return HandGesture.FIST
        }
        
        // Open palm: all fingers extended
        if (extendedCount >= 4 && indexExtended && middleExtended) {
            return HandGesture.OPEN_PALM
        }
        
        // Point: only index extended
        if (indexExtended && !middleExtended && !ringExtended && !pinkyExtended) {
            return HandGesture.POINT
        }
        
        // Swipe detection would need temporal analysis
        // For now, return based on static pose
        
        return HandGesture.NONE
    }
    
    private fun distance(p1: com.google.mediapipe.tasks.components.containers.NormalizedLandmark, p2: com.google.mediapipe.tasks.components.containers.NormalizedLandmark): Float {
        val dx = p1.x - p2.x
        val dy = p1.y - p2.y
        val dz = p1.z - p2.z
        return Math.sqrt(dx * dx + dy * dy + dz * dz).toFloat()
    }
    
    fun startTracking() {
        if (!isUvcSupported || handLandmarker == null) {
            Log.w("HandTracking", "Cannot start: UVC not supported or landmarker not initialized")
            return
        }
        
        isTracking = true
        // Start camera preview and feed frames to handLandmarker
        // This would require CameraX integration with ImageReader
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
        handLandmarker?.close()
        imageReader?.close()
    }
}