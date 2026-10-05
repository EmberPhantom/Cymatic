package com.cymatic.client.render

import com.cymatic.client.network.model.SceneAssetRef
import com.cymatic.client.network.model.ScenePerfBudget
import java.net.URLEncoder

/**
 * Render-core asset streaming planner (Phase 1, pure logic — no Android
 * imports so it stays JVM-testable).
 *
 * Decides, per manifest entry, whether the renderer should fetch bytes via
 * `GET /v1/assets/resolve/url` or fall back to its procedural primitive.
 * The server is the authority on availability (template catalog URIs answer
 * 404 `template_not_baked` until the bake stage lands); this planner only
 * enforces client-side budgets and ordering.
 */
sealed interface AssetPlan {
    /** Fetch bytes: resolve [uri] through [resolveUrl], [fetchFirst] first. */
    data class Fetch(
        val uri: String,
        val resolveUrl: String,
        val fetchFirst: Boolean,
    ) : AssetPlan

    /** Render procedurally without fetching. */
    data class Procedural(val uri: String, val reason: String) : AssetPlan
}

object AssetStream {
    /** Manifest types the Phase-1 renderer can turn into pixels. */
    private val FETCHABLE_TYPES = setOf("model", "texture")

    /**
     * Resolve-endpoint URL for a manifest URI.
     * Mirrors `GET /v1/assets/resolve/url` (see services/api endpoints).
     */
    fun resolveUrl(apiBaseUrl: String, uri: String, projectId: Int? = null): String {
        val base = apiBaseUrl.trimEnd('/')
        val q = StringBuilder("uri=${URLEncoder.encode(uri, "UTF-8")}")
        if (projectId != null) q.append("&project_id=").append(projectId)
        return "$base/v1/assets/resolve/url?$q"
    }

    /**
     * Plan a whole manifest. Required entries first (ascending triangles so
     * small essentials win ties), then optional; entries already in
     * [cachedIds] are skipped (no fetch needed). A running triangle sum
     * against [budget] degrades the tail to procedural.
     */
    fun planManifest(
        assets: List<SceneAssetRef>,
        budget: ScenePerfBudget,
        apiBaseUrl: String,
        projectId: Int? = null,
        cachedIds: Set<String> = emptySet(),
    ): List<AssetPlan> {
        val ordered = assets.sortedWith(
            compareByDescending<SceneAssetRef> { it.required }
                .thenBy { it.estimatedTriangles },
        )
        var triSum = 0
        return ordered.map { ref ->
            planOne(ref, budget, apiBaseUrl, projectId, cachedIds, triSum).also {
                if (it is AssetPlan.Fetch) triSum += ref.estimatedTriangles.coerceAtLeast(0)
            }
        }
    }

    private fun planOne(
        ref: SceneAssetRef,
        budget: ScenePerfBudget,
        apiBaseUrl: String,
        projectId: Int?,
        cachedIds: Set<String>,
        triSumSoFar: Int,
    ): AssetPlan {
        if (ref.uri.isBlank()) return AssetPlan.Procedural(ref.uri, "empty uri")
        if (ref.type !in FETCHABLE_TYPES) {
            return AssetPlan.Procedural(ref.uri, "unsupported type ${ref.type}")
        }
        if (ref.id in cachedIds) return AssetPlan.Procedural(ref.uri, "cached")
        val want = ref.estimatedTriangles.coerceAtLeast(0)
        if (triSumSoFar + want > budget.maxTriangles) {
            return AssetPlan.Procedural(ref.uri, "over triangle budget")
        }
        return AssetPlan.Fetch(
            uri = ref.uri,
            resolveUrl = resolveUrl(apiBaseUrl, ref.uri, projectId),
            fetchFirst = ref.required,
        )
    }
}
