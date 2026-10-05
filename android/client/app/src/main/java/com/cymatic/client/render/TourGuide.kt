package com.cymatic.client.render

import com.cymatic.client.network.model.NavPath
import com.cymatic.client.network.model.NavPoint
import kotlin.math.sqrt

/**
 * Guided-tour planner over NavigationSpec paths: ordered legs at walk speed
 * with dwell stops, mirroring the web viewer's Walkthrough (1.2 m/s, 3 s).
 * Pure logic — the renderer advances [TourLeg]s by elapsed time.
 */
object TourGuide {

    const val WALK_SPEED_M_S = 1.2
    const val DWELL_SECONDS = 3.0
    const val DEFAULT_LEG_SECONDS = 6.0

    data class Waypoint(val position: FloatArray, val dwellAfterSec: Double = 0.0)

    data class TourLeg(
        val fromId: String,
        val toId: String,
        val waypoints: List<Waypoint>,
        val durationSec: Double
    )

    private fun dist(a: FloatArray, b: FloatArray): Double {
        val dx = a[0] - b[0]
        val dy = a[1] - b[1]
        val dz = a[2] - b[2]
        return sqrt((dx * dx + dy * dy + dz * dz).toDouble())
    }

    fun planTour(points: List<NavPoint>, paths: List<NavPath>): List<TourLeg> {
        if (paths.isEmpty()) return emptyList()
        val byId = points.associateBy { it.id }
        val legs = mutableListOf<TourLeg>()
        for (p in paths) {
            val from = byId[p.fromPoint]?.let { SceneCoords.toFilament(it.position) }
            val to = byId[p.toPoint]?.let { SceneCoords.toFilament(it.position) }
            val mids = p.waypoints.map { SceneCoords.toFilament(it) }
            val chain = listOfNotNull(from) + mids + listOfNotNull(to)
            if (chain.size < 2) continue
            var length = 0.0
            for (i in 1 until chain.size) length += dist(chain[i - 1], chain[i])
            val walkDuration = if (length > 0.0) length / WALK_SPEED_M_S + DWELL_SECONDS
            else DEFAULT_LEG_SECONDS
            val duration = if (p.type == "teleport") 0.5 else walkDuration
            val wps = chain.mapIndexed { idx, pos ->
                Waypoint(pos, dwellAfterSec = if (idx == chain.lastIndex) DWELL_SECONDS else 0.0)
            }
            legs.add(TourLeg(p.fromPoint, p.toPoint, wps, duration))
        }
        return legs
    }

    fun totalDuration(legs: List<TourLeg>): Double = legs.sumOf { it.durationSec }

    data class Sample(val position: FloatArray, val legIndex: Int, val finished: Boolean)

    /** Camera position along the tour at [elapsedSec]; loops. Pure function. */
    fun sampleTour(legs: List<TourLeg>, elapsedSec: Double): Sample? {
        if (legs.isEmpty()) return null
        val total = totalDuration(legs)
        if (total <= 0.0) return Sample(legs[0].waypoints.firstOrNull()?.position ?: floatArrayOf(0f, 1.6f, 0f), 0, true)
        var t = elapsedSec % total
        for ((idx, leg) in legs.withIndex()) {
            if (t <= leg.durationSec) {
                val wps = leg.waypoints
                if (wps.isEmpty()) continue
                if (wps.size == 1 || leg.durationSec <= 0.0) return Sample(wps.last().position, idx, false)
                // Walk the polyline proportionally (dwell folded into leg time).
                var remaining = t
                val segTotal = wps.size - 1
                val segTime = leg.durationSec / segTotal
                var seg = (remaining / segTime).toInt().coerceIn(0, segTotal - 1)
                val frac = ((remaining - seg * segTime) / segTime).coerceIn(0.0, 1.0)
                val a = wps[seg].position
                val b = wps[seg + 1].position
                return Sample(
                    floatArrayOf(
                        (a[0] + (b[0] - a[0]) * frac).toFloat(),
                        (a[1] + (b[1] - a[1]) * frac).toFloat(),
                        (a[2] + (b[2] - a[2]) * frac).toFloat()
                    ),
                    idx, false
                )
            }
            t -= leg.durationSec
        }
        val last = legs.last()
        return Sample(last.waypoints.lastOrNull()?.position ?: floatArrayOf(0f, 1.6f, 0f), legs.lastIndex, true)
    }
}
