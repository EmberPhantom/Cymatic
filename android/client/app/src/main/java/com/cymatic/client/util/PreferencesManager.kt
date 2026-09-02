package com.cymatic.client.util

import android.content.Context
import android.content.SharedPreferences
import com.google.gson.Gson
import com.google.gson.reflect.TypeToken

class PreferencesManager(private val context: Context) {

    private val prefs: SharedPreferences = try {
        androidx.security.crypto.EncryptedSharedPreferences.create(
            "cymatic_prefs_enc",
            androidx.security.crypto.MasterKey.Builder(context).setKeyScheme(androidx.security.crypto.MasterKey.KeyScheme.AES256_GCM).build(),
            context,
            androidx.security.crypto.EncryptedSharedPreferences.PrefKeyEncryptionScheme.AES256_SIV,
            androidx.security.crypto.EncryptedSharedPreferences.PrefValueEncryptionScheme.AES256_GCM
        )
    } catch (_: Exception) {
        context.getSharedPreferences("cymatic_prefs", Context.MODE_PRIVATE)
    }
    private val gson = Gson()
    
    // Keys
    companion object {
        const val KEY_API_URL = "api_url"
        const val KEY_SIGNALING_URL = "signaling_url"
        const val KEY_ACCESS_TOKEN = "access_token"
        const val KEY_REFRESH_TOKEN = "refresh_token"
        const val KEY_USER_ID = "user_id"
        const val KEY_ORG_ID = "org_id"
        const val KEY_SELECTED_PROJECT_ID = "selected_project_id"
        const val KEY_USER_PREFERENCES = "user_preferences"
        const val KEY_HAND_TRACKING_ENABLED = "hand_tracking_enabled"
        const val KEY_VOICE_LANGUAGE = "voice_language"
        const val KEY_VOICE_SPEAKER = "voice_speaker"
        const val KEY_RENDER_QUALITY = "render_quality"
        const val KEY_IPD = "ipd"
    }
    
    // API
    var apiUrl: String
        get() = prefs.getString(KEY_API_URL, "http://10.0.2.2:8000")!!
        set(value) = prefs.edit().putString(KEY_API_URL, value).apply()
    
    var signalingUrl: String
        get() = prefs.getString(KEY_SIGNALING_URL, "ws://10.0.2.2:8000")!!
        set(value) = prefs.edit().putString(KEY_SIGNALING_URL, value).apply()
    
    // Auth
    var accessToken: String?
        get() = prefs.getString(KEY_ACCESS_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_ACCESS_TOKEN, value).apply()
    
    var refreshToken: String?
        get() = prefs.getString(KEY_REFRESH_TOKEN, null)
        set(value) = prefs.edit().putString(KEY_REFRESH_TOKEN, value).apply()
    
    var userId: Int?
        get() = prefs.getInt(KEY_USER_ID, -1).takeIf { it != -1 }
        set(value) = prefs.edit().putInt(KEY_USER_ID, value ?: -1).apply()
    
    var organizationId: Int?
        get() = prefs.getInt(KEY_ORG_ID, -1).takeIf { it != -1 }
        set(value) = prefs.edit().putInt(KEY_ORG_ID, value ?: -1).apply()
    
    // Selected project
    var selectedProjectId: Int?
        get() = prefs.getInt(KEY_SELECTED_PROJECT_ID, -1).takeIf { it != -1 }
        set(value) = prefs.edit().putInt(KEY_SELECTED_PROJECT_ID, value ?: -1).apply()
    
    // User preferences
    data class UserPreferences(
        val handTrackingEnabled: Boolean = false,
        val voiceLanguage: String = "en",
        val voiceSpeaker: String = "anushka",
        val renderQuality: String = "medium", // low, medium, high, ultra
        val ipd: Int = 64, // mm
        val enableHaptics: Boolean = true,
        val enableSpatialAudio: Boolean = true
    )
    
    var userPreferences: UserPreferences
        get() {
            val json = prefs.getString(KEY_USER_PREFERENCES, null)
            return if (json != null) {
                gson.fromJson(json, UserPreferences::class.java)
            } else {
                UserPreferences()
            }
        }
        set(value) {
            prefs.edit().putString(KEY_USER_PREFERENCES, gson.toJson(value)).apply()
        }
    
    // Convenience getters
    var isHandTrackingEnabled: Boolean
        get() = userPreferences.handTrackingEnabled
        set(value) {
            userPreferences = userPreferences.copy(handTrackingEnabled = value)
        }
    
    var voiceLanguage: String
        get() = userPreferences.voiceLanguage
        set(value) {
            userPreferences = userPreferences.copy(voiceLanguage = value)
        }
    
    var voiceSpeaker: String
        get() = userPreferences.voiceSpeaker
        set(value) {
            userPreferences = userPreferences.copy(voiceSpeaker = value)
        }
    
    var renderQuality: String
        get() = userPreferences.renderQuality
        set(value) {
            userPreferences = userPreferences.copy(renderQuality = value)
        }
    
    var ipd: Int
        get() = userPreferences.ipd
        set(value) {
            userPreferences = userPreferences.copy(ipd = value)
        }
    
    // Clear all (logout)
    fun clear() {
        prefs.edit().clear().apply()
    }
    
    // Check if logged in
    val isLoggedIn: Boolean
        get() = accessToken != null && userId != null
}