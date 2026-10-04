package com.cymatic.client.render

import com.cymatic.client.network.model.SceneAssetManifest
import com.cymatic.client.network.model.SceneEntity
import com.cymatic.client.network.model.ScenePerfBudget

/**
 * Maps cymatic_v1 entities to engine-agnostic render commands.
 * Filament (or any backend) consumes RenderCommand; GLB loading is decided
 * here: model URI present in the manifest -> LOAD_MODEL, else PRIMITIVE
 * fallback (first-class requirement, never a blank scene). Pure logic.
 */
sealed class RenderCommand {
    abstract val id: String
    abstract val name: String
    abstract val position: FloatArray
    abstract val rotationRad: FloatArray
    abstract val scale: FloatArray

    data class Box(
        override val id: String,
        override val name: String,
        override val position: FloatArray,
        override val rotationRad: FloatArray,
        override val scale: FloatArray,
        val size: FloatArray,
        val colorRgb: FloatArray,
        val roughness: Float
    ) : RenderCommand()

    data class Plane(
        override val id: String,
        override val name: String,
        override val position: FloatArray,
        override val rotationRad: FloatArray,
        override val scale: FloatArray,
        val width: Float,
        val height: Float,
        val colorRgb: FloatArray
    ) : RenderCommand()

    /** Point of interest: emissive marker + floating label. */
    data class Marker(
        override val id: String,
        override val name: String,
        override val position: FloatArray,
        override val rotationRad: FloatArray,
        override val scale: FloatArray,
        val label: String,
        val description: String,
        val hasNarration: Boolean
    ) : RenderCommand()

    /** Navigation beacon rendered on the floor. */
    data class NavBeacon(
        override val id: String,
        override val name: String,
        override val position: FloatArray,
        override val rotationRad: FloatArray,
        override val scale: FloatArray
    ) : RenderCommand()

    /** GLB model asset resolved from the manifest. */
    data class Model(
        override val id: String,
        override val name: String,
        override val position: FloatArray,
        override val rotationRad: FloatArray,
        override val scale: FloatArray,
        val uri: String,
        val estimatedTriangles: Int,
        /** True when the model was kept despite exceeding the perf budget
         * (caller must cap pixel cost / note the downgrade); normally an
         * over-budget model falls back to a primitive Box instead. */
        val downgraded: Boolean = false
    ) : RenderCommand()

    data class Light(
        override val id: String,
        override val name: String,
        override val position: FloatArray,
        override val rotationRad: FloatArray,
        override val scale: FloatArray,
        val lightType: String,
        val colorRgb: FloatArray,
        val intensity: Float,
        val range: Float?
    ) : RenderCommand()
}

object EntityMapper {

    /** Style -> base color + roughness for primitive fallbacks. */
    private val STYLE_COLORS = mapOf(
        "modern" to (floatArrayOf(0.82f, 0.83f, 0.84f) to 0.4f),
        "traditional" to (floatArrayOf(0.72f, 0.55f, 0.36f) to 0.8f),
        "luxury" to (floatArrayOf(0.85f, 0.78f, 0.62f) to 0.25f)
    )
    private val DEFAULT_COLOR = floatArrayOf(0.62f, 0.62f, 0.64f) to 0.7f

    fun styleColor(properties: Map<String, Any>): Pair<FloatArray, Float> {
        val style = (properties["style"] as? String)?.lowercase() ?: ""
        return STYLE_COLORS[style] ?: DEFAULT_COLOR
    }

    private fun stringProp(properties: Map<String, Any>, vararg keys: String): String? {
        for (k in keys) {
            val v = properties[k] as? String
            if (!v.isNullOrBlank()) return v
        }
        return null
    }

    @Suppress("UNCHECKED_CAST")
    private fun doubleListProp(properties: Map<String, Any>, key: String): List<Double>? {
        return (properties[key] as? List<*>)?.mapNotNull { (it as? Number)?.toDouble() }
    }

    /** Manifest URIs available for GLB resolution (exact match on id or uri). */
    fun manifestUris(manifest: SceneAssetManifest): Map<String, String> {
        val out = mutableMapOf<String, String>()
        for (a in manifest.assets) {
            if (a.type == "model" && a.uri.isNotBlank()) {
                if (a.id.isNotBlank()) out[a.id] = a.uri
                out[a.uri] = a.uri
            }
        }
        return out
    }

    /** Filename portion of an asset path/hint (after the last separator). */
    fun filenameOf(path: String): String =
        path.substringAfterLast('/').substringAfterLast('\\')

    /** True for loadable 3D model extensions (GLB preferred, glTF accepted). */
    fun isModelUri(uri: String): Boolean {
        val lower = uri.lowercase()
        return lower.endsWith(".glb") || lower.endsWith(".gltf")
    }

    /**
     * Resolve the GLB URI for an entity: exact id match first, else an exact
     * (case-insensitive) filename match of the prefab hint against manifest
     * URIs. Substring matching is deliberately NOT used — a hint of "chair"
     * must not resolve "armchair.glb". Returns null when nothing matches
     * exactly or the match is not a model file.
     */
    fun resolveModelUri(
        entityId: String,
        prefabPath: String?,
        manifestUris: Map<String, String>
    ): String? {
        manifestUris[entityId]?.let { if (isModelUri(it)) return it }
        val hint = prefabPath?.trim()?.takeIf { it.isNotEmpty() } ?: return null
        // An exact prefab path that is itself a manifest key wins.
        manifestUris[hint]?.let { if (isModelUri(it)) return it }
        val want = filenameOf(hint).lowercase()
        if (want.isEmpty()) return null
        for (uri in manifestUris.values.toSet()) {
            if (!isModelUri(uri)) continue
            if (filenameOf(uri).lowercase() == want) return uri
        }
        return null
    }

