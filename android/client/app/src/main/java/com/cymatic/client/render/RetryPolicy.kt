package com.cymatic.client.render

/**
 * Pure retry/backoff policy for render-session network operations.
 *
 * Exponential backoff with a cap; callers `delay()` the returned value (which
 * honors coroutine cancellation, unlike the old fixed 5 s sleeps). No Android
 * dependencies — JVM unit-tested.
 */
object RetryPolicy {

    /**
     * Backoff delay for 0-based [attempt]: base * 2^attempt, capped at [maxMs].
     * Attempt 0 waits [baseMs], attempt 1 waits 2x, etc.
     */
    fun delayForAttempt(attempt: Int, baseMs: Long = 2000L, maxMs: Long = 30_000L): Long {
        require(attempt >= 0) { "attempt must be >= 0" }
        require(baseMs > 0) { "baseMs must be positive" }
        require(maxMs >= baseMs) { "maxMs must be >= baseMs" }
        val shifted = baseMs shl attempt.coerceAtMost(20)
        // Guard overflow: saturate at maxMs.
        if (shifted <= 0) return maxMs
        return shifted.coerceAtMost(maxMs)
    }

    /** HTTP codes worth retrying for scene fetch (generating/not-ready + transient). */
    fun shouldRetryHttp(code: Int): Boolean {
        return code == 404 || code == 408 || code == 429 || code >= 500
    }

    /** Attempt budget check: 0-based [attempt] must be below [maxAttempts]. */
    fun shouldRetryAttempt(attempt: Int, maxAttempts: Int): Boolean {
        return attempt < maxAttempts
    }

    /**
     * Heartbeat failures before the session is reported LOST (vs RETRYING).
     * Keeps the UI from flapping on a single dropped heartbeat.
     */
    const val HEARTBEAT_LOST_AFTER = 3
}
