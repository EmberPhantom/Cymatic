package com.cymatic.client.ui.render

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.PowerManager
import android.os.SystemClock
import android.view.KeyEvent
import android.view.MotionEvent
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.cymatic.client.R
import com.cymatic.client.databinding.ActivityRenderBinding
import com.cymatic.client.input.ControllerManager
import com.cymatic.client.render.EntityMapper
import com.cymatic.client.render.GazeSelector
import com.cymatic.client.render.LightingPresets
import com.cymatic.client.render.RenderCommand
import com.cymatic.client.render.RenderQuality
import com.cymatic.client.render.RenderSessionManager
import com.cymatic.client.render.RenderVoiceHelper
import com.cymatic.client.render.ThermalPolicy
import com.cymatic.client.render.TourGuide
import com.cymatic.client.sensor.SensorFusion
import com.cymatic.client.util.PreferencesManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.launch

/**
 * Native on-device 3D walkthrough (Unity-free path).
 *
 * Flow: render session create -> scene JSON fetch -> Filament scene build
 * (EntityMapper commands) -> stereo SBS viewports -> heartbeat loop.
 * Head pose from SensorFusion drives both eye cameras; gaze dwell (2 s)
 * selects POI markers / nav beacons; controller select does the same at the
 * reticle; hold-to-talk drives copilot voice via the render voice endpoint.
 */
@AndroidEntryPoint
class RenderActivity : AppCompatActivity() {

    private var _binding: ActivityRenderBinding? = null
    private val binding get() = _binding!!

    private lateinit var prefs: PreferencesManager
    private var sessionManager: RenderSessionManager? = null
    private var sensorFusion: SensorFusion? = null
    private var controllerManager: ControllerManager? = null
    private var voiceHelper: RenderVoiceHelper? = null
    private var sceneBuilder: FilamentSceneBuilder? = null

    private var heartbeatJob: Job? = null
    private val sensorHandler = Handler(Looper.getMainLooper())
    private var sensorLoop: Runnable? = null
    private var lastSensorMs = 0L

    private var gazeTargets: List<GazeSelector.Target> = emptyList()
    private var gazeState = GazeSelector.State()
    private var tourLegs: List<TourGuide.TourLeg> = emptyList()
    private var tourStartMs = 0L
    private var eyePos = floatArrayOf(0f, 1.6f, 0f)
    private var lastHeadQuat = floatArrayOf(0f, 0f, 0f, 1f)
    private var lastSelectPressed = false
    private var lastGazeMs = 0L

    // Thermal step-down (mirrors VRActivity): PowerManager status -> quality.
    private var powerManager: PowerManager? = null
    private val thermalHandler = Handler(Looper.getMainLooper())
    private var thermalRunnable: Runnable? = null
    private var thermalMonitoring = false

    // Session end must outlive onDestroy: lifecycleScope is cancelled in
    // onDestroy, so ending the session there would never run.
    private val endScope = CoroutineScope(SupervisorJob() + Dispatchers.IO)

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        _binding = ActivityRenderBinding.inflate(layoutInflater)
        setContentView(binding.root)

        val projectId = intent.getIntExtra(EXTRA_PROJECT_ID, -1)
        if (projectId <= 0) {
            toast(getString(R.string.no_project_selected))
            finish()
            return
        }

        prefs = PreferencesManager(this)
        sessionManager = RenderSessionManager(this)
        sensorFusion = SensorFusion(this)
        controllerManager = ControllerManager(this)
        voiceHelper = RenderVoiceHelper(this)

        binding.btnRenderBack.setOnClickListener { finish() }
        binding.statusText.text = "Connecting…"
        binding.progressBar.visibility = View.VISIBLE

        binding.btnPtt.setOnTouchListener { _, event ->
            when (event.action) {
                MotionEvent.ACTION_DOWN -> voiceHelper?.startTalk()
                MotionEvent.ACTION_UP, MotionEvent.ACTION_CANCEL -> onPttReleased()
            }
            true
        }

