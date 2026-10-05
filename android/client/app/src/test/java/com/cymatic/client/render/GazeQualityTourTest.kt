package com.cymatic.client.render

import org.junit.Assert.*
import org.junit.Test

class GazeSelectorTest {

    private val beacon = GazeSelector.Target("n1", "nav", floatArrayOf(0f, 0f, -5f), "Hall")

    @Test
    fun `identity quaternion looks down minus Z`() {
        val fwd = GazeSelector.forwardFromQuaternion(floatArrayOf(0f, 0f, 0f, 1f))
        assertArrayEquals(floatArrayOf(-0f, -0f, -1f), fwd, 1e-5f)
    }

    @Test
    fun `dwell confirms after two seconds`() {
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val fwd = floatArrayOf(0f, -0.32f, -0.95f)
        var state = GazeSelector.State()
        var confirmed: GazeSelector.Target? = null
        repeat(5) {
            val u = GazeSelector.update(state, listOf(beacon), eye, fwd, 0.5)
            state = u.state
            confirmed = u.confirmed ?: confirmed
        }
        assertEquals("n1", confirmed?.id)
        // Dwell resets after confirm.
        assertNull(state.currentId)
    }

    @Test
    fun `looking away resets dwell`() {
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val fwd = floatArrayOf(0f, -0.32f, -0.95f)
        var state = GazeSelector.update(GazeSelector.State(), listOf(beacon), eye, fwd, 0.5).state
        assertEquals("n1", state.currentId)
        state = GazeSelector.update(state, listOf(beacon), eye, floatArrayOf(0f, 0f, 1f), 0.5).state
        assertNull(state.currentId)
    }

    @Test
    fun `targets behind viewer are ignored`() {
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val behind = GazeSelector.Target("b1", "nav", floatArrayOf(0f, 1.6f, 5f), "Behind")
        val u = GazeSelector.update(
            GazeSelector.State(), listOf(behind), eye, floatArrayOf(0f, 0f, -1f), 2.5
        )
        assertNull(u.confirmed)
    }

    @Test
    fun `targetsFrom keeps markers and beacons only`() {
        val cmds = listOf(
            RenderCommand.Box("b", "b", floatArrayOf(0f, 0f, 0f), FloatArray(3), floatArrayOf(1f, 1f, 1f),
                floatArrayOf(1f, 1f, 1f), floatArrayOf(1f, 1f, 1f), 0.5f),
            RenderCommand.Marker("m", "POI", floatArrayOf(0f, 0f, 0f), FloatArray(3), floatArrayOf(1f, 1f, 1f),
                "POI", "desc", true),
            RenderCommand.NavBeacon("n", "Hall", floatArrayOf(0f, 0f, 0f), FloatArray(3), floatArrayOf(1f, 1f, 1f))
        )
        val targets = GazeSelector.targetsFrom(cmds)
        assertEquals(listOf("m", "n"), targets.map { it.id })
    }
}

class RenderQualityTest {

    @Test
    fun `quality mapping`() {
        assertEquals(0.5f, RenderQuality.resolutionScale("low"), 1e-6f)
        assertEquals(0.75f, RenderQuality.resolutionScale("medium"), 1e-6f)
        assertEquals(0.9f, RenderQuality.resolutionScale("high"), 1e-6f)
        assertEquals(1.0f, RenderQuality.resolutionScale("ultra"), 1e-6f)
        assertEquals(0.75f, RenderQuality.resolutionScale("mystery"), 1e-6f)
    }
}

class TourSampleTest {

    @Test
    fun `sample interpolates along leg`() {
        val legs = listOf(
            TourGuide.TourLeg("a", "b",
                listOf(
                    TourGuide.Waypoint(floatArrayOf(0f, 0f, 0f)),
                    TourGuide.Waypoint(floatArrayOf(12f, 0f, 0f))
                ), 13.0)
        )
        val mid = TourGuide.sampleTour(legs, 5.0)!!
        // 5s of 13s along 12 m ≈ 4.6 m
        assertEquals(12.0 * (5.0 / 13.0), mid.position[0].toDouble(), 1e-4)
        assertFalse(mid.finished)
    }

    @Test
    fun `empty tour samples null`() {
        assertNull(TourGuide.sampleTour(emptyList(), 1.0))
    }
}
