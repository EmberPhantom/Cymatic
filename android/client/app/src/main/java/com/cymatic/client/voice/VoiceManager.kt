package com.cymatic.client.voice

import android.content.Context
import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.util.Base64
import android.util.Log
import com.cymatic.client.network.ApiClient
import com.cymatic.client.network.model.VoiceTranscript
import com.cymatic.client.network.model.VoiceResponse
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlin.math.abs

class VoiceManager(private val context: Context) {

    private var audioRecord: AudioRecord? = null
    @Volatile private var isRecording = false
    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    private val bufferSize = AudioRecord.getMinBufferSize(
        sampleRate,
        channelConfig,
        audioFormat
    ).coerceAtLeast(2048) * 2
    
    private var audioChannel = Channel<ByteArray>(10)
    private val scope = CoroutineScope(Dispatchers.IO)
    private var captureJob: Job? = null

    // Batching state — fixes per-chunk STT 15 req/s (was sending every 20-30ms chunk)
    private val pcmAccumulator = mutableListOf<ByteArray>()
    private var accumulatedBytes = 0
    private var lastSttSendMs = 0L
    private var isSttInFlight = false
    // ~0.8s of PCM at 16k mono 16bit = 25600 bytes; batch to ~0.8s + throttle 900ms => ~1.1 req/s max
    private val STT_BATCH_BYTES = 25600
    private val STT_MIN_INTERVAL_MS = 900L
    private val STT_VAD_THRESHOLD_RMS = 400 // ~ amplitude threshold for voice activity
    private val STT_MAX_ACCUM_BYTES = STT_BATCH_BYTES * 3 // guard overflow

    // Callbacks
    private var onTranscript: ((String) -> Unit)? = null
    private var onResponse: ((VoiceResponse) -> Unit)? = null
    private var onError: ((String) -> Unit)? = null
    
    fun setCallbacks(
        onTranscript: ((String) -> Unit)? = null,
        onResponse: ((VoiceResponse) -> Unit)? = null,
        onError: ((String) -> Unit)? = null
    ) {
        this.onTranscript = onTranscript
        this.onResponse = onResponse
        this.onError = onError
    }
    
    fun startRecording() {
        if (isRecording) return
        if (audioChannel.isClosedForSend) audioChannel = Channel(10)
        isRecording = true
        accumulatedBytes = 0
        pcmAccumulator.clear()
        lastSttSendMs = 0L

        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            sampleRate,
            channelConfig,
            audioFormat,
            bufferSize
        )
        
        try { audioRecord?.startRecording() } catch (e: Exception) {
            Log.e("VoiceManager", "startRecording failed", e)
            isRecording = false
            return
        }
        
