package com.cymatic.client.render

import kotlin.math.acos
import kotlin.math.sqrt

/**
 * 3D gaze selection over markers/beacons: forward vector from the head
 * quaternion, angular match within [matchDegrees], 2 s dwell to confirm
 * (same dwell convention as GazeManager). Pure logic, JVM-tested.
 */
object GazeSelector {

    const val DWELL_SECONDS = 2.0
    const val MATCH_DEGREES = 5.0

    data class Target(val id: String, val kind: String, val position: FloatArray, val label: String)

    data class State(
        val currentId: String? = null,
        val dwellSec: Double = 0.0
    )

    fun targetsFrom(commands: List<RenderCommand>): List<Target> {
        return commands.mapNotNull {
            when (it) {
                is RenderCommand.Marker -> Target(it.id, "poi", it.position, it.label)
                is RenderCommand.NavBeacon -> Target(it.id, "nav", it.position, it.name.ifBlank { it.id })
                else -> null
            }
        }
    }

    /** Camera forward (-Z) rotated by head quaternion [x,y,z,w]. */
    fun forwardFromQuaternion(q: FloatArray): FloatArray {
        if (q.size < 4) return floatArrayOf(0f, 0f, -1f)
        val (x, y, z, w) = q
        // Rotate (0,0,-1) by q: third column of rotation matrix, negated.
        val m02 = 2 * (x * z + y * w)
        val m12 = 2 * (y * z - x * w)
        val m22 = 1 - 2 * (x * x + y * y)
        return floatArrayOf(-m02, -m12, -m22)
    }

    fun angleDeg(a: FloatArray, b: FloatArray): Double {
        val dot = (a[0] * b[0] + a[1] * b[1] + a[2] * b[2]).toDouble()
        val na = sqrt((a[0] * a[0] + a[1] * a[1] + a[2] * a[2]).toDouble()).coerceAtLeast(1e-9)
        val nb = sqrt((b[0] * b[0] + b[1] * b[1] + b[2] * b[2]).toDouble()).coerceAtLeast(1e-9)
        return Math.toDegrees(acos((dot / (na * nb)).coerceIn(-1.0, 1.0)))
    }

    data class Update(val state: State, val confirmed: Target?)

    /**
     * Advance dwell by [dtSec] given eye [eyePos] and head [forward].
     * Returns confirmed target once dwell completes (then resets).
     */
    fun update(
        state: State,
        targets: List<Target>,
        eyePos: FloatArray,
        forward: FloatArray,
        dtSec: Double
    ): Update {
        var best: Target? = null
        var bestAngle = MATCH_DEGREES
        for (t in targets) {
            val to = floatArrayOf(t.position[0] - eyePos[0], t.position[1] - eyePos[1], t.position[2] - eyePos[2])
            // Ignore targets behind the viewer.
            val along = to[0] * forward[0] + to[1] * forward[1] + to[2] * forward[2]
            if (along <= 0) continue
            val ang = angleDeg(to, forward)
            if (ang < bestAngle) {
                bestAngle = ang
                best = t
            }
        }
        if (best == null) return Update(State(), null)
        if (state.currentId != best.id) return Update(State(best.id, 0.0), null)
        val dwell = state.dwellSec + dtSec
        return if (dwell >= DWELL_SECONDS) Update(State(), best)
        else Update(State(best.id, dwell), null)
    }
}
