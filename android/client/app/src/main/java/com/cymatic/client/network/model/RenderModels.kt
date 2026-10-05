package com.cymatic.client.network.model

import com.google.gson.annotations.SerializedName

// --- Native render sessions (POST /v1/render/*, Unity-free path) ---

data class RenderSessionRequest(
    @SerializedName("project_id") val projectId: Int,
    @SerializedName("device_id") val deviceId: String,
    @SerializedName("app_version") val appVersion: String = "0.1.0"
)

data class RenderSessionResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("project_id") val projectId: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("status") val status: String,
    @SerializedName("device_id") val deviceId: String?,
    @SerializedName("scene_url") val sceneUrl: String?,
    @SerializedName("started_at") val startedAt: String?,
    @SerializedName("ended_at") val endedAt: String?
)

data class RenderHeartbeatResponse(
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("status") val status: String,
    @SerializedName("swept_stale") val sweptStale: Int = 0
)

data class RenderVoiceResponse(
    @SerializedName("transcript") val transcript: String,
    @SerializedName("response") val response: String,
    // Base64-encoded WAV reply; null when TTS unavailable.
    @SerializedName("audio_data") val audioData: String?
)

// --- cymatic_v1 scene package (GET .../scene-package/view) ---

data class ScenePackageView(
    @SerializedName("project") val project: SceneProject,
    @SerializedName("scene_package") val scenePackage: ScenePackage
)

data class SceneProject(
    @SerializedName("id") val id: Int,
    @SerializedName("name") val name: String,
    @SerializedName("domain") val domain: String
)

data class ScenePackage(
    @SerializedName("metadata") val metadata: Map<String, Any> = emptyMap(),
    @SerializedName("domain") val domain: String = "real_estate",
    @SerializedName("entities") val entities: List<SceneEntity> = emptyList(),
    @SerializedName("navigation") val navigation: SceneNavigation = SceneNavigation(),
    @SerializedName("lighting") val lighting: SceneLighting = SceneLighting(),
    @SerializedName("copilot_policy") val copilotPolicy: Map<String, Any> = emptyMap(),
    @SerializedName("performance_budget") val performanceBudget: ScenePerfBudget = ScenePerfBudget(),
    @SerializedName("asset_manifest") val assetManifest: SceneAssetManifest = SceneAssetManifest()
)

data class SceneEntity(
    @SerializedName("id") val id: String,
    @SerializedName("name") val name: String = "",
    @SerializedName("type") val type: String = "decoration",
    @SerializedName("position") val position: List<Double> = listOf(0.0, 0.0, 0.0),
    @SerializedName("rotation") val rotation: List<Double> = listOf(0.0, 0.0, 0.0),
    @SerializedName("scale") val scale: List<Double> = listOf(1.0, 1.0, 1.0),
    @SerializedName("prefab_path") val prefabPath: String? = null,
    @SerializedName("properties") val properties: Map<String, Any> = emptyMap(),
    @SerializedName("components") val components: List<Map<String, Any>> = emptyList(),
    @SerializedName("children") val children: List<SceneEntity> = emptyList()
)

data class SceneNavigation(
    @SerializedName("points") val points: List<NavPoint> = emptyList(),
    @SerializedName("paths") val paths: List<NavPath> = emptyList(),
    @SerializedName("default_start_point") val defaultStartPoint: String = "start"
)

data class NavPoint(
    @SerializedName("id") val id: String,
    @SerializedName("name") val name: String = "",
    @SerializedName("position") val position: List<Double> = listOf(0.0, 0.0, 0.0),
    @SerializedName("description") val description: String = "",
    @SerializedName("connections") val connections: List<String> = emptyList()
)

data class NavPath(
    @SerializedName("from_point") val fromPoint: String = "",
    @SerializedName("to_point") val toPoint: String = "",
    @SerializedName("type") val type: String = "walk",
    @SerializedName("waypoints") val waypoints: List<List<Double>> = emptyList()
)

data class SceneLighting(
    @SerializedName("preset") val preset: String = "neutral",
    @SerializedName("time_of_day") val timeOfDay: String = "noon",
    @SerializedName("ambient_intensity") val ambientIntensity: Double = 0.5,
    @SerializedName("sun_direction") val sunDirection: List<Double> = listOf(0.5, -1.0, 0.3),
    @SerializedName("custom_lights") val customLights: List<CustomLight> = emptyList()
)

data class CustomLight(
    @SerializedName("type") val type: String = "point",
    @SerializedName("position") val position: List<Double> = listOf(0.0, 2.5, 0.0),
    @SerializedName("color") val color: List<Double> = listOf(1.0, 1.0, 1.0),
    @SerializedName("intensity") val intensity: Double = 1.0,
    @SerializedName("range") val range: Double? = null,
    @SerializedName("angle") val angle: Double? = null
)

data class ScenePerfBudget(
    @SerializedName("target_fps") val targetFps: Int = 30,
    @SerializedName("max_triangles") val maxTriangles: Int = 50000,
    @SerializedName("max_draw_calls") val maxDrawCalls: Int = 60,
    @SerializedName("texture_budget_mb") val textureBudgetMb: Int = 64,
    @SerializedName("max_entities") val maxEntities: Int = 200,
    @SerializedName("lod_distances") val lodDistances: List<Double> = listOf(5.0, 15.0, 40.0)
)

data class SceneAssetManifest(
    @SerializedName("assets") val assets: List<SceneAssetRef> = emptyList(),
    @SerializedName("total_size_mb") val totalSizeMb: Double = 0.0
)

data class SceneAssetRef(
    @SerializedName("id") val id: String = "",
    @SerializedName("type") val type: String = "model",
    @SerializedName("uri") val uri: String = "",
    @SerializedName("fallback_uri") val fallbackUri: String? = null,
    @SerializedName("required") val required: Boolean = false,
    @SerializedName("estimated_triangles") val estimatedTriangles: Int = 0
)
