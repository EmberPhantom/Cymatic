package com.cymatic.client.network

import com.cymatic.client.BuildConfig
import com.cymatic.client.network.model.*
import com.cymatic.client.util.PreferencesManager
import com.google.gson.Gson
import com.google.gson.GsonBuilder
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.logging.HttpLoggingInterceptor
import okhttp3.Request
import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory
import retrofit2.http.Body
import retrofit2.http.GET
import retrofit2.http.Multipart
import retrofit2.http.POST
import retrofit2.http.Part
import retrofit2.http.Path
import java.util.concurrent.TimeUnit
import okhttp3.MultipartBody
import okhttp3.RequestBody

object ApiClient {

    /**
     * Default base URL (emulator loopback). Cleartext http here is for
     * local/emulator DEBUG traffic only — production must configure an https
     * URL via configure(); see AuthPolicy + network_security_config.xml.
     */
    private var baseUrl: String = AuthPolicy.DEFAULT_BASE_URL

    private val gson = GsonBuilder()
        .setLenient()
        .create()

    private var prefs: PreferencesManager? = null
    fun initPrefs(p: PreferencesManager) { prefs = p }

    // Bare client for the refresh call itself: no auth header, no logging of
    // bodies (the refresh response carries tokens).
    private val refreshHttpClient = OkHttpClient.Builder()
        .connectTimeout(15, TimeUnit.SECONDS)
        .readTimeout(15, TimeUnit.SECONDS)
        .build()

    private fun refreshAccessToken(): String? {
        val refreshToken = prefs?.refreshToken?.takeIf { it.isNotBlank() } ?: return null
        return try {
            val refreshRetrofit = Retrofit.Builder()
                .baseUrl(baseUrl)
                .client(refreshHttpClient)
                .addConverterFactory(GsonConverterFactory.create(gson))
                .build()
            val svc = refreshRetrofit.create(ApiService::class.java)
            // Authenticator runs on a background thread; blocking is allowed.
            val resp = kotlinx.coroutines.runBlocking {
                svc.refreshToken(RefreshRequest(token = refreshToken))
            }
            if (resp.isSuccessful && resp.body() != null) {
                val tokens = resp.body()!!
                prefs?.accessToken = tokens.accessToken
                if (tokens.refreshToken.isNotBlank()) prefs?.refreshToken = tokens.refreshToken
                tokens.accessToken
            } else {
                // Refresh rejected: drop tokens so the UI falls back to login.
                if (resp.code() == 401) {
                    prefs?.accessToken = null
                    prefs?.refreshToken = null
                }
                null
            }
        } catch (e: Exception) {
            null
        }
    }

    private val authAuthenticator = okhttp3.Authenticator { _, response ->
        val priorRetries = generateSequence(response) { it.priorResponse }.count() - 1
        val path = try { response.request.url.encodedPath } catch (e: Exception) { "" }
        val canRetry = AuthPolicy.shouldRefreshAndRetry(
            responseCode = response.code,
            priorAuthRetries = priorRetries,
            requestPath = path,
            hasRefreshToken = !prefs?.refreshToken.isNullOrBlank()
        )
        if (!canRetry) return@Authenticator null
        // Single-flight best effort: refresh, then retry once with the new token.
        val fresh = synchronized(this) {
            // Another thread may have refreshed already; reuse the current token.
            val current = prefs?.accessToken
            val sent = response.request.header(AuthPolicy.AUTHORIZATION_HEADER)
                ?.removePrefix("Bearer ")?.trim()
            if (!current.isNullOrBlank() && current != sent) current else refreshAccessToken()
        } ?: return@Authenticator null
        response.request.newBuilder()
            .header(AuthPolicy.AUTHORIZATION_HEADER, "Bearer $fresh")
            .build()
    }

    private val okHttpClient = OkHttpClient.Builder()
        // DEBUG body logging redacts Authorization (tokens never hit logcat),
        // but login/refresh bodies still carry secrets: DEBUG-only by design.
        .addInterceptor(HttpLoggingInterceptor().apply {
            level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY else HttpLoggingInterceptor.Level.NONE
            redactHeader(AuthPolicy.AUTHORIZATION_HEADER)
        })
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val builder = chain.request().newBuilder()
                .addHeader("Content-Type", "application/json")
                .addHeader("Accept", "application/json")
            AuthPolicy.bearerHeader(prefs?.accessToken)?.let { header ->
                builder.header(AuthPolicy.AUTHORIZATION_HEADER, header)
            }
            chain.proceed(builder.build())
        }
        .authenticator(authAuthenticator)
        .build()

    private var retrofit: Retrofit = Retrofit.Builder()
        .baseUrl(baseUrl)
        .client(okHttpClient)
        .addConverterFactory(GsonConverterFactory.create(gson))
        .build()

    var apiService: ApiService = retrofit.create(ApiService::class.java)
        private set

    fun configure(serverUrl: String) {
        val url = if (serverUrl.endsWith("/")) serverUrl else "$serverUrl/"
        baseUrl = url
        retrofit = Retrofit.Builder()
            .baseUrl(url)
            .client(okHttpClient)
            .addConverterFactory(GsonConverterFactory.create(gson))
            .build()
        apiService = retrofit.create(ApiService::class.java)
    }
}

interface ApiService {

    // Auth
    @POST("v1/auth/login")
    suspend fun login(@Body request: LoginRequest): retrofit2.Response<LoginResponse>

