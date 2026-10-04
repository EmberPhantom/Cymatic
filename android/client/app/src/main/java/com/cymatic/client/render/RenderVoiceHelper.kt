package com.cymatic.client.render

import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Log
import androidx.core.content.ContextCompat
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
    private var recordThread: Thread? = null
    private val pcm = mutableListOf<ByteArray>()

    data class Reply(val transcript: String, val response: String)

    /**
     * Starts push-to-talk capture (16 kHz mono PCM, matching [WavUtil]).
     * Returns false (and captures nothing) when RECORD_AUDIO is not granted.
     */
    fun startTalk(): Boolean {
        if (recording) return true
        if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.RECORD_AUDIO) != PackageManager.PERMISSION_GRANTED) {
            Log.w("RenderVoice", "RECORD_AUDIO not granted, PTT ignored")
            return false
        }
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
            val thread = Thread {
                val buf = ByteArray(minBuf)
                while (recording) {
                    val n = try {
                        recorder?.read(buf, 0, buf.size) ?: 0
                    } catch (e: Exception) {
                        0
                    }
                    if (n > 0) synchronized(pcm) { pcm.add(buf.copyOf(n)) }
                }
            }
            thread.isDaemon = true
            thread.start()
            recordThread = thread
            return true
        } catch (e: Exception) {
            recording = false
            return false
        }
    }

    suspend fun stopTalk(sessionId: Int, language: String = "en"): Reply? {
        recording = false
        // Join the recorder thread BEFORE draining pcm: otherwise the tail of
        // the utterance races with the upload assembly and gets truncated.
        try { recordThread?.join(500) } catch (e: Exception) { }
        recordThread = null
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
        // Frame as a valid WAV (16 kHz mono 16-bit, matching capture above);
        // the backend voice/audio endpoint parses the container, not raw PCM.
        val wav = WavUtil.wrapPcmAsWav(bytes)
        return withContext(Dispatchers.IO) {
            val part = MultipartBody.Part.createFormData(
                "audio", "ptt.wav", wav.toRequestBody("audio/wav".toMediaType())
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
        try { recordThread?.join(300) } catch (e: Exception) { }
        recordThread = null
        try { recorder?.release() } catch (e: Exception) { }
        recorder = null
    }
}
