package com.cymatic.client.render

import kotlin.math.acos
import kotlin.math.sqrt

/**
 * 3D gaze selection over markers/beacons: forward vector from the head
 * quaternion, angular match within a distance/size-scaled cone, 2 s dwell to
 * confirm (same dwell convention as GazeManager). Pure logic, JVM-tested.
 */
object GazeSelector {

    const val DWELL_SECONDS = 2.0
    /** Base cone half-angle for a point target; scaled up by apparent size. */
    const val BASE_MATCH_DEGREES = 2.0
    /** Legacy fixed cone, kept for callers/tests that need the old behavior. */
    const val MATCH_DEGREES = 5.0
    /** Clamp for the scaled cone so distant walls can't capture everything. */
    const val MAX_MATCH_DEGREES = 15.0
    /** A controller press only confirms a target already dwelled this long. */
    const val PRESS_MIN_DWELL_SECONDS = 0.5

    data class Target(
        val id: String,
        val kind: String,
        val position: FloatArray,
        val label: String,
        /** Approximate bounding-sphere radius in meters (marker/beacon size). */
        val radiusM: Float = 0.3f
    )

    data class State(
        val currentId: String? = null,
        val dwellSec: Double = 0.0
    )

    fun targetsFrom(commands: List<RenderCommand>): List<Target> {
        return commands.mapNotNull {
            when (it) {
                is RenderCommand.Marker -> Target(it.id, "poi", it.position, it.label, radiusM = 0.35f)
                is RenderCommand.NavBeacon -> Target(it.id, "nav", it.position, it.name.ifBlank { it.id }, radiusM = 0.5f)
                else -> null
            }
        }
    }

    /**
     * Cone half-angle for a target of [radiusM] at [distanceM]: the base cone
     * plus the target's apparent angular radius, clamped. A fixed 5° cone
     * under-selects near/large beacons and over-selects far/small markers;
     * scaling by apparent size fixes both.
     */
    fun matchDegreesFor(distanceM: Double, radiusM: Float): Double {
        if (distanceM <= 1e-6) return MAX_MATCH_DEGREES
        val apparentDeg = Math.toDegrees(kotlin.math.atan2(radiusM.toDouble(), distanceM))
        return (BASE_MATCH_DEGREES + apparentDeg).coerceIn(BASE_MATCH_DEGREES, MAX_MATCH_DEGREES)
    }

    /** Distance from [eyePos] to [target]. */
    fun distanceTo(eyePos: FloatArray, target: Target): Double {
        val dx = (target.position[0] - eyePos[0]).toDouble()
        val dy = (target.position[1] - eyePos[1]).toDouble()
        val dz = (target.position[2] - eyePos[2]).toDouble()
        return sqrt(dx * dx + dy * dy + dz * dz)
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
        val best = bestTarget(targets, eyePos, forward) ?: return Update(State(), null)
        if (state.currentId != best.id) return Update(State(best.id, 0.0), null)
        val dwell = state.dwellSec + dtSec
        return if (dwell >= DWELL_SECONDS) Update(State(), best)
        else Update(State(best.id, dwell), null)
    }

    /**
     * Controller-press confirmation: returns the gazed target ONLY when the
     * press is separated from acquisition — i.e. the caller already dwelled
     * on this target for at least [PRESS_MIN_DWELL_SECONDS]. A bare press
     * with no prior dwell never confirms (the old caller passed a full
     * DWELL_SECONDS dt, auto-confirming whatever was under the reticle
     * within a single update).
     */
    fun confirmOnPress(
        state: State,
        targets: List<Target>,
        eyePos: FloatArray,
        forward: FloatArray
    ): Target? {
        if (state.currentId == null) return null
        if (state.dwellSec < PRESS_MIN_DWELL_SECONDS) return null
        val best = bestTarget(targets, eyePos, forward) ?: return null
        return if (best.id == state.currentId) best else null
    }

    private fun bestTarget(
        targets: List<Target>,
        eyePos: FloatArray,
        forward: FloatArray
    ): Target? {
        var best: Target? = null
        var bestAngle = Double.MAX_VALUE
        for (t in targets) {
            val to = floatArrayOf(t.position[0] - eyePos[0], t.position[1] - eyePos[1], t.position[2] - eyePos[2])
            // Ignore targets behind the viewer.
            val along = to[0] * forward[0] + to[1] * forward[1] + to[2] * forward[2]
            if (along <= 0) continue
            val dist = distanceTo(eyePos, t)
            val cone = matchDegreesFor(dist, t.radiusM)
            val ang = angleDeg(to, forward)
            if (ang < cone && ang < bestAngle) {
                bestAngle = ang
                best = t
            }
        }
        return best
    }
}