    @POST("v1/auth/register")
    suspend fun register(@Body request: RegisterRequest): retrofit2.Response<RegisterResponse>

    @POST("v1/auth/refresh")
    suspend fun refreshToken(@Body request: RefreshRequest): retrofit2.Response<LoginResponse>

    // Projects
    @GET("v1/projects")
    suspend fun getProjects(): retrofit2.Response<ProjectListResponse>

    @POST("v1/projects")
    suspend fun createProject(@Body request: CreateProjectRequest): retrofit2.Response<ProjectResponse>

    @GET("v1/projects/{id}")
    suspend fun getProject(@Path("id") projectId: Int): retrofit2.Response<ProjectResponse>

    // Spec generation
    @POST("v1/projects/{id}/intake")
    suspend fun intakePrompt(@Path("id") projectId: Int, @Body request: IntakeRequest): retrofit2.Response<IntakeResponse>

    @POST("v1/projects/{id}/clarify")
    suspend fun clarifyRequirements(@Path("id") projectId: Int, @Body request: ClarifyRequest): retrofit2.Response<ClarifyResponse>

    @POST("v1/projects/{id}/generate-spec")
    suspend fun generateSpec(@Path("id") projectId: Int, @Body request: GenerateSpecRequest): retrofit2.Response<JobResponse>

    @POST("v1/projects/{id}/validate-spec")
    suspend fun validateSpec(@Path("id") projectId: Int): retrofit2.Response<ValidateSpecResponse>

    @GET("v1/projects/{id}/specs")
    suspend fun listSpecs(@Path("id") projectId: Int): retrofit2.Response<SpecListResponse>

    @GET("v1/projects/{id}/specs/{spec_id}")
    suspend fun getSpec(@Path("id") projectId: Int, @Path("spec_id") specId: Int): retrofit2.Response<SpecResponse>

    // Native render (Unity-free path)
    @POST("v1/render/sessions")
    suspend fun createRenderSession(@Body request: RenderSessionRequest): retrofit2.Response<RenderSessionResponse>

    @POST("v1/render/sessions/{id}/heartbeat")
    suspend fun renderHeartbeat(@Path("id") sessionId: Int): retrofit2.Response<RenderHeartbeatResponse>

    @POST("v1/render/sessions/{id}/end")
    suspend fun endRenderSession(@Path("id") sessionId: Int): retrofit2.Response<RenderHeartbeatResponse>

    @Multipart
    @POST("v1/render/sessions/{id}/voice/audio")
    suspend fun renderVoiceAudio(
        @Path("id") sessionId: Int,
        @Part audio: MultipartBody.Part,
        @Part("language") language: RequestBody
    ): retrofit2.Response<RenderVoiceResponse>

    @GET("v1/projects/{id}/scene-package/view")
    suspend fun getScenePackageView(@Path("id") projectId: Int): retrofit2.Response<ScenePackageView>

    // Streaming (legacy Unity path, frozen)
    @POST("v1/stream/sessions")
    suspend fun createStreamSession(@Body request: StreamSessionRequest): retrofit2.Response<StreamSessionResponse>

    @GET("v1/stream/sessions/{id}")
    suspend fun getStreamSession(@Path("id") sessionId: String): retrofit2.Response<StreamSessionResponse>

    @POST("v1/stream/sessions/{id}/offer")
    suspend fun handleOffer(@Path("id") sessionId: String, @Body request: WebRTCOffer): retrofit2.Response<Unit>

    @POST("v1/stream/sessions/{id}/answer")
    suspend fun handleAnswer(@Path("id") sessionId: String, @Body request: WebRTCAnswer): retrofit2.Response<Unit>

    @POST("v1/stream/sessions/{id}/candidate")
    suspend fun handleCandidate(@Path("id") sessionId: String, @Body request: ICECandidate): retrofit2.Response<Unit>

    @POST("v1/stream/sessions/{id}/input")
    suspend fun handleInput(@Path("id") sessionId: String, @Body request: InputPacket): retrofit2.Response<Unit>

    // Copilot / Voice
    @POST("v1/stream/sessions/{id}/agent/message")
    suspend fun copilotMessage(@Path("id") sessionId: String, @Body request: CopilotMessage): retrofit2.Response<CopilotResponse>

    @POST("v1/stream/sessions/{id}/voice/transcript")
    suspend fun voiceTranscript(@Path("id") sessionId: String, @Body request: VoiceTranscript): retrofit2.Response<VoiceResponse>

    // Analytics
    @GET("v1/analytics/projects/{id}")
    suspend fun getProjectAnalytics(@Path("id") projectId: Int): retrofit2.Response<ProjectAnalytics>

    @GET("v1/analytics/sessions/{id}")
    suspend fun getSessionAnalytics(@Path("id") sessionId: Int): retrofit2.Response<SessionAnalytics>

    // Credits
    @GET("v1/credits/balance")
    suspend fun getCreditBalance(): retrofit2.Response<CreditBalance>

    @GET("v1/credits/usage")
    suspend fun getCreditUsage(): retrofit2.Response<CreditUsageList>

    @POST("v1/projects/{id}/specs/{spec_id}/edit")
    suspend fun editSpec(@Path("id") projectId: Int, @Path("spec_id") specId: Int, @Body request: EditRequest): retrofit2.Response<EditResponse>
}
