package com.cymatic.client.ui.vr

import android.content.pm.ActivityInfo
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.opengl.GLSurfaceView
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.util.Log
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.ImageView
import android.widget.ProgressBar
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.cymatic.client.R
import com.cymatic.client.webrtc.WebRTCManager
import com.cymatic.client.network.ApiClient
import com.cymatic.client.network.ApiService
import com.cymatic.client.network.model.StreamSessionRequest
import com.cymatic.client.sensor.SensorFusion
import com.cymatic.client.input.ControllerManager
import com.cymatic.client.input.GazeManager
import com.cymatic.client.audio.AudioManager
import com.cymatic.client.util.PreferencesManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch
import org.webrtc.EglBase
import org.webrtc.SurfaceViewRenderer
import java.net.URLEncoder
import java.util.concurrent.Executors

@AndroidEntryPoint
class VRActivity : AppCompatActivity() {

    private lateinit var sensorFusion: SensorFusion
    private lateinit var gazeManager: GazeManager
    private lateinit var controllerManager: ControllerManager
    private lateinit var audioManager: AudioManager
    private lateinit var webRTCManager: WebRTCManager
    private lateinit var apiService: ApiService
    private lateinit var preferencesManager: PreferencesManager
    
    private var eglBase: EglBase? = null
    private var surfaceViewRenderer: SurfaceViewRenderer? = null
    private var glSurfaceView: GLSurfaceView? = null
    
    private var currentSessionId: String? = null
    private var isStreaming = false
    private var isConnected = false
    
    // UI
    private lateinit var connectionStatus: TextView
    private lateinit var fpsText: TextView
    private lateinit var latencyText: TextView
    private lateinit var thermalText: TextView
    private lateinit var progressBar: ProgressBar
    private lateinit var btnEndSession: Button
    private lateinit var btnPTT: ImageView
    private lateinit var gazeReticle: ImageView
    
    // Sensor fusion — throttled to 20Hz (was 60Hz at 284)
    private val handler = Handler(Looper.getMainLooper())
    private val sensorRunnable = Runnable { updateSensors() }
    private var lastSensorUpdate = 0L
    private var lastPoseSendTime = 0L
    private var lastSentOrientation = FloatArray(4).apply { this[3] = 1f }
    
    // PTT
    private var isRecording = false
    private var audioRecord: AudioRecord? = null
    private val audioExecutor = Executors.newSingleThreadExecutor()
    
    // Thermal monitoring — single schedule guard (311)
    private lateinit var powerManager: PowerManager
    private var thermalMonitorRunnable: Runnable? = null
    private val thermalMonitorHandler = Handler(Looper.getMainLooper())
    private var isThermalMonitoring = false
    private val THERMAL_THRESHOLD_WARNING = 0.8f
    private val THERMAL_THRESHOLD_CRITICAL = 0.95f
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setRequestedOrientation(ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE)
        setContentView(R.layout.activity_vr)
        
        // Keep screen on
        window.addFlags(android.view.WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        
        initViews()
        initManagers()
        initWebRTC()
        initSensors()
        
        // Start session
        startStreamingSession()
    }
    