        lifecycleScope.launch {
            val result = sessionManager!!.start(projectId)
            binding.progressBar.visibility = View.GONE
            if (result.isFailure) {
                binding.statusText.text = "Failed: ${result.exceptionOrNull()?.message}"
                toast(getString(R.string.render_session_failed))
                return@launch
            }
            onSceneReady()
        }
    }

    private fun onSceneReady() {
        val scene = sessionManager!!.scene!!.scenePackage
        val manifestUris = EntityMapper.manifestUris(scene.assetManifest)
        val commands = EntityMapper.mapAll(scene.entities, manifestUris, scene.performanceBudget)
        val preset = LightingPresets.resolve(
            scene.lighting.preset, scene.lighting.timeOfDay, scene.lighting.ambientIntensity,
            scene.lighting.sunDirection
        )
        tourLegs = TourGuide.planTour(scene.navigation.points, scene.navigation.paths)
        gazeTargets = GazeSelector.targetsFrom(commands)
        tourStartMs = System.currentTimeMillis()

        // Start position: first tour waypoint, else default eye height.
        tourLegs.firstOrNull()?.waypoints?.firstOrNull()?.let {
            eyePos = it.position.copyOf()
        }

        binding.statusText.text =
            "${sessionManager!!.scene!!.project.name}: ${commands.size} objects, " +
                "${tourLegs.size} tour legs"
        binding.tourInfo.text =
            "Tour ${TourGuide.totalDuration(tourLegs).toInt()}s · budget ${scene.performanceBudget.maxTriangles} tris"

        if (!initFilamentSurface(commands, preset)) {
            binding.statusText.text = "${binding.statusText.text}\n(Preview mode: Filament unavailable)"
        }
        sensorFusion?.start()
        powerManager = getSystemService(POWER_SERVICE) as? PowerManager
        startSensorLoop()
        startHeartbeatLoop()
        startThermalMonitoring()
    }

    /**
     * Builds the Filament engine, scene and stereo camera rig. Returns false
     * when the ubershader is missing so the activity degrades to a data
     * preview instead of crashing.
     */
    private fun initFilamentSurface(
        commands: List<RenderCommand>,
        preset: LightingPresets.Preset
    ): Boolean {
        return try {
            Class.forName("com.google.android.filament.Engine")
            val resId = resources.getIdentifier("ubershader", "raw", packageName)
            if (resId == 0) return false
            val bytes = resources.openRawResource(resId).readBytes()
            sceneBuilder = FilamentSceneBuilder.build(binding.filamentView, commands, preset, bytes)
            sceneBuilder?.setResolutionScale(RenderQuality.resolutionScale(prefs.renderQuality))
            sceneBuilder?.setEyePosition(eyePos[0], eyePos[1], eyePos[2])
            sceneBuilder?.startLoop()
            true
        } catch (e: Exception) {
            false
        }
    }

    /** 20 Hz sensor/gaze/controller loop (same cadence as VRActivity). */
    private fun startSensorLoop() {
        val loop = object : Runnable {
            override fun run() {
                val now = System.currentTimeMillis()
                if (now - lastSensorMs >= 50) {
                    lastSensorMs = now
                    updateSensors(now)
                }
                sensorLoop?.let { sensorHandler.postDelayed(it, 16) }
            }
        }
        sensorLoop = loop
        sensorHandler.post(loop)
    }

    private fun updateSensors(nowMs: Long) {
        val fusion = sensorFusion ?: return
        val quat = fusion.getOrientation()
        lastHeadQuat = quat.copyOf()
        val ipdM = (prefs.ipd.coerceIn(50, 80)) / 1000f
        sceneBuilder?.setHeadQuaternion(quat, ipdM)

        // Tour advance.
        if (tourLegs.isNotEmpty()) {
            val elapsed = (nowMs - tourStartMs) / 1000.0
            TourGuide.sampleTour(tourLegs, elapsed)?.let {
                eyePos = it.position
                sceneBuilder?.setEyePosition(eyePos[0], eyePos[1], eyePos[2])
            }
        }

        // Gaze dwell over POIs / nav beacons (measured dt, not a constant).
        if (gazeTargets.isNotEmpty()) {
            val fwdNow = SystemClock.elapsedRealtime()
            val dtSec = if (lastGazeMs == 0L) 0.05
            else ((fwdNow - lastGazeMs) / 1000.0).coerceIn(0.005, 0.5)
            lastGazeMs = fwdNow
            val forward = GazeSelector.forwardFromQuaternion(quat)
            val update = GazeSelector.update(gazeState, gazeTargets, eyePos, forward, dtSec)
            gazeState = update.state
            update.confirmed?.let { onGazeConfirmed(it) }
        }

        // Controller select (rising edge) acts like a gaze confirm at the reticle.
        controllerManager?.let {
            val pressed = it.isConnected() && it.isSelectPressed()
            if (pressed && !lastSelectPressed) {
                onControllerSelect()
            }
            lastSelectPressed = pressed
        }
    }

    private fun onGazeConfirmed(target: GazeSelector.Target) {
        if (target.kind == "nav") {
            eyePos = target.position.copyOf().also { it[1] = 1.6f }
            sceneBuilder?.setEyePosition(eyePos[0], eyePos[1], eyePos[2])
            toast("Moved to ${target.label}")
        } else {
            toast(target.label)
        }
    }

    private fun onControllerSelect() {
        // Reticle-centered press: confirms ONLY a target with a separated
        // prior dwell (confirmOnPress), never auto-confirms in one update.
        val forward = GazeSelector.forwardFromQuaternion(lastHeadQuat)
        GazeSelector.confirmOnPress(gazeState, gazeTargets, eyePos, forward)
            ?.let { onGazeConfirmed(it) }
    }

    private fun onPttReleased() {
        val sid = sessionManager?.session?.id ?: return
        lifecycleScope.launch {
            binding.statusText.text = getString(R.string.listening)
            val reply = voiceHelper?.stopTalk(sid, prefs.voiceLanguage)
            binding.statusText.text = reply?.let { "You: ${it.transcript}\nCopilot: ${it.response}" }
                ?: getString(R.string.didnt_catch_that)
        }
    }

    /** Forward hardware key events (Bluetooth VR controller buttons). */
    override fun dispatchKeyEvent(event: KeyEvent): Boolean {
        val cm = controllerManager ?: return super.dispatchKeyEvent(event)
        val handled = when (event.action) {
            KeyEvent.ACTION_DOWN -> cm.onKeyDown(event.keyCode, event)
            KeyEvent.ACTION_UP -> cm.onKeyUp(event.keyCode, event)
            else -> false
        }
        return handled || super.dispatchKeyEvent(event)
    }

    /** Forward analog controller axes (touchpad/trigger/thumbstick). */
    override fun onGenericMotionEvent(event: MotionEvent): Boolean {
        val cm = controllerManager ?: return super.onGenericMotionEvent(event)
        return cm.onGenericMotionEvent(event) || super.onGenericMotionEvent(event)
    }

    private fun startHeartbeatLoop() {
        heartbeatJob?.cancel()
        val manager = sessionManager ?: return
        // Repeating heartbeat while the session is alive; recovery state is
        // surfaced in the status line (OK clears it, RETRYING warns, LOST sticks).
        heartbeatJob = manager.startHeartbeatLoop(lifecycleScope, 60_000) { health ->
            runOnUiThread {
                when (health) {
                    RenderSessionManager.SessionHealth.OK -> {
                        if (binding.statusText.text == getString(R.string.session_lost) ||
                            binding.statusText.text == getString(R.string.session_reconnecting)
                        ) binding.statusText.text = getString(R.string.session_recovered)
                    }
                    RenderSessionManager.SessionHealth.RETRYING ->
                        binding.statusText.text = getString(R.string.session_reconnecting)
                    RenderSessionManager.SessionHealth.LOST ->
                        binding.statusText.text = getString(R.string.session_lost)
                }
            }
        }
    }

    /** Thermal step-down (mirrors VRActivity.checkThermalState). */
    private fun startThermalMonitoring() {
        if (thermalMonitoring) return
        thermalMonitoring = true
        if (thermalRunnable == null) {
            thermalRunnable = Runnable { checkThermalState() }
        }
        thermalRunnable?.let {
            thermalHandler.removeCallbacks(it)
            thermalHandler.postDelayed(it, 5000)
        }
    }

    private fun stopThermalMonitoring() {
        thermalMonitoring = false
        thermalRunnable?.let { thermalHandler.removeCallbacks(it) }
    }

    private fun checkThermalState() {
        val pm = powerManager
        if (pm != null && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.Q) {
            val status = try { pm.currentThermalStatus } catch (e: Exception) { PowerManager.THERMAL_STATUS_NONE }
            ThermalPolicy.qualityForThermal(status)?.let { quality ->
                if (prefs.renderQuality != quality) {
                    prefs.renderQuality = quality
                    sceneBuilder?.setResolutionScale(RenderQuality.resolutionScale(quality))
                    toast(getString(R.string.thermal_stepdown, quality))
                }
            }
        }
        if (thermalMonitoring) {
            thermalRunnable?.let { thermalHandler.postDelayed(it, 5000) }
        }
    }

    override fun onPause() {
        sensorFusion?.onPause()
        super.onPause()
    }

    override fun onResume() {
        super.onResume()
        sensorFusion?.onResume()
    }

    override fun onDestroy() {
        sensorLoop?.let { sensorHandler.removeCallbacks(it) }
        sensorLoop = null
        stopThermalMonitoring()
        sensorFusion?.stop()
        controllerManager?.dispose()
        voiceHelper?.dispose()
        heartbeatJob?.cancel()
        // End the session BEFORE destroying local state, in a scope that
        // outlives onDestroy (lifecycleScope is already cancelled here, so a
        // launch in it would never execute and the session would leak server-side).
        val manager = sessionManager
        sessionManager = null
        if (manager?.session != null) {
            endScope.launch {
                try { manager.end() } catch (e: Exception) { }
            }
        }
        sceneBuilder?.destroy()
        sceneBuilder = null
        // NOTE: endScope is deliberately NOT cancelled here: it owns the single
        // detached end() call above and dies with the activity once it finishes.
        _binding = null
        super.onDestroy()
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()

    companion object {
        const val EXTRA_PROJECT_ID = "extra_project_id"
    }
}
