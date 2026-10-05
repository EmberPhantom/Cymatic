package com.cymatic.client.render

import com.cymatic.client.network.model.NavPath
import com.cymatic.client.network.model.NavPoint
import org.junit.Assert.*
import org.junit.Test

class TourGuideTest {

    private fun pt(id: String, x: Double) =
        NavPoint(id = id, position = listOf(x, 0.0, 0.0))

    @Test
    fun `empty paths yield no legs`() {
        assertTrue(TourGuide.planTour(listOf(pt("a", 0.0)), emptyList()).isEmpty())
    }

    @Test
    fun `walk leg duration follows distance over speed plus dwell`() {
        // 12 m at 1.2 m/s = 10 s + 3 s dwell
        val legs = TourGuide.planTour(
            listOf(pt("a", 0.0), pt("b", 12.0)),
            listOf(NavPath(fromPoint = "a", toPoint = "b", type = "walk"))
        )
        assertEquals(1, legs.size)
        assertEquals(13.0, legs[0].durationSec, 1e-6)
        assertEquals(TourGuide.DWELL_SECONDS, legs[0].waypoints.last().dwellAfterSec, 1e-9)
    }

    @Test
    fun `teleport leg is instant`() {
        val legs = TourGuide.planTour(
            listOf(pt("a", 0.0), pt("b", 100.0)),
            listOf(NavPath(fromPoint = "a", toPoint = "b", type = "teleport"))
        )
        assertEquals(0.5, legs[0].durationSec, 1e-9)
    }

    @Test
    fun `unknown point ids are skipped`() {
        val legs = TourGuide.planTour(
            listOf(pt("a", 0.0)),
            listOf(NavPath(fromPoint = "a", toPoint = "ghost", type = "walk"))
        )
        assertTrue(legs.isEmpty())
    }

    @Test
    fun `total duration sums legs`() {
        val legs = listOf(
            TourGuide.TourLeg("a", "b", emptyList(), 5.0),
            TourGuide.TourLeg("b", "c", emptyList(), 7.0)
        )
        assertEquals(12.0, TourGuide.totalDuration(legs), 1e-9)
    }
}
