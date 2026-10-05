package com.cymatic.client.network

import org.junit.Assert.*
import org.junit.Test

class AuthPolicyTest {

    @Test
    fun `bearer header formats token`() {
        assertEquals("Bearer abc", AuthPolicy.bearerHeader("abc"))
        assertNull(AuthPolicy.bearerHeader(null))
        assertNull(AuthPolicy.bearerHeader("  "))
    }

    @Test
    fun `401 with refresh token retries once`() {
        assertTrue(
            AuthPolicy.shouldRefreshAndRetry(
                responseCode = 401,
                priorAuthRetries = 0,
                requestPath = "/v1/render/sessions",
                hasRefreshToken = true
            )
        )
    }

    @Test
    fun `no retry without refresh token`() {
        assertFalse(
            AuthPolicy.shouldRefreshAndRetry(401, 0, "/v1/render/sessions", false)
        )
    }

    @Test
    fun `no retry on non-401`() {
        assertFalse(
            AuthPolicy.shouldRefreshAndRetry(500, 0, "/v1/render/sessions", true)
        )
        assertFalse(
            AuthPolicy.shouldRefreshAndRetry(200, 0, "/v1/render/sessions", true)
        )
    }

    @Test
    fun `no retry on auth endpoints or repeats`() {
        assertFalse(
            AuthPolicy.shouldRefreshAndRetry(401, 0, "/v1/auth/refresh", true)
        )
        assertFalse(
            AuthPolicy.shouldRefreshAndRetry(401, 0, "/v1/auth/login", true)
        )
        assertFalse(
            AuthPolicy.shouldRefreshAndRetry(401, 1, "/v1/render/sessions", true)
        )
    }

    @Test
    fun `auth endpoints detected`() {
        assertTrue(AuthPolicy.isAuthEndpoint("/v1/auth/login"))
        assertTrue(AuthPolicy.isAuthEndpoint("/v1/auth/refresh"))
        assertTrue(AuthPolicy.isAuthEndpoint("/v1/auth/register"))
        assertFalse(AuthPolicy.isAuthEndpoint("/v1/render/sessions"))
    }

    @Test
    fun `cleartext detection flags emulator default`() {
        assertTrue(AuthPolicy.isCleartextHttp(AuthPolicy.DEFAULT_BASE_URL))
        assertTrue(AuthPolicy.isCleartextHttp("http://192.168.1.10:8000/"))
        assertFalse(AuthPolicy.isCleartextHttp("https://api.example.com/"))
    }
}
