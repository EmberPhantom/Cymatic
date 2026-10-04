package com.cymatic.client.network.model

import com.google.gson.annotations.SerializedName

data class LoginRequest(
    @SerializedName("username") val email: String,
    @SerializedName("password") val password: String
)

data class LoginResponse(
    @SerializedName("access_token") val accessToken: String,
    @SerializedName("refresh_token") val refreshToken: String,
    @SerializedName("token_type") val tokenType: String = "bearer"
)

data class RefreshRequest(
    @SerializedName("token") val token: String
)

data class RegisterRequest(
    @SerializedName("email") val email: String,
    @SerializedName("password") val password: String,
    @SerializedName("name") val name: String,
    @SerializedName("organization_id") val organizationId: Int? = null
)

data class RegisterResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("email") val email: String,
    @SerializedName("name") val name: String,
    @SerializedName("role") val role: String,
    @SerializedName("organization_id") val organizationId: Int,
    @SerializedName("is_active") val isActive: Boolean
)

data class ProjectListResponse(
    val projects: List<ProjectResponse>
)

data class ProjectResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("organization_id") val organizationId: Int,
    @SerializedName("name") val name: String,
    @SerializedName("domain") val domain: String,
    @SerializedName("category") val category: String?,
    @SerializedName("status") val status: String,
    @SerializedName("created_by") val createdBy: Int,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String?
)

data class CreateProjectRequest(
    @SerializedName("name") val name: String,
    @SerializedName("domain") val domain: String,
    @SerializedName("category") val category: String? = null
)

data class IntakeRequest(
    @SerializedName("prompt") val prompt: String,
    @SerializedName("context") val context: Map<String, Any> = emptyMap()
)

data class IntakeResponse(
    @SerializedName("detected_domain") val detectedDomain: String,
    @SerializedName("objective") val objective: String,
    @SerializedName("missing_fields") val missingFields: List<String>,
    @SerializedName("suggested_questions") val suggestedQuestions: List<String>,
    @SerializedName("extracted_entities") val extractedEntities: Map<String, Any>,
    @SerializedName("confidence") val confidence: Double
)

data class ClarifyRequest(
    @SerializedName("answers") val answers: Map<String, String>
)

data class ClarifyResponse(
    @SerializedName("updated_fields") val updatedFields: Map<String, Any>,
    @SerializedName("ready_for_generation") val readyForGeneration: Boolean,
    @SerializedName("completion_percentage") val completionPercentage: Double,
    @SerializedName("remaining_questions") val remainingQuestions: List<ClarificationQuestion>
)

data class ClarificationQuestion(
    @SerializedName("field") val field: String,
    @SerializedName("question") val question: String,
    @SerializedName("type") val type: String,
    @SerializedName("options") val options: List<String>,
    @SerializedName("required") val required: Boolean,
    @SerializedName("depends_on") val dependsOn: String?
)

data class GenerateSpecRequest(
    @SerializedName("prompt") val prompt: String,
    @SerializedName("context") val context: Map<String, Any> = emptyMap()
)

data class JobResponse(
    @SerializedName("job_id") val jobId: String,
    @SerializedName("status") val status: String,
    @SerializedName("message") val message: String
)

data class ValidateSpecResponse(
    @SerializedName("valid") val valid: Boolean,
    @SerializedName("errors") val errors: List<String>,
    @SerializedName("warnings") val warnings: List<String>
)

data class SpecListResponse(
    val specs: List<SpecResponse>
)

data class SpecResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("project_id") val projectId: Int,
    @SerializedName("version") val version: Int,
    @SerializedName("payload_json") val payloadJson: Map<String, Any>,
    @SerializedName("status") val status: String,
    @SerializedName("created_at") val createdAt: String,
    @SerializedName("updated_at") val updatedAt: String?
)

data class StreamSessionRequest(
    @SerializedName("project_id") val projectId: Int,
    @SerializedName("device_info") val deviceInfo: Map<String, Any> = emptyMap()
)

data class StreamSessionResponse(
    @SerializedName("id") val id: String,
    @SerializedName("project_id") val projectId: Int,
    @SerializedName("user_id") val userId: Int,
    @SerializedName("device_info_json") val deviceInfoJson: Map<String, Any>,
    @SerializedName("started_at") val startedAt: String,
    @SerializedName("ended_at") val endedAt: String?,
    @SerializedName("status") val status: String
)

data class WebRTCOffer(
    @SerializedName("sdp") val sdp: String,
    @SerializedName("type") val type: String = "offer"
)

data class WebRTCAnswer(
    @SerializedName("sdp") val sdp: String,
    @SerializedName("type") val type: String = "answer"
)

data class ICECandidate(
    @SerializedName("candidate") val candidate: String,
    @SerializedName("sdp_mid") val sdpMid: String,
    @SerializedName("sdp_mline_index") val sdpMLineIndex: Int
)

