package com.cymatic.client.render

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.cymatic.client.BuildConfig
import com.cymatic.client.network.ApiClient
import com.cymatic.client.network.model.RenderSessionRequest
import com.cymatic.client.network.model.RenderSessionResponse
import com.cymatic.client.network.model.ScenePackageView
import kotlinx.coroutines.delay

/**
 * Owns the native render session lifecycle: create (device registry happens
 * server-side) -> scene fetch -> heartbeat loop -> end. Retries scene fetch
 * while the package is still generating (404 until ready).
 */
class RenderSessionManager(
    private val context: Context
) {
    var session: RenderSessionResponse? = null
        private set
    var scene: ScenePackageView? = null
        private set

    private fun deviceId(): String {
        val id = Settings.Secure.getString(context.contentResolver, Settings.Secure.ANDROID_ID)
        return "android-${id ?: Build.MODEL ?: "unknown"}".take(120)
    }

    suspend fun start(projectId: Int, maxSceneAttempts: Int = 12): Result<ScenePackageView> {
        val create = ApiClient.apiService.createRenderSession(
            RenderSessionRequest(projectId, deviceId(), BuildConfig.VERSION_NAME)
        )
        if (!create.isSuccessful || create.body() == null) {
            return Result.failure(RenderException("session_create_${create.code()}"))
        }
        session = create.body()

        var lastError = "scene_not_ready"
        repeat(maxSceneAttempts) {
            val view = ApiClient.apiService.getScenePackageView(projectId)
            if (view.isSuccessful && view.body() != null) {
                scene = view.body()
                return Result.success(scene!!)
            }
            lastError = "scene_${view.code()}"
            delay(5000)
        }
        return Result.failure(RenderException(lastError))
    }

    suspend fun heartbeat(): Boolean {
        val id = session?.id ?: return false
        return try {
            ApiClient.apiService.renderHeartbeat(id).isSuccessful
        } catch (e: Exception) {
            false
        }
    }

    suspend fun end() {
        val id = session?.id ?: return
        try {
            ApiClient.apiService.endRenderSession(id)
        } catch (e: Exception) {
            // Best effort: server sweeps stale sessions via heartbeat timeout.
        } finally {
            session = null
        }
    }

    class RenderException(message: String) : Exception(message)
}
