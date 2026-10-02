package com.cymatic.client.render

import kotlin.math.PI

/**
 * Coordinate conversion: cymatic_v1 packages are authored in Unity's
 * left-handed Y-up space; Filament/OpenGL is right-handed Y-up.
 * Port of the web viewer's toThreeVec3: negate Z on positions and directions.
 * Pure math — JVM unit-tested, no Android dependencies.
 */
object SceneCoords {

    fun toFilament(position: List<Double>): FloatArray {
        val x = position.getOrElse(0) { 0.0 }
        val y = position.getOrElse(1) { 0.0 }
        val z = position.getOrElse(2) { 0.0 }
        return floatArrayOf(x.toFloat(), y.toFloat(), (-z).toFloat())
    }

    fun toFilamentDirection(direction: List<Double>): FloatArray = toFilament(direction)

    /** Unity euler degrees (XYZ) -> Filament radians, with Z negated. */
    fun eulerToRadians(rotation: List<Double>): FloatArray {
        val rx = rotation.getOrElse(0) { 0.0 }
        val ry = rotation.getOrElse(1) { 0.0 }
        val rz = rotation.getOrElse(2) { 0.0 }
        val k = (PI / 180.0).toFloat()
        return floatArrayOf(rx.toFloat() * k, ry.toFloat() * k, (-rz).toFloat() * k)
    }

    fun scaleOrDefault(scale: List<Double>): FloatArray {
        if (scale.isEmpty()) return floatArrayOf(1f, 1f, 1f)
        return floatArrayOf(
            (if (scale[0] == 0.0) 1.0 else scale[0]).toFloat(),
            (if (scale.getOrElse(1) { 1.0 } == 0.0) 1.0 else scale.getOrElse(1) { 1.0 }).toFloat(),
            (if (scale.getOrElse(2) { 1.0 } == 0.0) 1.0 else scale.getOrElse(2) { 1.0 }).toFloat()
        )
    }
}