    private fun initViews() {
        connectionStatus = findViewById(R.id.tv_connection_status)
        fpsText = findViewById(R.id.tv_fps)
        latencyText = findViewById(R.id.tv_latency)
        thermalText = findViewById(R.id.tv_thermal)
        progressBar = findViewById(R.id.pb_loading)
        btnEndSession = findViewById(R.id.btn_end_session)
        btnPTT = findViewById(R.id.iv_ptt)
        gazeReticle = findViewById(R.id.iv_gaze_reticle)
        
        btnEndSession.setOnClickListener { stopStreaming() }
        btnPTT.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> startVoiceRecording()
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> stopVoiceRecording()
            }
            true
        }
        
        // Setup SurfaceViewRenderer for WebRTC video rendering
        surfaceViewRenderer = findViewById(R.id.surface_view_renderer)
        surfaceViewRenderer?.setZOrderMediaOverlay(true)
        // 142: Disable hardware scaler on low-end — saves 3840 decode + extra blit; use software scale or fixed 1080p
        surfaceViewRenderer?.setEnableHardwareScaler(false)
        surfaceViewRenderer?.setMirror(false)
    }
    
    private fun initManagers() {
        sensorFusion = SensorFusion(this)
        gazeManager = GazeManager(this)
        controllerManager = ControllerManager(this)
        audioManager = AudioManager(this)
        
        // Thermal monitoring
        powerManager = getSystemService(POWER_SERVICE) as PowerManager
        
        // Create EglBase first for WebRTC
        eglBase = EglBase.create()
        
        // Initialize WebRTC with EglBase
        webRTCManager = WebRTCManager(this, eglBase!!)
        
        apiService = ApiClient.apiService
        preferencesManager = PreferencesManager(this)
        
        // Setup WebRTC callbacks
        webRTCManager.setCallbacks(
            onConnected = { sessionId ->
                runOnUiThread {
                    isConnected = true
                    currentSessionId = sessionId
                    updateConnectionStatus("Connected", true)
                    progressBar.visibility = View.GONE
                }
            },
            onDisconnected = { reason ->
                runOnUiThread {
                    isConnected = false
                    isStreaming = false
                    updateConnectionStatus("Disconnected: $reason", false)
                }
            },
            onError = { error ->
                runOnUiThread {
                    Toast.makeText(this@VRActivity, "Error: $error", Toast.LENGTH_LONG).show()
                }
            },
            onStats = { stats ->
                runOnUiThread {
                    updateStats(stats)
                }
            },
            onRemoteVideoFrame = { frame ->
                // Render remote video frame — already on correct thread via webrtc; post to UI only if needed
                surfaceViewRenderer?.onFrame(frame)
            }
        )
        
        // Start thermal monitoring
        startThermalMonitoring()
    }
    
    private fun initWebRTC() {
        // EglBase already created in initManagers
    }
    
    private fun initSensors() {
        // 206: Removed double registration — SensorFusion is single source at GAME/NORMAL rates.
        // Previously this registered accel/gyro/mag again at GAME doubling to ~100Hz per sensor.
        // SensorFusion.start() handles registration; VRActivity just drives pose polling at 20Hz.
    }
    
    private fun startStreamingSession() {
        lifecycleScope.launch {
            try {
                val projectId = preferencesManager.selectedProjectId ?: 1
                val deviceInfo = mapOf(
                    "model" to android.os.Build.MODEL,
                    "manufacturer" to android.os.Build.MANUFACTURER,
                    "android_version" to android.os.Build.VERSION.RELEASE,
                    "screen_width" to resources.displayMetrics.widthPixels,
                    "screen_height" to resources.displayMetrics.heightPixels,
                    "density" to resources.displayMetrics.density
                )
                val request = StreamSessionRequest(projectId = projectId, deviceInfo = deviceInfo)
                
                val response = apiService.createStreamSession(request)
                
                if (response.isSuccessful) {
                    val session = response.body()!!
                    currentSessionId = session.id
                    connectToRenderServer(session.id)
                } else {
                    runOnUiThread {
                        Toast.makeText(this@VRActivity, "Failed to create session: ${response.message()}", Toast.LENGTH_LONG).show()
                        finish()
                    }
                }
            } catch (e: Exception) {
                Log.e("VRActivity", "Failed to start session", e)
                runOnUiThread {
                    Toast.makeText(this@VRActivity, "Error: ${e.message}", Toast.LENGTH_LONG).show()
                    finish()
                }
            }
        }
    }
    
    private fun connectToRenderServer(sessionId: String) {
        // 253: Sanitize signalingUrl — handle http->ws, trim slashes, encode params to avoid malformed URL
        val raw = preferencesManager.signalingUrl.trim().trimEnd('/')
        val baseUrl = when {
            raw.startsWith("wss://") || raw.startsWith("ws://") -> raw
            raw.startsWith("https://") -> raw.replaceFirst("https://", "wss://")
            raw.startsWith("http://") -> raw.replaceFirst("http://", "ws://")
            raw.isEmpty() -> "ws://10.0.2.2:8000"
            else -> "ws://$raw"
        }
        val token = preferencesManager.accessToken ?: ""
        val encodedToken = try { URLEncoder.encode(token, "UTF-8") } catch (_: Exception) { token }
        val encodedSession = try { URLEncoder.encode(sessionId, "UTF-8") } catch (_: Exception) { sessionId }
        // Ensure no double slash: baseUrl already trimmed
        val signalingUrl = "${baseUrl}/v1/stream/ws/${encodedSession}?token=${encodedToken}&type=android"
        webRTCManager.connect(signalingUrl, sessionId)
    }
    
    private fun stopStreaming() {
        isStreaming = false
        webRTCManager.disconnect()
        audioManager.stop()
        finish()
    }
    
    private fun updateConnectionStatus(status: String, connected: Boolean) {
        connectionStatus.text = status
        connectionStatus.setTextColor(if (connected) 0xFF4CAF50.toInt() else 0xFFF44336.toInt())
    }
    
    private fun updateStats(stats: WebRTCManager.StreamStats) {
        fpsText.text = "FPS: ${stats.fps}"
        latencyText.text = "Latency: ${stats.latencyMs}ms"
        thermalText.text = "Thermal: ${(stats.thermalLevel * 100).toInt()}%"
        
        if (stats.thermalLevel > 0.8f) {
            thermalText.setTextColor(0xFFF44336.toInt())
        } else {
            thermalText.setTextColor(0xFF4CAF50.toInt())
        }
    }
    
    private fun updateSensors() {
        // 284: Throttled to 20Hz (50ms) vs 60Hz (16ms) — saves 60 head-pose sends/s.
        // Also delta-suppress: only send if orientation changed > ~0.5deg to reduce websocket churn.
        val now = SystemClock.elapsedRealtime()
        if (now - lastSensorUpdate < 50) {
            handler.postDelayed(sensorRunnable, 50 - (now - lastSensorUpdate))
            return
        }
        lastSensorUpdate = now
        
        val orientation = sensorFusion.getOrientation()
        val position = sensorFusion.getPosition()
        
        // Delta check via quaternion dot (avoid spamming identical poses)
        if (shouldSendPose(orientation, now)) {
            webRTCManager.sendHeadPose(position, orientation)
            lastSentOrientation = orientation.copyOf()
            lastPoseSendTime = now
        }
        
        // Update gaze at same throttled rate — dt = 0.05 for dwell calc
        val gazeDirection = sensorFusion.getForwardVector()
        gazeManager.update(gazeDirection, 0.05f)
        
        // Update reticle position on UI thread coalesced
        val reticlePos = gazeManager.getReticlePosition()
        gazeReticle.x = reticlePos.x
        gazeReticle.y = reticlePos.y
        gazeReticle.visibility = View.VISIBLE

        // Controller must work without hand tracking (docs/05) - send its state at
        // the same throttled 20Hz cadence as head pose, only while a controller is
        // actually connected.
        if (controllerManager.isConnected()) {
            webRTCManager.sendControllerState(controllerManager.getState())
        }

        handler.postDelayed(sensorRunnable, 50)
    }

    /** Forward hardware key events (Bluetooth VR controller buttons) to ControllerManager. */
    override fun dispatchKeyEvent(event: android.view.KeyEvent): Boolean {
        if (!::controllerManager.isInitialized) return super.dispatchKeyEvent(event)
        val handled = when (event.action) {
            android.view.KeyEvent.ACTION_DOWN -> controllerManager.onKeyDown(event.keyCode, event)
            android.view.KeyEvent.ACTION_UP -> controllerManager.onKeyUp(event.keyCode, event)
            else -> false
        }
        return handled || super.dispatchKeyEvent(event)
    }

    /** Forward analog controller axes (touchpad/trigger/thumbstick) to ControllerManager. */
    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        if (::controllerManager.isInitialized && controllerManager.onGenericMotionEvent(event)) {
            return true
        }
        return super.onGenericMotionEvent(event)
    }

    private fun shouldSendPose(orientation: FloatArray, now: Long): Boolean {
        if (now - lastPoseSendTime > 200) return true // keepalive every 200ms even if static
        // quaternion dot product close to 1 => almost identical
        val dot = (orientation[0]*lastSentOrientation[0] + orientation[1]*lastSentOrientation[1] +
                orientation[2]*lastSentOrientation[2] + orientation[3]*lastSentOrientation[3]).let { kotlin.math.abs(it) }
        // dot > 0.99996 ~ <0.5deg change => suppress
        return dot < 0.99996f
    }
    
    // Thermal monitoring — guarded single schedule (311)
    private fun startThermalMonitoring() {
        if (isThermalMonitoring) return
        isThermalMonitoring = true
        if (thermalMonitorRunnable == null) {
            thermalMonitorRunnable = Runnable { checkThermalState() }
        }
        thermalMonitorHandler.removeCallbacks(thermalMonitorRunnable!!)
        thermalMonitorHandler.postDelayed(thermalMonitorRunnable!!, 5000)
    }

    private fun stopThermalMonitoring() {
        isThermalMonitoring = false
        thermalMonitorRunnable?.let { thermalMonitorHandler.removeCallbacks(it) }
    }
    
    private fun checkThermalState() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            val thermalStatus = powerManager.currentThermalStatus
            val thermalLevel = when (thermalStatus) {
                PowerManager.THERMAL_STATUS_NONE -> 0.0f
                PowerManager.THERMAL_STATUS_LIGHT -> 0.25f
                PowerManager.THERMAL_STATUS_MODERATE -> 0.5f
                PowerManager.THERMAL_STATUS_SEVERE -> 0.75f
                PowerManager.THERMAL_STATUS_CRITICAL -> 1.0f
                PowerManager.THERMAL_STATUS_EMERGENCY -> 1.0f
                PowerManager.THERMAL_STATUS_SHUTDOWN -> 1.0f
                else -> 0.0f
            }
            
            runOnUiThread {
                thermalText.text = "Thermal: ${(thermalLevel * 100).toInt()}%"
                
                if (thermalLevel >= THERMAL_THRESHOLD_CRITICAL) {
                    thermalText.setTextColor(0xFFF44336.toInt())
                    showThermalWarning("Critical thermal state - performance may be reduced")
                } else if (thermalLevel >= THERMAL_THRESHOLD_WARNING) {
                    thermalText.setTextColor(0xFFF44336.toInt())
                } else {
                    thermalText.setTextColor(0xFF4CAF50.toInt())
                }
            }
            
            if (thermalLevel >= THERMAL_THRESHOLD_CRITICAL) {
                reduceStreamingQuality()
            }
        }
        
        // 311: Only reschedule if still monitoring — avoids double schedule on recreate
        if (isThermalMonitoring) {
            thermalMonitorHandler.postDelayed(thermalMonitorRunnable!!, 5000)
        }
    }
    
    private fun showThermalWarning(message: String) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show()
        Log.w("VRActivity", message)
    }

    private fun reduceStreamingQuality() {
        webRTCManager.reduceQuality()
    }
    
    private fun startVoiceRecording() {
        if (isRecording) return
        
        isRecording = true
        btnPTT.setImageResource(R.drawable.ic_mic_active)
        
        val bufferSize = AudioRecord.getMinBufferSize(
            16000,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            16000,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT,
            bufferSize * 2
        )
        
        audioRecord?.startRecording()
        
        audioExecutor.execute {
            val buffer = ByteArray(bufferSize)
            while (isRecording) {
                val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                if (read > 0) {
                    webRTCManager.sendAudioData(buffer.copyOfRange(0, read))
                }
            }
        }
    }
    
    private fun stopVoiceRecording() {
        if (!isRecording) return
        
        isRecording = false
        btnPTT.setImageResource(R.drawable.ic_mic)
        
        try { audioRecord?.stop() } catch (_: Exception) {}
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null
    }
    
    override fun onResume() {
        super.onResume()
        sensorFusion.onResume()
        handler.removeCallbacks(sensorRunnable)
        handler.post(sensorRunnable)
        startThermalMonitoring()
        
        if (isStreaming) {
            webRTCManager.resume()
        }
    }
    
    override fun onPause() {
        super.onPause()
        sensorFusion.onPause()
        handler.removeCallbacks(sensorRunnable)
        stopThermalMonitoring()
        
        if (isStreaming) {
            webRTCManager.pause()
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(sensorRunnable)
        stopThermalMonitoring()
        
        if (isStreaming) {
            stopStreaming()
        }
        
        webRTCManager.dispose()
        audioManager.dispose()
        try { eglBase?.release() } catch (_: Exception) {}
        audioExecutor.shutdownNow()
    }
}
