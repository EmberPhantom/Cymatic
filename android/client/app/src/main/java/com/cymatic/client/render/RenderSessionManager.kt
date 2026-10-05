package com.cymatic.client.render

import android.content.Context
import android.os.Build
import android.provider.Settings
import com.cymatic.client.BuildConfig
import com.cymatic.client.network.ApiClient
import com.cymatic.client.network.model.RenderSessionRequest
import com.cymatic.client.network.model.RenderSessionResponse
import com.cymatic.client.network.model.ScenePackageView
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import kotlin.coroutines.coroutineContext

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

        // Exponential backoff honoring cancellation: delay() throws on cancel,
        // and ensureActive() aborts before wasted network calls.
        var lastError = "scene_not_ready"
        for (attempt in 0 until maxSceneAttempts) {
            coroutineContext.ensureActive()
            try {
                val view = ApiClient.apiService.getScenePackageView(projectId)
                if (view.isSuccessful && view.body() != null) {
                    scene = view.body()
                    return Result.success(scene!!)
                }
                lastError = "scene_${view.code()}"
                if (!RetryPolicy.shouldRetryHttp(view.code())) break
            } catch (e: Exception) {
                coroutineContext.ensureActive()
                lastError = "scene_error_${e.javaClass.simpleName}"
            }
            if (!RetryPolicy.shouldRetryAttempt(attempt + 1, maxSceneAttempts)) break
            delay(RetryPolicy.delayForAttempt(attempt))
        }
        return Result.failure(RenderException(lastError))
    }

    /** Recovery state surfaced to the UI by the heartbeat loop. */
    enum class SessionHealth { OK, RETRYING, LOST }

    suspend fun heartbeat(): Boolean {
        val id = session?.id ?: return false
        return try {
            ApiClient.apiService.renderHeartbeat(id).isSuccessful
        } catch (e: Exception) {
            false
        }
    }

    /**
     * Repeating heartbeat while the session is alive. Reports OK on success,
     * RETRYING while [RetryPolicy.HEARTBEAT_LOST_AFTER] consecutive failures
     * accumulate, LOST after that. The job ends when the scope cancels or the
     * session is cleared.
     */
    fun startHeartbeatLoop(
        scope: CoroutineScope,
        intervalMs: Long = 60_000,
        onHealth: (SessionHealth) -> Unit = {}
    ): Job = scope.launch {
        var consecutiveFailures = 0
        while (isActive && session != null) {
            delay(intervalMs)
            if (!isActive || session == null) break
            if (heartbeat()) {
                consecutiveFailures = 0
                onHealth(SessionHealth.OK)
            } else {
                consecutiveFailures++
                onHealth(
                    if (consecutiveFailures >= RetryPolicy.HEARTBEAT_LOST_AFTER) SessionHealth.LOST
                    else SessionHealth.RETRYING
                )
            }
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
