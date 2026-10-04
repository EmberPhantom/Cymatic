package com.cymatic.client.render

/**
 * Pure thermal -> render-quality policy shared by VRActivity and RenderActivity.
 *
 * Takes the raw PowerManager thermal-status int (constants documented below
 * so this file stays free of Android dependencies and JVM-testable) and maps
 * it to a render-quality name (see [RenderQuality]) or null when no step-down
 * is needed.
 *
 * PowerManager values (API 29+): NONE=0, LIGHT=1, MODERATE=2, SEVERE=3,
 * CRITICAL=4, EMERGENCY=5, SHUTDOWN=6.
 */
object ThermalPolicy {

    const val THERMAL_NONE = 0
    const val THERMAL_LIGHT = 1
    const val THERMAL_MODERATE = 2
    const val THERMAL_SEVERE = 3
    const val THERMAL_CRITICAL = 4
    const val THERMAL_EMERGENCY = 5
    const val THERMAL_SHUTDOWN = 6

    /**
     * Quality to step down to at [thermalStatus], or null to keep the current
     * quality. Mirrors the VRActivity thresholds: warn at moderate, step down
     * at severe, minimum at critical+.
     */
    fun qualityForThermal(thermalStatus: Int): String? = when {
        thermalStatus >= THERMAL_CRITICAL -> "low"
        thermalStatus >= THERMAL_SEVERE -> "medium"
        else -> null
    }

    /** Whether [thermalStatus] warrants a user-visible warning. */
    fun shouldWarn(thermalStatus: Int): Boolean = thermalStatus >= THERMAL_SEVERE
}
