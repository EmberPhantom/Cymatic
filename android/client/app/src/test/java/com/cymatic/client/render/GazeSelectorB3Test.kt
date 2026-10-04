package com.cymatic.client.render

import org.junit.Assert.*
import org.junit.Test

class GazeSelectorB3Test {

    @Test
    fun `cone widens for near large targets`() {
        // 0.5 m radius at 1 m: 2 + atan(0.5) ≈ 28.6° -> clamped to max.
        assertEquals(15.0, GazeSelector.matchDegreesFor(1.0, 0.5f), 1e-9)
    }

    @Test
    fun `cone stays near base for far small targets`() {
        // 0.1 m radius at 20 m: 2 + 0.29 ≈ 2.29°.
        assertEquals(2.0 + Math.toDegrees(kotlin.math.atan2(0.1, 20.0)),
            GazeSelector.matchDegreesFor(20.0, 0.1f), 1e-9)
    }

    @Test
    fun `zero distance clamps to max`() {
        assertEquals(GazeSelector.MAX_MATCH_DEGREES, GazeSelector.matchDegreesFor(0.0, 0.5f), 0.0)
    }

    @Test
    fun `wide-angle near beacon acquired without full dwell`() {
        // ~7.3° off-axis: missed by the old fixed 5° cone, inside the scaled
        // cone (2 + atan(0.5/5.04) ≈ 7.7°) for a 0.5 m beacon at ~5 m.
        val beacon = GazeSelector.Target("n1", "nav", floatArrayOf(0.64f, 1.6f, -5f), "Hall", 0.5f)
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val u = GazeSelector.update(
            GazeSelector.State(), listOf(beacon), eye, floatArrayOf(0f, 0f, -1f), 0.1
        )
        assertEquals("n1", u.state.currentId)
        assertNull(u.confirmed)
    }

    @Test
    fun `far small marker outside cone ignored`() {
        // ~7.1° off-axis at 20 m with 0.1 m radius: cone ≈ 2.3° -> ignored.
        val marker = GazeSelector.Target("m1", "poi", floatArrayOf(2.5f, 1.6f, -20f), "Far", 0.1f)
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val u = GazeSelector.update(
            GazeSelector.State(), listOf(marker), eye, floatArrayOf(0f, 0f, -1f), 2.5
        )
        assertNull(u.confirmed)
        assertNull(u.state.currentId)
    }

    @Test
    fun `press without prior dwell never confirms`() {
        val beacon = GazeSelector.Target("n1", "nav", floatArrayOf(0f, 1.6f, -5f), "Hall", 0.5f)
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val fwd = floatArrayOf(0f, 0f, -1f)
        assertNull(GazeSelector.confirmOnPress(GazeSelector.State(), listOf(beacon), eye, fwd))
    }

    @Test
    fun `press with brief dwell does not confirm`() {
        val beacon = GazeSelector.Target("n1", "nav", floatArrayOf(0f, 1.6f, -5f), "Hall", 0.5f)
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val fwd = floatArrayOf(0f, 0f, -1f)
        val state = GazeSelector.State("n1", 0.1)
        assertNull(GazeSelector.confirmOnPress(state, listOf(beacon), eye, fwd))
    }

    @Test
    fun `press after real dwell confirms`() {
        val beacon = GazeSelector.Target("n1", "nav", floatArrayOf(0f, 1.6f, -5f), "Hall", 0.5f)
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val fwd = floatArrayOf(0f, 0f, -1f)
        val state = GazeSelector.State("n1", 1.0)
        assertEquals("n1", GazeSelector.confirmOnPress(state, listOf(beacon), eye, fwd)?.id)
    }

    @Test
    fun `press on a different target than dwelled does not confirm`() {
        val a = GazeSelector.Target("a", "nav", floatArrayOf(0f, 1.6f, -5f), "A", 0.5f)
        val b = GazeSelector.Target("b", "nav", floatArrayOf(5f, 1.6f, -5f), "B", 0.5f)
        val eye = floatArrayOf(0f, 1.6f, 0f)
        val fwd = floatArrayOf(0f, 0f, -1f)
        val state = GazeSelector.State("b", 1.5)
        assertNull(GazeSelector.confirmOnPress(state, listOf(a, b), eye, fwd))
    }
}
