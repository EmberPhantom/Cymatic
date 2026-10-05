package com.cymatic.client.render

import kotlin.math.PI

/**
 * Coordinate conversion: cymatic_v1 packages are authored in Unity's
 * left-handed Y-up space; Filament/OpenGL is right-handed Y-up.
 * Port of the web viewer's toThreeVec3: negate Z on positions and directions.
 *
 * Rotation convention (Unity euler degrees XYZ -> Filament radians):
 * mirroring Z maps yaw (Y) and roll (Z) to their negations while pitch (X)
 * passes through. Yaw is the load-bearing axis for walkthroughs: a Unity
 * yaw of +90deg must present the same facing after the Z-flip, which needs
 * the sign flip (verified: local +X of a yawed entity lands on the mirrored
 * world position only when ry is negated).
 *
 * NOTE: the web viewer (apps/viewer/src/scene.ts) negates yaw but passes
 * roll through unconverted, while this port negates both Y and Z (matching
 * the pre-existing Android behavior for Z). Combined-euler mirroring is an
 * approximation on both sides (Unity applies Y*X*Z, three.js/Filament XYZ);
 * single-axis placements — the overwhelmingly common case — are exact here.
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

    /** Unity euler degrees (XYZ) -> Filament radians, with Y and Z negated. */
    fun eulerToRadians(rotation: List<Double>): FloatArray {
        val rx = rotation.getOrElse(0) { 0.0 }
        val ry = rotation.getOrElse(1) { 0.0 }
        val rz = rotation.getOrElse(2) { 0.0 }
        val k = (PI / 180.0).toFloat()
        return floatArrayOf(rx.toFloat() * k, (-ry).toFloat() * k, (-rz).toFloat() * k)
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
