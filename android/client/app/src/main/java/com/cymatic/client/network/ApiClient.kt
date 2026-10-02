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
    
    private var baseUrl: String = "http://10.0.2.2:8000/" // Default for emulator; overridable via configure()
    
    private val gson = GsonBuilder()
        .setLenient()
        .create()

    private var prefs: PreferencesManager? = null
    fun initPrefs(p: PreferencesManager) { prefs = p }

    private val okHttpClient = OkHttpClient.Builder()
        .addInterceptor(HttpLoggingInterceptor().apply { level = if (BuildConfig.DEBUG) HttpLoggingInterceptor.Level.BODY else HttpLoggingInterceptor.Level.NONE })
        .connectTimeout(30, TimeUnit.SECONDS)
        .readTimeout(30, TimeUnit.SECONDS)
        .writeTimeout(30, TimeUnit.SECONDS)
        .addInterceptor { chain ->
            val builder = chain.request().newBuilder()
                .addHeader("Content-Type", "application/json")
                .addHeader("Accept", "application/json")
            prefs?.accessToken?.let { token -> builder.addHeader("Authorization", "Bearer $token") }
            chain.proceed(builder.build())
        }
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