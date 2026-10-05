package com.cymatic.client.render

import com.cymatic.client.network.model.SceneAssetRef
import com.cymatic.client.network.model.ScenePerfBudget
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class AssetStreamTest {
    private val budget = ScenePerfBudget(maxTriangles = 1000)
    private val base = "https://api.example.com/"

    private fun ref(
        id: String,
        uri: String = "assets/models/$id.glb",
        type: String = "model",
        required: Boolean = false,
        tris: Int = 100,
    ) = SceneAssetRef(id = id, type = type, uri = uri, required = required, estimatedTriangles = tris)

    @Test
    fun `required entries fetch first`() {
        val plans = AssetStream.planManifest(
            listOf(ref("opt", required = false), ref("req", required = true)),
            budget, base,
        )
        val fetches = plans.filterIsInstance<AssetPlan.Fetch>()
        assertEquals(2, fetches.size)
        assertEquals("assets/models/req.glb", fetches[0].uri)
        assertTrue(fetches[0].fetchFirst)
    }

    @Test
    fun `triangle budget degrades tail to procedural`() {
        val plans = AssetStream.planManifest(
            listOf(ref("a", tris = 600), ref("b", tris = 600)),
            budget, base,
        )
        assertTrue(plans[0] is AssetPlan.Fetch)
        val tail = plans[1] as AssetPlan.Procedural
        assertEquals("over triangle budget", tail.reason)
    }

    @Test
    fun `empty uri and unsupported type go procedural`() {
        val plans = AssetStream.planManifest(
            listOf(ref("e", uri = ""), ref("s", type = "audio")),
            budget, base,
        )
        assertTrue(plans.all { it is AssetPlan.Procedural })
    }

    @Test
    fun `cached ids are skipped`() {
        val plans = AssetStream.planManifest(
            listOf(ref("a")), budget, base, cachedIds = setOf("a"),
        )
        assertEquals("cached", (plans[0] as AssetPlan.Procedural).reason)
    }

    @Test
    fun `resolve url encodes uri and project`() {
        val url = AssetStream.resolveUrl(base, "assets/models/my room.glb", 7)
        assertTrue(url.startsWith("https://api.example.com/v1/assets/resolve/url?"))
        assertTrue("project_id=7" in url)
        assertTrue("my+room.glb" in url || "my%20room.glb" in url)
    }
}
