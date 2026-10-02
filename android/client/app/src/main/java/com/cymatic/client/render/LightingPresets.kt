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
        val skyTint: FloatArray
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

    fun resolve(preset: String, timeOfDay: String, ambientIntensity: Double): Preset {
        val base = TABLE[preset.lowercase()] ?: TABLE.getValue("neutral")
        val scale = TIME_OF_DAY_SCALE[timeOfDay.lowercase()] ?: 1.0f
        val ambient = ambientIntensity.toFloat().coerceIn(0f, 1f)
        return base.copy(sunIntensity = base.sunIntensity * scale, ambient = ambient)
    }
}
