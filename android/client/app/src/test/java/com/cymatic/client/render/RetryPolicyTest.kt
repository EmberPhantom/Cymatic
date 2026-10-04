package com.cymatic.client.render

import org.junit.Assert.*
import org.junit.Test

class RetryPolicyTest {

    @Test
    fun `backoff doubles per attempt`() {
        assertEquals(2000L, RetryPolicy.delayForAttempt(0))
        assertEquals(4000L, RetryPolicy.delayForAttempt(1))
        assertEquals(8000L, RetryPolicy.delayForAttempt(2))
    }

    @Test
    fun `backoff saturates at max`() {
        assertEquals(30_000L, RetryPolicy.delayForAttempt(10))
        assertEquals(5_000L, RetryPolicy.delayForAttempt(10, baseMs = 1000L, maxMs = 5000L))
    }

    @Test
    fun `retryable codes cover not-ready and transient`() {
        assertTrue(RetryPolicy.shouldRetryHttp(404))
        assertTrue(RetryPolicy.shouldRetryHttp(408))
        assertTrue(RetryPolicy.shouldRetryHttp(429))
        assertTrue(RetryPolicy.shouldRetryHttp(500))
        assertTrue(RetryPolicy.shouldRetryHttp(503))
    }

    @Test
    fun `client errors are not retried`() {
        assertFalse(RetryPolicy.shouldRetryHttp(200))
        assertFalse(RetryPolicy.shouldRetryHttp(400))
        assertFalse(RetryPolicy.shouldRetryHttp(401))
        assertFalse(RetryPolicy.shouldRetryHttp(403))
    }

    @Test
    fun `attempt budget is exclusive`() {
        assertTrue(RetryPolicy.shouldRetryAttempt(0, 3))
        assertTrue(RetryPolicy.shouldRetryAttempt(2, 3))
        assertFalse(RetryPolicy.shouldRetryAttempt(3, 3))
    }
}