        captureJob = scope.launch {
            val buffer = ByteArray(bufferSize)
            while (isRecording) {
                val read = try { audioRecord?.read(buffer, 0, buffer.size) ?: 0 } catch (_: Exception) { 0 }
                if (read > 0) {
                    val data = buffer.copyOfRange(0, read)
                    // Keep channel bounded
                    val res = audioChannel.trySend(data)
                    if (!res.isSuccess) {
                        audioChannel.tryReceive().getOrNull()
                        audioChannel.trySend(data)
                    }
                    // Batch instead of per-chunk STT
                    enqueueForStt(data)
                } else {
                    delay(10)
                }
            }
        }
    }
    
    fun stopRecording() {
        if (!isRecording) return
        isRecording = false
        captureJob?.cancel()
        captureJob = null
        try { audioRecord?.stop() } catch (_: Exception) {}
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null
        // Flush remaining accumulator if voice-active
        scope.launch {
            flushSttAccumulator(force = true)
        }
    }

    private fun enqueueForStt(chunk: ByteArray) {
        pcmAccumulator.add(chunk)
        accumulatedBytes += chunk.size
        if (accumulatedBytes >= STT_BATCH_BYTES) {
            val now = System.currentTimeMillis()
            if (now - lastSttSendMs >= STT_MIN_INTERVAL_MS && !isSttInFlight) {
                // VAD guard — skip sending silence to save ~5% thermal/CPU + network
                if (isVoiceActive(pcmAccumulator)) {
                    val batch = concatAccumulator()
                    sendBatchedToStt(batch, now)
                } else {
                    // Silence: drop batch silently
                    pcmAccumulator.clear()
                    accumulatedBytes = 0
                    lastSttSendMs = now
                }
            }
        }
        // Overflow guard: drop oldest batches if we accumulate too much while throttled
        if (accumulatedBytes > STT_MAX_ACCUM_BYTES) {
            // Drop oldest third
            var dropped = 0
            while (pcmAccumulator.isNotEmpty() && dropped < STT_BATCH_BYTES) {
                val b = pcmAccumulator.removeAt(0)
                dropped += b.size
                accumulatedBytes -= b.size
            }
        }
    }

    private fun concatAccumulator(): ByteArray {
        val out = ByteArray(accumulatedBytes)
        var off = 0
        for (b in pcmAccumulator) {
            System.arraycopy(b, 0, out, off, b.size)
            off += b.size
        }
        pcmAccumulator.clear()
        accumulatedBytes = 0
        return out
    }

    private suspend fun flushSttAccumulator(force: Boolean) {
        if (pcmAccumulator.isEmpty()) return
        val now = System.currentTimeMillis()
        if (!force && isVoiceActive(pcmAccumulator).not()) {
            pcmAccumulator.clear(); accumulatedBytes = 0; return
        }
        if (now - lastSttSendMs < STT_MIN_INTERVAL_MS && !force) return
        // Require at least ~300ms of audio to avoid tiny requests
        if (!force && accumulatedBytes < 9600) return
        if (!isVoiceActive(pcmAccumulator)) {
            pcmAccumulator.clear(); accumulatedBytes = 0; return
        }
        val batch = concatAccumulator()
        sendBatchedToStt(batch, now)
    }

    private fun isVoiceActive(buffers: List<ByteArray>): Boolean {
        // Simple RMS VAD — sufficient for PTT without heavy lib
        var sumSq = 0L
        var samples = 0
        for (buf in buffers) {
            // 16-bit PCM little-endian
            var i = 0
            while (i + 1 < buf.size) {
                val s = ((buf[i+1].toInt() shl 8) or (buf[i].toInt() and 0xFF)).toShort().toInt()
                sumSq += (s * s).toLong()
                samples++
                i += 2
                if (samples >= 1600) break // enough for estimate
            }
            if (samples >= 1600) break
        }
        if (samples == 0) return false
        val rms = kotlin.math.sqrt(sumSq.toDouble() / samples)
        return rms >= STT_VAD_THRESHOLD_RMS
    }
    
    private fun sendBatchedToStt(pcmBatch: ByteArray, nowMs: Long) {
        if (isSttInFlight) return
        isSttInFlight = true
        lastSttSendMs = nowMs
        scope.launch {
            try {
                val base64Audio = Base64.encodeToString(pcmBatch, Base64.NO_WRAP)
                
                val request = VoiceTranscript(
                    transcript = base64Audio,
                    language = "en",
                    confidence = null
                )
                
                val response = ApiClient.apiService.voiceTranscript(
                    sessionId = "", // Would come from current session
                    request
                )
                
                if (response.isSuccessful) {
                    val voiceResponse = response.body()!!
                    onTranscript?.invoke(voiceResponse.response)
                    onResponse?.invoke(voiceResponse)
                } else {
                    onError?.invoke("STT failed: ${response.message()}")
                }
            } catch (e: Exception) {
                Log.e("VoiceManager", "STT error", e)
                onError?.invoke("Voice processing error: ${e.message}")
            } finally {
                isSttInFlight = false
            }
        }
    }

    // Kept for compatibility but now routes through batching
    private fun sendToSTT(audioData: ByteArray) {
        enqueueForStt(audioData)
    }
    
    fun playTTS(audioBase64: String) {
        scope.launch {
            var track: android.media.AudioTrack? = null
            try {
                val audioBytes = Base64.decode(audioBase64, Base64.NO_WRAP)
                
                track = android.media.AudioTrack.Builder()
                    .setAudioAttributes(
                        android.media.AudioAttributes.Builder()
                            .setUsage(android.media.AudioAttributes.USAGE_VOICE_COMMUNICATION)
                            .setContentType(android.media.AudioAttributes.CONTENT_TYPE_SPEECH)
                            .build()
                    )
                    .setAudioFormat(
                        android.media.AudioFormat.Builder()
                            .setSampleRate(16000)
                            .setEncoding(android.media.AudioFormat.ENCODING_PCM_16BIT)
                            .setChannelMask(android.media.AudioFormat.CHANNEL_OUT_MONO)
                            .build()
                    )
                    .setBufferSizeInBytes(maxOf(audioBytes.size, AudioTrack.getMinBufferSize(16000, AudioFormat.CHANNEL_OUT_MONO, AudioFormat.ENCODING_PCM_16BIT)))
                    .setTransferMode(android.media.AudioTrack.MODE_STATIC)
                    .build()
                
                track.write(audioBytes, 0, audioBytes.size)
                track.play()
                
                while (track.playState == android.media.AudioTrack.PLAYSTATE_PLAYING) {
                    delay(50)
                }
            } catch (e: Exception) {
                Log.e("VoiceManager", "TTS playback error", e)
            } finally {
                try { track?.stop() } catch (_: Exception) {}
                try { track?.release() } catch (_: Exception) {}
            }
        }
    }
    
    fun setOnTranscript(listener: (String) -> Unit) {
        onTranscript = listener
    }
    
    fun setOnResponse(listener: (VoiceResponse) -> Unit) {
        onResponse = listener
    }
    
    fun setOnError(listener: (String) -> Unit) {
        onError = listener
    }
    
    fun dispose() {
        stopRecording()
        try { if (!audioChannel.isClosedForSend) audioChannel.close() } catch (_: Exception) {}
    }
}
