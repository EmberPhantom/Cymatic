package com.cymatic.client.render

import com.cymatic.client.network.model.SceneAssetManifest
import com.cymatic.client.network.model.SceneAssetRef
import com.cymatic.client.network.model.SceneEntity
import org.junit.Assert.*
import org.junit.Test

class EntityMapperTest {

    private fun entity(id: String, type: String, props: Map<String, Any> = emptyMap()) =
        SceneEntity(id = id, name = id, type = type,
            position = listOf(1.0, 0.0, 2.0), properties = props)

    @Test
    fun `room maps to box with style color`() {
        val cmds = EntityMapper.mapEntity(
            entity("r1", "room", mapOf("size" to listOf(5.0, 3.0, 4.0), "style" to "modern")),
            emptyMap()
        )
        assertEquals(1, cmds.size)
        val box = cmds[0] as RenderCommand.Box
        assertArrayEquals(floatArrayOf(5f, 3f, 4f), box.size, 1e-6f)
        // Z-flipped position
        assertArrayEquals(floatArrayOf(1f, 0f, -2f), box.position, 1e-6f)
    }

    @Test
    fun `poi maps to marker with narration flag`() {
        val cmds = EntityMapper.mapEntity(
            entity("p1", "poi", mapOf("description" to "Gopuram", "has_narration" to true)),
            emptyMap()
        )
        val marker = cmds[0] as RenderCommand.Marker
        assertEquals("Gopuram", marker.description)
        assertTrue(marker.hasNarration)
    }

    @Test
    fun `furniture without manifest falls back to primitive`() {
        val cmds = EntityMapper.mapEntity(entity("f1", "furniture"), emptyMap())
        assertTrue(cmds[0] is RenderCommand.Box)
    }

    @Test
    fun `furniture with manifest uri loads model`() {
        val manifest = mapOf("f1" to "models/chair.glb")
        val cmds = EntityMapper.mapEntity(entity("f1", "furniture"), manifest)
        val model = cmds[0] as RenderCommand.Model
        assertEquals("models/chair.glb", model.uri)
    }

    @Test
    fun `manifestUris indexes models only`() {
        val manifest = SceneAssetManifest(assets = listOf(
            SceneAssetRef(id = "c1", type = "model", uri = "models/chair.glb"),
            SceneAssetRef(id = "t1", type = "texture", uri = "tex/wall.png")
        ))
        val uris = EntityMapper.manifestUris(manifest)
        assertEquals("models/chair.glb", uris["c1"])
        assertFalse(uris.containsKey("t1"))
    }

    @Test
    fun `children are mapped recursively`() {
        val parent = entity("room1", "room", mapOf("size" to listOf(4.0, 3.0, 4.0)))
            .copy(children = listOf(entity("lamp1", "light")))
        val cmds = EntityMapper.mapEntity(parent, emptyMap())
        assertEquals(2, cmds.size)
        assertTrue(cmds[1] is RenderCommand.Light)
    }

    @Test
    fun `unknown type degrades to default box`() {
        val cmds = EntityMapper.mapEntity(entity("x1", "spaceship"), emptyMap())
        assertTrue(cmds[0] is RenderCommand.Box)
    }
}

class LightingPresetsTest {

    @Test
    fun `warm preset is warmer than cool`() {
        val warm = LightingPresets.resolve("warm", "evening", 0.5)
        val cool = LightingPresets.resolve("cool", "noon", 0.5)
        assertTrue(warm.sunColor[0] > cool.sunColor[0])
        assertTrue(warm.sunColor[2] < cool.sunColor[2])
    }

    @Test
    fun `night scales sun down`() {
        val noon = LightingPresets.resolve("neutral", "noon", 0.5)
        val night = LightingPresets.resolve("neutral", "night", 0.5)
        assertTrue(night.sunIntensity < noon.sunIntensity)
    }

    @Test
    fun `unknown preset falls back to neutral`() {
        val a = LightingPresets.resolve("mystery", "noon", 0.5)
        val b = LightingPresets.resolve("neutral", "noon", 0.5)
        assertArrayEquals(a.sunColor, b.sunColor, 1e-6f)
    }

    @Test
    fun `ambient follows spec budget`() {
        val p = LightingPresets.resolve("neutral", "noon", 0.8)
        assertEquals(0.8f, p.ambient, 1e-6f)
    }
}
