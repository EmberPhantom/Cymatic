package com.cymatic.client.render

/**
 * Lighting preset table: cymatic_v1 preset/time_of_day -> sun color,
 * sun intensity multiplier and ambient level for Filament's LightManager
 * + IBL intensity. Matches the web viewer's look; pure data.
 */
object LightingPresets {

    data class Preset(
        val sunColor: FloatArray,
        val sunIntensity: Float,
        val ambient: Float,
        val skyTint: FloatArray,
        /** Filament-space sun travel direction (points down toward the scene). */
        val sunDirection: FloatArray = floatArrayOf(0.3f, -1.0f, -0.4f)
    )

    private val TABLE = mapOf(
        "warm" to Preset(floatArrayOf(1.0f, 0.85f, 0.68f), 2.2f, 0.45f, floatArrayOf(0.45f, 0.38f, 0.33f)),
        "cool" to Preset(floatArrayOf(0.82f, 0.90f, 1.0f), 1.8f, 0.55f, floatArrayOf(0.33f, 0.38f, 0.45f)),
        "neutral" to Preset(floatArrayOf(1.0f, 1.0f, 1.0f), 2.0f, 0.5f, floatArrayOf(0.4f, 0.4f, 0.42f)),
        "golden_hour" to Preset(floatArrayOf(1.0f, 0.62f, 0.30f), 2.6f, 0.35f, floatArrayOf(0.5f, 0.34f, 0.22f)),
        "blue_hour" to Preset(floatArrayOf(0.45f, 0.58f, 0.85f), 1.2f, 0.4f, floatArrayOf(0.20f, 0.26f, 0.40f)),
        "custom" to Preset(floatArrayOf(1.0f, 1.0f, 1.0f), 2.0f, 0.5f, floatArrayOf(0.4f, 0.4f, 0.42f))
    )

    private val TIME_OF_DAY_SCALE = mapOf(
        "morning" to 0.9f,
        "noon" to 1.0f,
        "evening" to 0.75f,
        "night" to 0.25f
    )

    fun resolve(
        preset: String,
        timeOfDay: String,
        ambientIntensity: Double,
        sunDirection: List<Double>? = null
    ): Preset {
        val base = TABLE[preset.lowercase()] ?: TABLE.getValue("neutral")
        val scale = TIME_OF_DAY_SCALE[timeOfDay.lowercase()] ?: 1.0f
        // Time of day scales BOTH sun and ambient: night must actually darken
        // the scene (the old code left ambient at the spec value, so night
        // scenes stayed bright).
        val ambient = (ambientIntensity.toFloat() * scale).coerceIn(0f, 1f)
        return base.copy(
            sunIntensity = base.sunIntensity * scale,
            ambient = ambient,
            sunDirection = resolveSunDirection(sunDirection)
        )
    }

    /**
     * Spec sun_direction (Unity space) -> normalized Filament direction.
     * Falls back to the default downward sun when absent/degenerate.
     */
    fun resolveSunDirection(sunDirection: List<Double>?): FloatArray {
        if (sunDirection != null && sunDirection.size >= 3) {
            val v = SceneCoords.toFilamentDirection(sunDirection)
            val n = kotlin.math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2])
            if (n > 1e-6f) return floatArrayOf(v[0] / n, v[1] / n, v[2] / n)
        }
        val d = floatArrayOf(0.3f, -1.0f, -0.4f)
        val n = kotlin.math.sqrt(d[0] * d[0] + d[1] * d[1] + d[2] * d[2])
        return floatArrayOf(d[0] / n, d[1] / n, d[2] / n)
    }

    /**
     * Unit ambient as spherical-harmonics irradiance for
     * IndirectLight.Builder.irradiance(3, sh): uniform ambient has only the
     * L00 (DC) term per channel; the 9-coeff-per-channel layout Filament
     * expects puts it at indices 0/9/18. Pair with
     * intensity(preset.ambient) so the preset scales the light exactly once
     * (the old stub baked ambient into the coefficients AND the intensity,
     * double-scaling it).
     *
     * This is a documented uniform-ambient approximation: no directional
     * sky/ground tint, which is fine for low-end baked-light walkthroughs.
     */
    fun unitAmbientSH(): FloatArray {
        val sh = FloatArray(27)
        sh[0] = 1f; sh[9] = 1f; sh[18] = 1f
        return sh
    }
}
