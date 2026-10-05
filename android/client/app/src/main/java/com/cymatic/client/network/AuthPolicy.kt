package com.cymatic.client.network

/**
 * Pure auth-interceptor policy for [ApiClient].
 *
 * Backend contract (services/api/app/api/v1/endpoints/auth.py):
 * - POST /v1/auth/refresh with JSON `{"token": "<refresh_token>"}` returns
 *   `{"access_token", "refresh_token"}`.
 * - Protected routes return 401 when the access token is expired/invalid.
 *
 * Kept free of OkHttp types so the rules are JVM unit-tested; ApiClient wires
 * them into an interceptor + authenticator.
 */
object AuthPolicy {

    const val AUTHORIZATION_HEADER = "Authorization"
    const val HTTP_UNAUTHORIZED = 401
    const val MAX_AUTH_RETRIES = 1

    /** Exact default base URL (emulator loopback). Cleartext http here is for
     * local/emulator debug traffic only — production builds must configure an
     * https URL via configure(). */
    const val DEFAULT_BASE_URL = "http://10.0.2.2:8000/"

    /** `Bearer <token>` header value, or null when there is no token. */
    fun bearerHeader(accessToken: String?): String? {
        if (accessToken.isNullOrBlank()) return null
        return "Bearer ${accessToken.trim()}"
    }

    /**
     * Whether a 401 response should trigger a refresh-and-retry.
     * Never retries auth endpoints themselves (would loop) and never retries
     * more than [MAX_AUTH_RETRIES] times per request.
     */
    fun shouldRefreshAndRetry(
        responseCode: Int,
        priorAuthRetries: Int,
        requestPath: String,
        hasRefreshToken: Boolean
    ): Boolean {
        if (responseCode != HTTP_UNAUTHORIZED) return false
        if (priorAuthRetries >= MAX_AUTH_RETRIES) return false
        if (isAuthEndpoint(requestPath)) return false
        return hasRefreshToken
    }

    /** Auth endpoints that must never go through refresh-retry. */
    fun isAuthEndpoint(path: String): Boolean {
        val p = path.lowercase()
        return p.contains("auth/login") || p.contains("auth/refresh") || p.contains("auth/register")
    }

    /** Counts prior Authorization retries by walking OkHttp-style prior responses. */
    fun countPriorResponses(priorResponseCount: Int): Int = priorResponseCount.coerceAtLeast(0)

    /** True when [url] uses cleartext http (debug/emulator only). */
    fun isCleartextHttp(url: String): Boolean {
        return url.lowercase().startsWith("http://")
    }
}