data class InputPacket(
    @SerializedName("input_type") val inputType: String,
    @SerializedName("payload") val payload: Map<String, Any>,
    // Epoch milliseconds - must match Unity's InputManager.InputPacket.timestamp (long, ms),
    // since input packets are relayed byte-for-byte from Android to the render server.
    @SerializedName("timestamp") val timestamp: Long
) {
    companion object {
        const val TYPE_HEAD_POSE = "head_pose"
        const val TYPE_GAZE = "gaze"
        const val TYPE_CONTROLLER = "controller"
        const val TYPE_VOICE = "voice"
        const val TYPE_HAND_TRACKING = "hand_tracking"
    }
}

data class HeadPoseData(
    @SerializedName("position") val position: FloatArray,
    @SerializedName("rotation") val rotation: FloatArray
)

data class GazeData(
    @SerializedName("origin") val origin: FloatArray,
    @SerializedName("direction") val direction: FloatArray,
    @SerializedName("target_id") val targetId: String?,
    @SerializedName("target_position") val targetPosition: FloatArray,
    @SerializedName("dwell_progress") val dwellProgress: Float
)

data class ControllerData(
    @SerializedName("select_pressed") val selectPressed: Boolean,
    @SerializedName("menu_pressed") val menuPressed: Boolean,
    @SerializedName("ptt_pressed") val pttPressed: Boolean,
    @SerializedName("touchpad_delta") val touchpadDelta: Pair<Float, Float>,
    @SerializedName("touchpad_position") val touchpadPosition: Pair<Float, Float>,
    @SerializedName("touchpad_touched") val touchpadTouched: Boolean
)

data class VoiceData(
    @SerializedName("is_recording") val isRecording: Boolean,
    @SerializedName("data") val data: ByteArray?
)

data class HandTrackingData(
    @SerializedName("left_hand") val leftHand: HandData?,
    @SerializedName("right_hand") val rightHand: HandData?
)

data class HandData(
    @SerializedName("position") val position: FloatArray,
    @SerializedName("rotation") val rotation: FloatArray,
    @SerializedName("joint_positions") val jointPositions: List<FloatArray>,
    @SerializedName("joint_confidences") val jointConfidences: FloatArray,
    @SerializedName("gesture") val gesture: String
)

data class CopilotMessage(
    @SerializedName("message") val message: String,
    @SerializedName("context") val context: Map<String, Any> = emptyMap()
)

data class CopilotResponse(
    @SerializedName("response") val response: String,
    @SerializedName("actions") val actions: List<CopilotAction>
)

data class CopilotAction(
    @SerializedName("type") val type: String,
    @SerializedName("params") val params: Map<String, Any>
)

data class VoiceTranscript(
    @SerializedName("transcript") val transcript: String,
    @SerializedName("language") val language: String = "en",
    @SerializedName("confidence") val confidence: Float?
)

data class VoiceResponse(
    @SerializedName("response") val response: String,
    @SerializedName("tts_audio_url") val ttsAudioUrl: String?
)

data class ProjectAnalytics(
    @SerializedName("project_id") val projectId: Int,
    @SerializedName("total_sessions") val totalSessions: Int,
    @SerializedName("total_duration_seconds") val totalDurationSeconds: Int,
    @SerializedName("avg_session_duration_seconds") val avgSessionDurationSeconds: Double,
    @SerializedName("unique_users") val uniqueUsers: Int,
    @SerializedName("events_by_type") val eventsByType: Map<String, Int>,
    @SerializedName("completion_rate") val completionRate: Double
)

data class SessionAnalytics(
    @SerializedName("session_id") val sessionId: Int,
    @SerializedName("duration_seconds") val durationSeconds: Int,
    @SerializedName("events_count") val eventsCount: Int,
    @SerializedName("events_by_type") val eventsByType: Map<String, Int>,
    @SerializedName("navigation_path") val navigationPath: List<String>,
    @SerializedName("copilot_interactions") val copilotInteractions: Int,
    @SerializedName("voice_interactions") val voiceInteractions: Int
)

data class CreditBalance(
    @SerializedName("balance") val balance: Int,
    @SerializedName("currency") val currency: String = "credits"
)

data class CreditUsageList(
    val usage: List<CreditLedgerResponse>
)

data class CreditLedgerResponse(
    @SerializedName("id") val id: Int,
    @SerializedName("organization_id") val organizationId: Int,
    @SerializedName("event_type") val eventType: String,
    @SerializedName("amount") val amount: Int,
    @SerializedName("reference_id") val referenceId: Int?,
    @SerializedName("reference_type") val referenceType: String?,
    @SerializedName("created_at") val createdAt: String
)

data class EditOperation(
    @SerializedName("operation") val operation: String,
    @SerializedName("entity_id") val entityId: String,
    @SerializedName("params") val params: Map<String, Any> = emptyMap()
)

data class EditRequest(
    @SerializedName("operations") val operations: List<EditOperation>
)

data class EditResponse(
    @SerializedName("success") val success: Boolean,
    @SerializedName("message") val message: String,
    @SerializedName("spec_id") val specId: Int? = null,
    @SerializedName("new_version") val newVersion: Int? = null
)
