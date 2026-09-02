package com.cymatic.client.ui.vr

import android.content.pm.ActivityInfo
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.opengl.GLSurfaceView
import android.os.Build
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.util.Log
import android.view.MotionEvent
import android.view.View
import android.widget.Button
import android.widget.FrameLayout
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
import com.cymatic.client.network.model.StreamSessionResponse
import com.cymatic.client.sensor.SensorFusion
import com.cymatic.client.input.ControllerManager
import com.cymatic.client.input.GazeManager
import com.cymatic.client.audio.AudioManager
import com.cymatic.client.util.PreferencesManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import org.webrtc.EglBase
import org.webrtc.RendererCommon
import org.webrtc.SurfaceViewRenderer
import org.webrtc.VideoFrame
import java.util.concurrent.Executors

@AndroidEntryPoint
class VRActivity : AppCompatActivity(), SensorEventListener {

    private lateinit var sensorManager: SensorManager
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
    
    // Sensor fusion
    private val handler = Handler(Looper.getMainLooper())
    private val sensorRunnable = Runnable { updateSensors() }
    private var lastSensorUpdate = 0L
    
    // PTT
    private var isRecording = false
    private var audioRecord: AudioRecord? = null
    private val audioExecutor = Executors.newSingleThreadExecutor()
    
    // Stats
    private var frameCount = 0
    private var lastFpsTime = 0L
    private var currentFps = 0
    
    // Thermal monitoring
    private lateinit var powerManager: PowerManager
    private var thermalMonitorRunnable: Runnable? = null
    private val thermalMonitorHandler = Handler(Looper.getMainLooper())
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
        surfaceViewRenderer?.setEnableHardwareScaler(true)
        surfaceViewRenderer?.setMirror(false)
    }
    
    private fun initManagers() {
        sensorManager = getSystemService(SENSOR_SERVICE) as SensorManager
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
                // Render remote video frame to SurfaceViewRenderer
                runOnUiThread {
                    surfaceViewRenderer?.onFrame(frame)
                }
            }
        )
        
        // Start thermal monitoring
        startThermalMonitoring()
    }
    
    private fun initWebRTC() {
        // EglBase already created in initManagers
    }
    
    private fun initSensors() {
        // Register sensor listeners
        val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
        val gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
        val magnetic = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)
        
        if (accelerometer != null) sensorManager.registerListener(this, accelerometer, SensorManager.SENSOR_DELAY_FASTEST)
        if (gyroscope != null) sensorManager.registerListener(this, gyroscope, SensorManager.SENSOR_DELAY_FASTEST)
        if (magnetic != null) sensorManager.registerListener(this, magnetic, SensorManager.SENSOR_DELAY_FASTEST)
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
        val baseUrl = preferencesManager.signalingUrl
        val token = preferencesManager.accessToken ?: ""
        val signalingUrl = "${baseUrl}/v1/stream/ws/${sessionId}?token=${token}&type=android"
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
        val now = System.currentTimeMillis()
        if (now - lastSensorUpdate >= 16) { // ~60Hz
            lastSensorUpdate = now
            
            // Get fused orientation
            val orientation = sensorFusion.getOrientation()
            val position = sensorFusion.getPosition()
            
            // Send head pose to render server
            webRTCManager.sendHeadPose(position, orientation)
            
            // Update gaze
            val gazeDirection = sensorFusion.getForwardVector()
            gazeManager.update(gazeDirection)
            
            // Update reticle position
            runOnUiThread {
                val reticlePos = gazeManager.getReticlePosition()
                gazeReticle.x = reticlePos.x
                gazeReticle.y = reticlePos.y
            }
        }
        
        handler.postDelayed(sensorRunnable, 16)
    }
    
    // Thermal monitoring
    private fun startThermalMonitoring() {
        thermalMonitorRunnable = Runnable { checkThermalState() }
        thermalMonitorHandler.postDelayed(thermalMonitorRunnable!!, 5000) // Check every 5 seconds
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
            
            // Update thermal UI
            runOnUiThread {
                thermalText.text = "Thermal: ${(thermalLevel * 100).toInt()}%"
                
                if (thermalLevel >= THERMAL_THRESHOLD_CRITICAL) {
                    thermalText.setTextColor(0xFFF44336.toInt()) // Red
                    showThermalWarning("Critical thermal state - performance may be reduced")
                } else if (thermalLevel >= THERMAL_THRESHOLD_WARNING) {
                    thermalText.setTextColor(0xFFF44336.toInt()) // Orange/Red
                } else {
                    thermalText.setTextColor(0xFF4CAF50.toInt()) // Green
                }
            }
            
            // Auto-reduce quality if thermal state is severe
            if (thermalLevel >= THERMAL_THRESHOLD_CRITICAL) {
                reduceStreamingQuality()
            }
        }
        
        // Schedule next check
        thermalMonitorHandler.postDelayed(thermalMonitorRunnable!!, 5000)
    }
    
    private fun reduceStreamingQuality() {
        // Signal to WebRTC manager to reduce bitrate/resolution
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
        
        audioRecord?.stop()
        audioRecord?.release()
        audioRecord = null
    }
    
    override fun onSensorChanged(event: SensorEvent) {
        sensorFusion.onSensorChanged(event)
    }
    
    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        sensorFusion.onAccuracyChanged(sensor!!, accuracy)
    }
    
    override fun onResume() {
        super.onResume()
        sensorFusion.onResume()
        handler.post(sensorRunnable)
        
        if (isStreaming) {
            webRTCManager.resume()
        }
    }
    
    override fun onPause() {
        super.onPause()
        sensorFusion.onPause()
        handler.removeCallbacks(sensorRunnable)
        
        if (isStreaming) {
            webRTCManager.pause()
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        handler.removeCallbacks(sensorRunnable)
        sensorManager.unregisterListener(this)
        
        if (isStreaming) {
            stopStreaming()
        }
        
        webRTCManager.dispose()
        audioManager.dispose()
        eglBase?.dispose()
        audioExecutor.shutdown()
    }
}