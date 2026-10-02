package com.cymatic.client.render

import org.junit.Assert.*
import org.junit.Test

class SceneCoordsTest {

    @Test
    fun `position flips Z for Filament`() {
        val out = SceneCoords.toFilament(listOf(1.0, 2.0, 3.0))
        assertArrayEquals(floatArrayOf(1f, 2f, -3f), out, 1e-6f)
    }

    @Test
    fun `short vectors default missing axes`() {
        val out = SceneCoords.toFilament(listOf(1.0))
        assertArrayEquals(floatArrayOf(1f, 0f, -0f), out, 1e-6f)
    }

    @Test
    fun `euler degrees become radians with negated Z`() {
        val out = SceneCoords.eulerToRadians(listOf(0.0, 90.0, 180.0))
        assertEquals(0f, out[0], 1e-5f)
        assertEquals(Math.PI.toFloat() / 2, out[1], 1e-5f)
        assertEquals(-Math.PI.toFloat(), out[2], 1e-5f)
    }

    @Test
    fun `empty scale defaults to one`() {
        assertArrayEquals(floatArrayOf(1f, 1f, 1f), SceneCoords.scaleOrDefault(emptyList()), 0f)
    }
}