    /**
     * True when [estTris] blows through [budget]'s triangle limit. Null budget
     * means "no constraint" (legacy callers). Never silently ignored: callers
     * must fall back to a primitive or mark the Model downgraded.
     */
    fun budgetExceeded(estTris: Int, budget: ScenePerfBudget?): Boolean {
        if (budget == null) return false
        if (estTris <= 0) return false
        return estTris > budget.maxTriangles
    }

    fun mapEntity(
        entity: SceneEntity,
        manifestUris: Map<String, String>,
        performanceBudget: ScenePerfBudget? = null
    ): List<RenderCommand> {
        val out = mutableListOf<RenderCommand>()
        mapOne(entity, manifestUris, performanceBudget, out)
        return out
    }

    fun mapAll(
        entities: List<SceneEntity>,
        manifestUris: Map<String, String>,
        performanceBudget: ScenePerfBudget? = null
    ): List<RenderCommand> {
        val out = mutableListOf<RenderCommand>()
        for (e in entities) mapOne(e, manifestUris, performanceBudget, out)
        return out
    }

    private fun mapOne(
        entity: SceneEntity,
        manifestUris: Map<String, String>,
        performanceBudget: ScenePerfBudget?,
        out: MutableList<RenderCommand>
    ) {
        val pos = SceneCoords.toFilament(entity.position)
        val rot = SceneCoords.eulerToRadians(entity.rotation)
        val scl = SceneCoords.scaleOrDefault(entity.scale)
        val (color, rough) = styleColor(entity.properties)

        // GLB wins for ANY entity type with an exactly-resolved manifest URI.
        val modelUri = resolveModelUri(entity.id, entity.prefabPath, manifestUris)
        val estTris = ((entity.properties["estimated_triangles"] as? Number)?.toInt()) ?: 0
        if (modelUri != null) {
            if (budgetExceeded(estTris, performanceBudget)) {
                // Explicit fallback: primitive box, never a silent blow-through.
                out.add(
                    RenderCommand.Box(entity.id, entity.name, pos, rot, scl,
                        floatArrayOf(0.6f, 0.6f, 0.6f), color, rough)
                )
            } else {
                out.add(
                    RenderCommand.Model(entity.id, entity.name, pos, rot, scl, modelUri, estTris)
                )
            }
        } else when (entity.type) {
            "room", "wall" -> {
                val size = doubleListProp(entity.properties, "size")
                val sx = size?.getOrElse(0) { 4.0 } ?: 4.0
                val sy = size?.getOrElse(1) { 2.6 } ?: 2.6
                val sz = size?.getOrElse(2) { 4.0 } ?: 4.0
                out.add(
                    RenderCommand.Box(entity.id, entity.name, pos, rot, scl,
                        floatArrayOf(sx.toFloat(), sy.toFloat(), sz.toFloat()), color, rough)
                )
            }
            "floor", "ceiling" -> {
                val size = doubleListProp(entity.properties, "size")
                out.add(
                    RenderCommand.Plane(entity.id, entity.name, pos, rot, scl,
                        (size?.getOrElse(0) { 5.0 } ?: 5.0).toFloat(),
                        (size?.getOrElse(2) { 5.0 } ?: 5.0).toFloat(), color)
                )
            }
            "door", "window" -> out.add(
                RenderCommand.Box(entity.id, entity.name, pos, rot, scl,
                    floatArrayOf(1.0f, 2.1f, 0.12f), color, rough)
            )
            "poi" -> out.add(
                RenderCommand.Marker(
                    entity.id, entity.name, pos, rot, scl,
                    label = entity.name.ifBlank { entity.id },
                    description = stringProp(entity.properties, "description") ?: "",
                    hasNarration = (entity.properties["has_narration"] as? Boolean) == true
                )
            )
            "navigation_point" -> out.add(
                RenderCommand.NavBeacon(entity.id, entity.name, pos, rot, scl)
            )
            "light" -> {
                val colorProp = doubleListProp(entity.properties, "color")
                out.add(
                    RenderCommand.Light(
                        entity.id, entity.name, pos, rot, scl,
                        lightType = stringProp(entity.properties, "light_type", "type") ?: "point",
                        colorRgb = colorProp?.let {
                            floatArrayOf(
                                it.getOrElse(0) { 1.0 }.toFloat(),
                                it.getOrElse(1) { 1.0 }.toFloat(),
                                it.getOrElse(2) { 1.0 }.toFloat())
                        } ?: floatArrayOf(1f, 1f, 1f),
                        intensity = ((entity.properties["intensity"] as? Number)?.toFloat()) ?: 1f,
                        range = (entity.properties["range"] as? Number)?.toFloat()
                    )
                )
            }
            else -> out.add(
                RenderCommand.Box(entity.id, entity.name, pos, rot, scl,
                    floatArrayOf(0.6f, 0.6f, 0.6f), color, rough)
            )
        }
        for (child in entity.children) mapOne(child, manifestUris, performanceBudget, out)
    }
}
