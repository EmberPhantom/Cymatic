package com.cymatic.client.render

/** render_quality pref -> Filament resolution scale. Pure mapping, tested. */
object RenderQuality {
    fun resolutionScale(quality: String): Float = when (quality.lowercase()) {
        "low" -> 0.5f
        "medium" -> 0.75f
        "high" -> 0.9f
        "ultra" -> 1.0f
        else -> 0.75f
    }
}
