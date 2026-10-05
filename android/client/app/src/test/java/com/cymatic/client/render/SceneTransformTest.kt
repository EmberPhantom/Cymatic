package com.cymatic.client.render

import org.junit.Assert.*
import org.junit.Test
import kotlin.math.PI

class SceneTransformTest {

    @Test
    fun `identity compose is identity`() {
        val m = SceneTransform.compose(
            floatArrayOf(0f, 0f, 0f), floatArrayOf(0f, 0f, 0f), floatArrayOf(1f, 1f, 1f)
        )
        assertArrayEquals(SceneTransform.identity(), m, 1e-6f)
    }

    @Test
    fun `translation lands in last column`() {
        val m = SceneTransform.compose(
            floatArrayOf(1f, 2f, 3f), floatArrayOf(0f, 0f, 0f), floatArrayOf(1f, 1f, 1f)
        )
        assertEquals(1f, m[12], 1e-6f)
        assertEquals(2f, m[13], 1e-6f)
        assertEquals(3f, m[14], 1e-6f)
        assertEquals(1f, m[15], 1e-6f)
    }

    @Test
    fun `size is honored via effective scale`() {
        val m = SceneTransform.compose(
            floatArrayOf(0f, 0f, 0f), floatArrayOf(0f, 0f, 0f),
            floatArrayOf(1f, 1f, 1f), size = floatArrayOf(2f, 4f, 6f)
        )
        assertEquals(2f, m[0], 1e-6f)
        assertEquals(4f, m[5], 1e-6f)
        assertEquals(6f, m[10], 1e-6f)
    }

    @Test
    fun `size multiplies entity scale`() {
        val es = SceneTransform.effectiveScale(floatArrayOf(2f, 1f, 1f), floatArrayOf(3f, 4f, 5f))
        assertArrayEquals(floatArrayOf(6f, 4f, 5f), es, 1e-6f)
    }

    @Test
    fun `rotation is applied - 90deg yaw maps +X to -Z`() {
        val m = SceneTransform.compose(
            floatArrayOf(0f, 0f, 0f),
            floatArrayOf(0f, (PI / 2).toFloat(), 0f),
            floatArrayOf(1f, 1f, 1f)
        )
        val p = SceneTransform.transformPoint(m, 1f, 0f, 0f)
        assertArrayEquals(floatArrayOf(0f, 0f, -1f), p, 1e-5f)
    }

    @Test
    fun `zero scale entries fall back to one`() {
        val es = SceneTransform.effectiveScale(floatArrayOf(0f, 0f, 0f), null)
        assertArrayEquals(floatArrayOf(1f, 1f, 1f), es, 0f)
    }

    @Test
    fun `multiply by identity is identity`() {
        val m = SceneTransform.compose(
            floatArrayOf(1f, 2f, 3f),
            floatArrayOf(0.3f, -0.5f, 0.1f),
            floatArrayOf(2f, 2f, 2f)
        )
        val r = SceneTransform.multiply(m, SceneTransform.identity())
        assertArrayEquals(m, r, 1e-6f)
    }
}
