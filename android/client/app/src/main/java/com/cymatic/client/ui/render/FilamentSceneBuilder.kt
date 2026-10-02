package com.cymatic.client.ui.render

import android.view.Choreographer
import android.view.SurfaceView
import com.cymatic.client.render.LightingPresets
import com.cymatic.client.render.RenderCommand
import com.google.android.filament.Colors
import com.google.android.filament.Engine
import com.google.android.filament.IndexBuffer
import com.google.android.filament.LightManager
import com.google.android.filament.Material
import com.google.android.filament.RenderableManager
import com.google.android.filament.Renderer
import com.google.android.filament.Scene
import com.google.android.filament.Skybox
import com.google.android.filament.TransformManager
import com.google.android.filament.VertexBuffer
import com.google.android.filament.View
import com.google.android.filament.android.DisplayHelper
import com.google.android.filament.android.UiHelper
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * Filament engine bootstrap for the native renderer.
 *
 * Builds: Engine + Renderer + Scene + SwapChain (via UiHelper) + two Views
 * (left/right viewports = phone stereo SBS) sharing one Scene, one sun light
 * from the LightingPresets table, and one entity per RenderCommand
 * (box/plane/marker primitives; Model commands load via gltfio when bytes
 * are available, otherwise fall back to a labeled box).
 *
 * Frame loop: Choreographer at display rate; [setHeadQuaternion] updates both
 * eye cameras from SensorFusion each frame. [setResolutionScale] backs the
 * thermal quality path (0.5 low .. 1.0 ultra).
 *
 * Materials come from `res/raw/ubershader.filamat` (build with matc, see
 * docs/27-mobile-render-pivot.md). Without it, [build] throws and the
 * activity degrades to preview mode.
 */
