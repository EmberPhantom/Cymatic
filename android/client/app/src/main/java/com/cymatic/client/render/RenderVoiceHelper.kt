package com.cymatic.client.render

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import com.cymatic.client.network.ApiClient
import com.cymatic.client.voice.VoiceManager
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody

/**
 * Push-to-talk for the native renderer: records 16 kHz mono PCM while held,
 * posts it to `voice/audio`, plays the spoken reply. Reuses VoiceManager
 * only for TTS playback (its capture pipeline targets the stream endpoint).
 */
class RenderVoiceHelper(private val context: Context) {

    private val tts = VoiceManager(context)
    private var recorder: AudioRecord? = null
    private var recording = false
    private val pcm = mutableListOf<ByteArray>()

    data class Reply(val transcript: String, val response: String)

    fun startTalk() {
        if (recording) return
        pcm.clear()
        val minBuf = AudioRecord.getMinBufferSize(
            16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        ).coerceAtLeast(2048)
        recorder = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            16000, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT,
            minBuf * 2
        )
        try {
            recorder?.startRecording()
            recording = true
            Thread {
                val buf = ByteArray(minBuf)
                while (recording) {
                    val n = try {
                        recorder?.read(buf, 0, buf.size) ?: 0
                    } catch (e: Exception) {
                        0
                    }
                    if (n > 0) synchronized(pcm) { pcm.add(buf.copyOf(n)) }
                }
            }.also { it.isDaemon = true; it.start() }
        } catch (e: Exception) {
            recording = false
        }
    }

    suspend fun stopTalk(sessionId: Int, language: String = "en"): Reply? {
        recording = false
        try { recorder?.stop() } catch (e: Exception) { }
        try { recorder?.release() } catch (e: Exception) { }
        recorder = null
        val bytes = synchronized(pcm) {
            val total = pcm.sumOf { it.size }
            val out = ByteArray(total)
            var off = 0
            for (b in pcm) {
                System.arraycopy(b, 0, out, off, b.size)
                off += b.size
            }
            pcm.clear()
            out
        }
        if (bytes.size < 3200) return null // <0.1 s: accidental tap
        return withContext(Dispatchers.IO) {
            val part = MultipartBody.Part.createFormData(
                "audio", "ptt.wav", bytes.toRequestBody("audio/wav".toMediaType())
            )
            val lang = language.toRequestBody("text/plain".toMediaType())
            val resp = ApiClient.apiService.renderVoiceAudio(sessionId, part, lang)
            val body = if (resp.isSuccessful) resp.body() else null
                ?: return@withContext null
            body.audioData?.let { tts.playTTS(it) }
            Reply(body.transcript, body.response)
        }
    }

    fun dispose() {
        recording = false
        try { recorder?.release() } catch (e: Exception) { }
        recorder = null
    }
}
