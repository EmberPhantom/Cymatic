package com.cymatic.client.render

import org.junit.Assert.*
import org.junit.Test

class ThermalPolicyTest {

    @Test
    fun `cool states keep quality`() {
        assertNull(ThermalPolicy.qualityForThermal(ThermalPolicy.THERMAL_NONE))
        assertNull(ThermalPolicy.qualityForThermal(ThermalPolicy.THERMAL_LIGHT))
        assertNull(ThermalPolicy.qualityForThermal(ThermalPolicy.THERMAL_MODERATE))
    }

    @Test
    fun `severe steps to medium, critical to low`() {
        assertEquals("medium", ThermalPolicy.qualityForThermal(ThermalPolicy.THERMAL_SEVERE))
        assertEquals("low", ThermalPolicy.qualityForThermal(ThermalPolicy.THERMAL_CRITICAL))
        assertEquals("low", ThermalPolicy.qualityForThermal(ThermalPolicy.THERMAL_EMERGENCY))
        assertEquals("low", ThermalPolicy.qualityForThermal(ThermalPolicy.THERMAL_SHUTDOWN))
    }

    @Test
    fun `warn threshold matches severe`() {
        assertFalse(ThermalPolicy.shouldWarn(ThermalPolicy.THERMAL_MODERATE))
        assertTrue(ThermalPolicy.shouldWarn(ThermalPolicy.THERMAL_SEVERE))
    }
}