class FilamentSceneBuilder private constructor(
    private val engine: Engine,
    private val renderer: Renderer,
    private val scene: Scene,
    private val viewLeft: View,
    private val viewRight: View,
    private val uiHelper: UiHelper,
    private val displayHelper: DisplayHelper
) {
    private var swapChain: com.google.android.filament.SwapChain? = null
    private var frameCallback: Choreographer.FrameCallback? = null
    private var resolutionScale = 1.0f
    private var destroyed = false
    private var lastWidth = 0
    private var lastHeight = 0

    // Eye cameras are owned by their views; kept for per-frame updates.
    private var cameraLeft: com.google.android.filament.Camera? = null
    private var cameraRight: com.google.android.filament.Camera? = null

    companion object {
        private const val NEAR = 0.05
        private const val FAR = 500.0
        private const val FOV_DEG = 70.0

        @Volatile
        private var instance: FilamentSceneBuilder? = null

        /**
         * Builds (or returns) the shared scene for [surfaceView].
         * @param materialBytes compiled ubershader (.filamat). Null only when
         * the caller already degraded to preview mode.
         */
        fun build(
            surfaceView: SurfaceView,
            commands: List<RenderCommand>,
            preset: LightingPresets.Preset,
            materialBytes: ByteArray?
        ): FilamentSceneBuilder {
            instance?.let { if (!it.destroyed) return it }
            requireNotNull(materialBytes) { "ubershader.filamat missing (see docs/27)" }
            val engine = Engine.create()
            val renderer = engine.createRenderer()
            val scene = engine.createScene()
            val viewLeft = engine.createView()
            val viewRight = engine.createView()
            val uiHelper = UiHelper(UiHelper.ContextErrorPolicy.DONT_CHECK)
            val displayHelper = DisplayHelper(surfaceView.context)
            val builder = FilamentSceneBuilder(
                engine, renderer, scene, viewLeft, viewRight, uiHelper, displayHelper
            )
            builder.attach(surfaceView)
            builder.populate(commands, preset, materialBytes)
            instance = builder
            return builder
        }

    }

    /** SBS layout: each eye gets half width, full height; cameras created once. */
    private fun applyViewport() {
        val w = (lastWidth * resolutionScale).toInt().coerceAtLeast(2)
        val h = (lastHeight * resolutionScale).toInt().coerceAtLeast(2)
        if (w < 4 || h < 4) return
        viewLeft.viewport = Viewport(0, 0, w / 2, h)
        viewRight.viewport = Viewport(w / 2, 0, w - w / 2, h)
        val aspect = (w / 2.0) / h.toDouble()
        cameraLeft?.setProjection(FOV_DEG, aspect, NEAR, FAR, com.google.android.filament.Camera.Fov.VERTICAL)
        cameraRight?.setProjection(FOV_DEG, aspect, NEAR, FAR, com.google.android.filament.Camera.Fov.VERTICAL)
    }

    private fun attach(surfaceView: SurfaceView) {
        cameraLeft = engine.createCamera(engine.entityManager.create())
        cameraRight = engine.createCamera(engine.entityManager.create())
        viewLeft.camera = cameraLeft
        viewRight.camera = cameraRight
        uiHelper.attachTo(surfaceView)
        displayHelper.attach(surfaceView)
        uiHelper.renderCallback = object : UiHelper.RendererCallback {
            override fun onNativeWindowChanged(surface: android.view.Surface) {
                swapChain?.let { engine.destroySwapChain(it) }
                swapChain = engine.createSwapChain(surface)
                displayHelper.attach(surfaceView)
            }

            override fun onDetachedFromSurface() {
                swapChain?.let { engine.destroySwapChain(it) }
                swapChain = null
            }

            override fun onResized(width: Int, height: Int) {
                lastWidth = width
                lastHeight = height
                applyViewport()
            }
        }
    }

    private fun populate(
        commands: List<RenderCommand>,
        preset: LightingPresets.Preset,
        materialBytes: ByteArray
    ) {
        // Sky tint backdrop.
        val skybox = Skybox.Builder().color(
            preset.skyTint[0], preset.skyTint[1], preset.skyTint[2], 1.0f
        ).build(engine)
        scene.skybox = skybox
        scene.indirectLight = com.google.android.filament.IndirectLight.Builder()
            .irradiance(3, sh(preset.ambient))
            .intensity(preset.ambient)
            .build(engine)

        // Sun.
        val sun = engine.entityManager.create()
        LightManager.Builder(LightManager.Type.DIRECTIONAL)
            .color(preset.sunColor[0], preset.sunColor[1], preset.sunColor[2])
            .intensity(preset.sunIntensity * 1000f)
            .direction(0.3f, -1.0f, -0.4f)
            .castShadows(true)
            .build(engine, sun)
        scene.addEntities(sun)

        val material = Material.Builder()
            .payload(ByteBuffer.wrap(materialBytes), materialBytes.size)
            .build(engine)

        for (cmd in commands) {
            when (cmd) {
                is RenderCommand.Model -> {
                    // gltfio path lands in P3b (needs .glb bytes + ResourceLoader);
                    // until then every model degrades to its labeled fallback box.
                    addBox(cmd.id, cmd.position, cmd.scale, floatArrayOf(0.55f, 0.5f, 0.55f), 0.8f, material)
                }
                is RenderCommand.Box -> addBox(cmd.id, cmd.position, cmd.scale, cmd.colorRgb, cmd.roughness, material)
                is RenderCommand.Plane -> addPlane(cmd, material)
                is RenderCommand.Marker -> {
                    addBox(cmd.id, cmd.position, floatArrayOf(0.35f, 0.35f, 0.35f),
                        floatArrayOf(1.0f, 0.75f, 0.2f), 0.3f, material)
                    // Floating text labels arrive with the label-sprite pass (P3b).
                }
                is RenderCommand.NavBeacon -> addBox(cmd.id, cmd.position, floatArrayOf(0.5f, 0.06f, 0.5f),
                    floatArrayOf(0.2f, 0.8f, 1.0f), 0.5f, material)
                is RenderCommand.Light -> {
                    if (--customLightBudget < 0) continue
                    val e = engine.entityManager.create()
                    LightManager.Builder(LightManager.Type.POINT)
                        .color(cmd.colorRgb[0], cmd.colorRgb[1], cmd.colorRgb[2])
                        .intensity(cmd.intensity * 50f)
                        .falloff(cmd.range ?: 8f)
                        .position(cmd.position[0], cmd.position[1], cmd.position[2])
                        .castShadows(false)
                        .build(engine, e)
                    scene.addEntities(e)
                }
            }
        }
        viewLeft.scene = scene
        viewRight.scene = scene
    }

    private var customLightBudget = 4

    private fun sh(ambient: Float): FloatArray {
        // Flat ambient spherical-harmonics stub scaled by preset.
        val v = ambient * 0.6f
        return FloatArray(27) { i -> if (i % 9 == 0) v else 0f }
    }

    // ---- minimal unit-cube / unit-plane geometry (positions + normals) ----

    private fun addBox(
        id: String, pos: FloatArray, scale: FloatArray,
        color: FloatArray, roughness: Float, material: Material
    ) {
        // One instance per entity: baseColor/roughness are per-instance state.
        val mat = material.createInstance()
        val half = floatArrayOf(0.5f * scale[0], 0.5f * scale.getOrElse(1) { 1f }, 0.5f * scale.getOrElse(2) { 1f })
        val v = cubeVertices(half)
        val entity = renderable(v.first, v.second, mat)
        setTransform(entity, pos)
        setBaseColor(entity, mat, color, roughness)
        scene.addEntities(entity)
    }

    private fun addPlane(cmd: RenderCommand.Plane, material: Material) {
        val mat = material.createInstance()
        val hw = cmd.width / 2f
        val hh = cmd.height / 2f
        val positions = floatArrayOf(
            -hw, 0f, -hh, hw, 0f, -hh, hw, 0f, hh, -hw, 0f, hh
        )
        val normals = floatArrayOf(0f, 1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f)
        // (0,2,1),(0,3,2): CCW seen from +Y (verified by cross product).
        val indices = shortArrayOf(0, 2, 1, 0, 3, 2)
        val entity = renderable(positions, normals, indices, mat)
        setTransform(entity, cmd.position)
        setBaseColor(entity, mat, cmd.colorRgb, 0.9f)
        scene.addEntities(entity)
    }

    /**
     * Indexed cube. Winding rule: for index pattern (0,2,1),(0,3,2), triangle
     * (P0,P1,P2) faces outward iff (P1-P0)x(P2-P0) points along the outward
     * normal. Each face layout below was verified against that rule.
     * Filament culls clockwise faces, so this is load-bearing.
     */
    private fun cubeVertices(half: FloatArray): Triple<FloatArray, FloatArray, ShortArray> {
        val hx = half[0]; val hy = half[1]; val hz = half[2]
        val positions = floatArrayOf(
            -hx, -hy, -hz, hx, -hy, -hz, hx, hy, -hz, -hx, hy, -hz, // back (-z)
            -hx, -hy, hz, -hx, hy, hz, hx, hy, hz, hx, -hy, hz, // front (+z)
            -hx, -hy, -hz, -hx, hy, -hz, -hx, hy, hz, -hx, -hy, hz, // left (-x)
            hx, -hy, -hz, hx, -hy, hz, hx, hy, hz, hx, hy, -hz, // right (+x)
            -hx, -hy, -hz, -hx, -hy, hz, hx, -hy, hz, hx, -hy, -hz, // bottom (-y)
            -hx, hy, -hz, hx, hy, -hz, hx, hy, hz, -hx, hy, hz // top (+y)
        )
        val normals = floatArrayOf(
            0f, 0f, -1f, 0f, 0f, -1f, 0f, 0f, -1f, 0f, 0f, -1f,
            0f, 0f, 1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f, 0f, 1f,
            -1f, 0f, 0f, -1f, 0f, 0f, -1f, 0f, 0f, -1f, 0f, 0f,
            1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f, 0f,
            0f, -1f, 0f, 0f, -1f, 0f, 0f, -1f, 0f, 0f, -1f, 0f,
            0f, 1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f, 0f, 1f, 0f
        )
        val indices = ShortArray(36) { i ->
            val face = i / 6
            val k = i % 6
            val base = (face * 4).toShort()
            (base + intArrayOf(0, 2, 1, 0, 3, 2)[k]).toShort()
        }
        return Triple(positions, normals, indices)
    }

    private fun renderable(
        positions: FloatArray, normals: FloatArray, indices: ShortArray,
        mat: Material.MaterialInstance
    ): Int {
        // Interleaved layout: position xyz + normal xyz = 24 bytes/vertex.
        val vb = VertexBuffer.Builder()
            .vertexCount(positions.size / 3)
            .bufferCount(1)
            .attribute(VertexBuffer.VertexAttribute.POSITION, 0, VertexBuffer.AttributeType.FLOAT3, 0, 24)
            .attribute(VertexBuffer.VertexAttribute.NORMAL, 0, VertexBuffer.AttributeType.FLOAT3, 12, 24)
            .build(engine)
        // Interleave positions + normals into one buffer.
        val interleaved = ByteBuffer.allocateDirect(positions.size * 4 + normals.size * 4)
            .order(ByteOrder.nativeOrder())
        for (i in positions.indices step 3) {
            interleaved.putFloat(positions[i]); interleaved.putFloat(positions[i + 1]); interleaved.putFloat(positions[i + 2])
            interleaved.putFloat(normals[i]); interleaved.putFloat(normals[i + 1]); interleaved.putFloat(normals[i + 2])
        }
        interleaved.flip()
        vb.setBufferAt(engine, 0, interleaved)
        val ib = IndexBuffer.Builder()
            .indexCount(indices.size)
            .bufferType(IndexBuffer.Builder.IndexType.USHORT)
            .build(engine)
        val ibBuf = ByteBuffer.allocateDirect(indices.size * 2).order(ByteOrder.nativeOrder())
        for (s in indices) ibBuf.putShort(s)
        ibBuf.flip()
        ib.setBuffer(engine, ibBuf)
        val entity = engine.entityManager.create()
        RenderableManager.Builder(1)
            .boundingBox(com.google.android.filament.Box(0f, 0f, 0f, 1f, 1f, 1f))
            .material(0, mat)
            .geometry(0, RenderableManager.PrimitiveType.TRIANGLES, vb, ib)
            .culling(true)
            .receiveShadows(true)
            .castShadows(true)
            .build(engine, entity)
        return entity
    }

    private fun setTransform(entity: Int, pos: FloatArray) {
        val tm: TransformManager = engine.transformManager
        val instance = tm.getInstance(entity)
        val m = FloatArray(16)
        android.opengl.Matrix.setIdentityM(m, 0)
        android.opengl.Matrix.translateM(m, 0, pos[0], pos[1], pos[2])
        tm.setTransform(instance, m)
    }

    private fun setBaseColor(
        entity: Int, mat: Material.MaterialInstance, color: FloatArray, roughness: Float
    ) {
        // Ubershader contract: baseColor (float3) + roughness (float) parameters.
        mat.setParameter("baseColor", Colors.RgbType.SRGB, color[0], color[1], color[2])
        mat.setParameter("roughness", roughness)
    }

    // ---- stereo head pose + frame loop ----

    /**
     * Updates both eye cameras from a head quaternion [x,y,z,w] plus eye
     * separation. Called every frame from the render loop.
     */
    fun setHeadQuaternion(q: FloatArray, eyeSeparationM: Float) {
        val rot = quatToMatrix(q)
        updateEye(cameraLeft, rot, -eyeSeparationM / 2f)
        updateEye(cameraRight, rot, eyeSeparationM / 2f)
    }

    private fun updateEye(
        camera: com.google.android.filament.Camera?, rot: FloatArray, xOffset: Float
    ) {
        camera ?: return
        val eye = FloatArray(16)
        android.opengl.Matrix.multiplyMM(eye, 0, rot, 0, translationMatrix(xOffset, 0f, 0f), 0)
        // Filament camera looks down -Z; head pose from SensorFusion is +Z-forward,
        // so rotate 180° about Y to face the scene.
        val fix = FloatArray(16)
        android.opengl.Matrix.setRotateM(fix, 0, 180f, 0f, 1f, 0f)
        val model = FloatArray(16)
        android.opengl.Matrix.multiplyMM(model, 0, fix, 0, eye, 0)
        // Position comes from the tour/free-look rig via setEyePosition.
        val withPos = FloatArray(16)
        android.opengl.Matrix.multiplyMM(withPos, 0, translationMatrix(eyeX, eyeY, eyeZ), 0, model, 0)
        camera.setModelMatrix(withPos)
    }

    @Volatile var eyeX = 0f
    @Volatile var eyeY = 1.6f
    @Volatile var eyeZ = 0f

    fun setEyePosition(x: Float, y: Float, z: Float) {
        eyeX = x; eyeY = y; eyeZ = z
    }

    private fun translationMatrix(x: Float, y: Float, z: Float): FloatArray {
        val m = FloatArray(16)
        android.opengl.Matrix.setIdentityM(m, 0)
        android.opengl.Matrix.translateM(m, 0, x, y, z)
        return m
    }

    internal fun quatToMatrix(q: FloatArray): FloatArray {
        val m = FloatArray(16)
        android.opengl.Matrix.setIdentityM(m, 0)
        if (q.size >= 4) {
            try {
                val w = q[3].toDouble().coerceIn(-1.0, 1.0)
                val norm = Math.sqrt(
                    q[0] * q[0] + q[1] * q[1] + q[2] * q[2].toDouble() + w * w
                ).toFloat().coerceAtLeast(1e-6f)
                android.opengl.Matrix.setRotateM(
                    m, 0,
                    Math.toDegrees(2 * Math.acos(w)).toFloat(),
                    q[0] / norm, q[1] / norm, q[2] / norm
                )
            } catch (e: Exception) {
                // Degenerate quaternion: keep identity.
            }
        }
        return m
    }

    fun setResolutionScale(scale: Float) {
        resolutionScale = scale.coerceIn(0.4f, 1.0f)
        applyViewport()
    }

    fun startLoop() {
        if (frameCallback != null) return
        frameCallback = Choreographer.FrameCallback {
            if (destroyed) return@FrameCallback
            val chain = swapChain
            if (chain != null && renderer.beginFrame(chain)) {
                renderer.render(viewLeft)
                renderer.render(viewRight)
                renderer.endFrame()
            }
            if (!destroyed) Choreographer.getInstance().postFrameCallback(frameCallback!!)
        }
        Choreographer.getInstance().postFrameCallback(frameCallback!!)
    }

    fun destroy() {
        destroyed = true
        frameCallback?.let { Choreographer.getInstance().removeFrameCallback(it) }
        frameCallback = null
        try {
            swapChain?.let { engine.destroySwapChain(it) }
            swapChain = null
            engine.destroyRenderer(renderer)
            engine.destroyView(viewLeft)
            engine.destroyView(viewRight)
            engine.destroyScene(scene)
            engine.destroy()
        } catch (e: Exception) {
            // Best effort during teardown.
        } finally {
            if (instance === this) instance = null
        }
    }
}

// Viewport shorthand used by the SBS layout above.
private typealias Viewport = com.google.android.filament.Viewport
