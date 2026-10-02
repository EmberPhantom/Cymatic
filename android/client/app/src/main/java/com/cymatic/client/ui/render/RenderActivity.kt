package com.cymatic.client.ui.render

import android.os.Bundle
import android.os.Handler
import android.os.Looper
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
import com.cymatic.client.render.TourGuide
import com.cymatic.client.sensor.SensorFusion
import com.cymatic.client.util.PreferencesManager
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.isActive
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
        val commands = EntityMapper.mapAll(scene.entities, manifestUris)
        val preset = LightingPresets.resolve(
            scene.lighting.preset, scene.lighting.timeOfDay, scene.lighting.ambientIntensity
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
        startSensorLoop()
        startHeartbeatLoop()
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

        // Gaze dwell over POIs / nav beacons.
        if (gazeTargets.isNotEmpty()) {
            val forward = GazeSelector.forwardFromQuaternion(quat)
            val update = GazeSelector.update(gazeState, gazeTargets, eyePos, forward, 0.05)
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
        // Reticle-centered: confirm whatever gaze currently dwells on, else toast.
        val forward = GazeSelector.forwardFromQuaternion(lastHeadQuat)
        val update = GazeSelector.update(gazeState, gazeTargets, eyePos, forward, GazeSelector.DWELL_SECONDS)
        update.confirmed?.let { onGazeConfirmed(it) }
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
        heartbeatJob = lifecycleScope.launch {
            while (isActive) {
                delay(60_000)
                if (sessionManager?.heartbeat() != true) {
                    binding.statusText.text = getString(R.string.session_lost)
                }
            }
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
        sensorFusion?.stop()
        controllerManager?.dispose()
        voiceHelper?.dispose()
        sceneBuilder?.destroy()
        sceneBuilder = null
        heartbeatJob?.cancel()
        // Best effort: the server sweeps heartbeat-silent sessions after timeout.
        lifecycleScope.launch { sessionManager?.end() }
        _binding = null
        super.onDestroy()
    }

    private fun toast(msg: String) = Toast.makeText(this, msg, Toast.LENGTH_LONG).show()

    companion object {
        const val EXTRA_PROJECT_ID = "extra_project_id"
    }
}
