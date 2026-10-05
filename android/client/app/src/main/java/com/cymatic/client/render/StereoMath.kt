package com.cymatic.client.render

import kotlin.math.acos
import kotlin.math.cos
import kotlin.math.sin
import kotlin.math.sqrt

/**
 * Pure stereo-rig + head-pose math for the phone SBS renderer.
 *
 * Conventions (must match FilamentSceneBuilder):
 * - Head quaternion is [x, y, z, w] from SensorFusion, +Z-forward.
 * - Filament cameras look down -Z, so a 180° yaw fix converts head space to
 *   view space.
 * - The per-eye IPD offset is applied AFTER the 180° fix (screen space), so a
 *   negative offset stays on the left of the screen. Applying it before the
 *   fix mirrors left/right (the old code did rot * T(offset) then fix * eye,
 *   which swaps the eyes on screen because the Y-180 maps +X to -X).
 *
 * Column-major 4x4 output. No Android dependencies — JVM unit-tested.
 */
object StereoMath {

    /** Normalize a quaternion; degenerate input yields identity [0,0,0,1]. */
    fun normalize(q: FloatArray): FloatArray {
        if (q.size < 4) return floatArrayOf(0f, 0f, 0f, 1f)
        val n = sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3])
        if (n < 1e-9f) return floatArrayOf(0f, 0f, 0f, 1f)
        return floatArrayOf(q[0] / n, q[1] / n, q[2] / n, q[3] / n)
    }

    /**
     * Quaternion -> rotation matrix (column-major 4x4).
     *
     * Correct form: normalize first, clamp w, divide the vector part by
     * sin(halfAngle). The old FilamentSceneBuilder.quatToMatrix divided the
     * raw axis by the full-quaternion norm and took acos of the unnormalized
     * (merely clamped) w, which is wrong for any non-unit quaternion with
     * |w| != norm (e.g. [0,0,0,0.5] produced a 120° spin instead of identity).
     */
    fun quatToMatrix(q: FloatArray): FloatArray {
        val m = SceneTransform.identity()
        if (q.size < 4) return m
        val qn = normalize(q)
        val w = qn[3].coerceIn(-1f, 1f)
        val halfAngle = acos(w)
        val sinHalf = sin(halfAngle)
        if (sinHalf < 1e-6f) return m // 0° (or 360°): identity rotation.
        val ax = qn[0] / sinHalf
        val ay = qn[1] / sinHalf
        val az = qn[2] / sinHalf
        val angle = 2f * halfAngle
        // Axis-angle -> rotation via Rodrigues, column-major.
        val c = cos(angle); val s = sin(angle); val t = 1f - c
        m[0] = t * ax * ax + c
        m[1] = t * ax * ay + s * az
        m[2] = t * ax * az - s * ay
        m[4] = t * ax * ay - s * az
        m[5] = t * ay * ay + c
        m[6] = t * ay * az + s * ax
        m[8] = t * ax * az + s * ay
        m[9] = t * ay * az - s * ax
        m[10] = t * az * az + c
        return m
    }

    /** 180° rotation about Y (head +Z-forward -> Filament -Z-forward). */
    fun yaw180Fix(): FloatArray {
        // cos180=-1, sin180=0: diag(-1, 1, -1).
        val m = SceneTransform.identity()
        m[0] = -1f; m[10] = -1f
        return m
    }

    /**
     * Full eye model matrix:
     * M = T(rigPos) * T(ipdOffsetX, 0, 0) * FixY180 * HeadRot.
     *
     * @param ipdOffsetX negative for the left eye, positive for the right eye
     * (screen space, meters).
     */
    fun composeEye(
        headRot: FloatArray,
        rigPos: FloatArray,
        ipdOffsetX: Float
    ): FloatArray {
        val tRig = SceneTransform.translation(
            rigPos.getOrElse(0) { 0f }, rigPos.getOrElse(1) { 0f }, rigPos.getOrElse(2) { 0f }
        )
        val tOff = SceneTransform.translation(ipdOffsetX, 0f, 0f)
        var m = SceneTransform.multiply(tRig, tOff)
        m = SceneTransform.multiply(m, yaw180Fix())
        m = SceneTransform.multiply(m, headRot)
        return m
    }

    /** Camera forward (-Z) rotated by head quaternion [x,y,z,w]. */
    fun forwardFromQuaternion(q: FloatArray): FloatArray {
        if (q.size < 4) return floatArrayOf(0f, 0f, -1f)
        val qn = normalize(q)
        val (x, y, z, w) = listOf(qn[0], qn[1], qn[2], qn[3])
        val m02 = 2 * (x * z + y * w)
        val m12 = 2 * (y * z - x * w)
        val m22 = 1 - 2 * (x * x + y * y)
        return floatArrayOf(-m02, -m12, -m22)
    }
}
