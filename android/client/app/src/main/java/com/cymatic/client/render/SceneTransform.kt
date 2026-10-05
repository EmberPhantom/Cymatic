package com.cymatic.client.render

import kotlin.math.cos
import kotlin.math.sin

/**
 * Pure scene-graph transform math for the native renderer.
 *
 * Column-major 4x4 matrices, same layout as android.opengl.Matrix, so results
 * can be handed directly to Filament's TransformManager without conversion.
 *
 * Convention: M = T(position) * Rx * Ry * Rz * S(effectiveScale), where
 * effectiveScale = size * scale component-wise when a spec `size` is present,
 * else scale. Rotation euler is radians in XYZ order, matching
 * [SceneCoords.eulerToRadians].
 *
 * No Android dependencies — JVM unit-tested.
 */
object SceneTransform {

    /** Identity matrix (column-major). */
    fun identity(): FloatArray = floatArrayOf(
        1f, 0f, 0f, 0f,
        0f, 1f, 0f, 0f,
        0f, 0f, 1f, 0f,
        0f, 0f, 0f, 1f
    )

    /**
     * Effective per-axis scale: spec `size` (physical dimensions, e.g. room
     * width/height/depth) multiplied by the entity `scale` multiplier.
     * Missing/zero entries fall back to 1.
     */
    fun effectiveScale(scale: FloatArray, size: FloatArray?): FloatArray {
        val sx = scale.getOrElse(0) { 1f }.let { if (it == 0f) 1f else it }
        val sy = scale.getOrElse(1) { 1f }.let { if (it == 0f) 1f else it }
        val sz = scale.getOrElse(2) { 1f }.let { if (it == 0f) 1f else it }
        if (size == null) return floatArrayOf(sx, sy, sz)
        return floatArrayOf(
            sx * size.getOrElse(0) { 1f },
            sy * size.getOrElse(1) { 1f },
            sz * size.getOrElse(2) { 1f }
        )
    }

    /**
     * Compose the full entity matrix. [rotationRad] is XYZ euler radians.
     * Previously FilamentSceneBuilder dropped rotation and `size` entirely
     * (boxes were always axis-aligned unit-scaled); both are honored here.
     */
    fun compose(
        position: FloatArray,
        rotationRad: FloatArray,
        scale: FloatArray,
        size: FloatArray? = null
    ): FloatArray {
        val px = position.getOrElse(0) { 0f }
        val py = position.getOrElse(1) { 0f }
        val pz = position.getOrElse(2) { 0f }
        val rx = rotationRad.getOrElse(0) { 0f }
        val ry = rotationRad.getOrElse(1) { 0f }
        val rz = rotationRad.getOrElse(2) { 0f }
        val es = effectiveScale(scale, size)

        // R = Rx * Ry * Rz (row-major 3x3 intermediates, multiplied explicitly
        // so the order is auditable; converted to column-major on output).
        val cx = cos(rx); val sx = sin(rx)
        val cy = cos(ry); val sy = sin(ry)
        val cz = cos(rz); val sz = sin(rz)
        val mx = arrayOf(
            floatArrayOf(1f, 0f, 0f),
            floatArrayOf(0f, cx, -sx),
            floatArrayOf(0f, sx, cx)
        )
        val my = arrayOf(
            floatArrayOf(cy, 0f, sy),
            floatArrayOf(0f, 1f, 0f),
            floatArrayOf(-sy, 0f, cy)
        )
        val mz = arrayOf(
            floatArrayOf(cz, -sz, 0f),
            floatArrayOf(sz, cz, 0f),
            floatArrayOf(0f, 0f, 1f)
        )
        val r = mat3Mul(mat3Mul(mx, my), mz)

        // M = T * R * S: scale the rotation columns, then set translation.
        // Column-major output: m[col * 4 + row].
        val m = FloatArray(16)
        for (c in 0 until 3) {
            val s = es[c]
            for (row in 0 until 3) m[c * 4 + row] = r[row][c] * s
            m[c * 4 + 3] = 0f
        }
        m[12] = px; m[13] = py; m[14] = pz; m[15] = 1f
        return m
    }

    private fun mat3Mul(a: Array<FloatArray>, b: Array<FloatArray>): Array<FloatArray> {
        return Array(3) { row ->
            FloatArray(3) { col ->
                a[row][0] * b[0][col] + a[row][1] * b[1][col] + a[row][2] * b[2][col]
            }
        }
    }

    /** Translation-only matrix. */
    fun translation(x: Float, y: Float, z: Float): FloatArray {
        val m = identity()
        m[12] = x; m[13] = y; m[14] = z
        return m
    }

    /** Column-major multiply: result = a * b. */
    fun multiply(a: FloatArray, b: FloatArray): FloatArray {
        val out = FloatArray(16)
        for (c in 0 until 4) {
            for (r in 0 until 4) {
                var sum = 0f
                for (k in 0 until 4) sum += a[k * 4 + r] * b[c * 4 + k]
                out[c * 4 + r] = sum
            }
        }
        return out
    }

    /** Transform a point (x,y,z,1) by column-major matrix [m]. */
    fun transformPoint(m: FloatArray, x: Float, y: Float, z: Float): FloatArray {
        return floatArrayOf(
            m[0] * x + m[4] * y + m[8] * z + m[12],
            m[1] * x + m[5] * y + m[9] * z + m[13],
            m[2] * x + m[6] * y + m[10] * z + m[14]
        )
    }
}
