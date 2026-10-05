package com.cymatic.client.render

import org.junit.Assert.*
import org.junit.Test

class StereoMathTest {

    @Test
    fun `identity quaternion is identity matrix`() {
        val m = StereoMath.quatToMatrix(floatArrayOf(0f, 0f, 0f, 1f))
        assertArrayEquals(SceneTransform.identity(), m, 1e-6f)
    }

    @Test
    fun `180deg yaw maps +Z to -Z and +X to -X`() {
        // 180° about Y: q = [0, sin(90°), 0, cos(90°)] = [0,1,0,0].
        val m = StereoMath.quatToMatrix(floatArrayOf(0f, 1f, 0f, 0f))
        assertArrayEquals(
            floatArrayOf(0f, 0f, -1f),
            SceneTransform.transformPoint(m, 0f, 0f, 1f), 1e-5f
        )
        assertArrayEquals(
            floatArrayOf(-1f, 0f, 0f),
            SceneTransform.transformPoint(m, 1f, 0f, 0f), 1e-5f
        )
    }

    @Test
    fun `non-unit zero-rotation quaternion is identity`() {
        // Old code: acos(clamped 0.5) -> 120° spin. Correct: scale-only -> identity.
        val m = StereoMath.quatToMatrix(floatArrayOf(0f, 0f, 0f, 0.5f))
        assertArrayEquals(SceneTransform.identity(), m, 1e-5f)
    }

    @Test
    fun `non-unit yaw quaternion matches normalized form`() {
        val a = StereoMath.quatToMatrix(floatArrayOf(0f, 2f, 0f, 0f))
        val b = StereoMath.quatToMatrix(floatArrayOf(0f, 1f, 0f, 0f))
        assertArrayEquals(a, b, 1e-5f)
    }

    @Test
    fun `degenerate quaternion is identity`() {
        val m = StereoMath.quatToMatrix(floatArrayOf(0f, 0f, 0f, 0f))
        assertArrayEquals(SceneTransform.identity(), m, 0f)
    }

    @Test
    fun `short quaternion is identity`() {
        val m = StereoMath.quatToMatrix(floatArrayOf(0f, 0f))
        assertArrayEquals(SceneTransform.identity(), m, 0f)
    }

    @Test
    fun `left eye offset stays left of right eye on screen`() {
        val rot = StereoMath.quatToMatrix(floatArrayOf(0f, 0f, 0f, 1f))
        val rig = floatArrayOf(0f, 1.6f, 0f)
        val left = StereoMath.composeEye(rot, rig, -0.032f)
        val right = StereoMath.composeEye(rot, rig, 0.032f)
        // Screen-space offsets survive the 180° fix without sign swap.
        assertEquals(-0.032f, left[12], 1e-6f)
        assertEquals(0.032f, right[12], 1e-6f)
        assertTrue(left[12] < right[12])
        assertEquals(1.6f, left[13], 1e-6f)
    }

    @Test
    fun `forward from identity looks down minus Z`() {
        assertArrayEquals(
            floatArrayOf(0f, 0f, -1f),
            StereoMath.forwardFromQuaternion(floatArrayOf(0f, 0f, 0f, 1f)), 1e-5f
        )
    }
}
