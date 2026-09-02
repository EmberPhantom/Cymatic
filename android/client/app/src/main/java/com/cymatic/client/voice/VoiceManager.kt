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
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import java.nio.ByteBuffer

class VoiceManager(private val context: Context) {

    private var audioRecord: AudioRecord? = null
    private var isRecording = false
    private val sampleRate = 16000
    private val channelConfig = AudioFormat.CHANNEL_IN_MONO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    private val bufferSize = AudioRecord.getMinBufferSize(
        sampleRate,
        channelConfig,
        audioFormat
    ) * 2
    
    private var audioChannel = Channel<ByteArray>(100)
    private val scope = CoroutineScope(Dispatchers.IO)
    
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
        if (audioChannel.isClosedForSend) audioChannel = Channel(100)
        isRecording = true
        
        audioRecord = AudioRecord(
            MediaRecorder.AudioSource.VOICE_COMMUNICATION,
            sampleRate,
            channelConfig,
            audioFormat,
            bufferSize
        )
        
        audioRecord?.startRecording()
        
        scope.launch {
            while (isRecording) {
                val buffer = ByteArray(bufferSize)
                val read = audioRecord?.read(buffer, 0, buffer.size) ?: 0
                if (read > 0) {
                    val data = buffer.copyOfRange(0, read)
                    audioChannel.trySend(data)
                    
                    // Also send to STT
                    sendToSTT(data)
                }
            }
        }
    }
    
    fun stopRecording() {
        isRecording = false
        try { audioRecord?.stop() } catch (_: Exception) {}
        try { audioRecord?.release() } catch (_: Exception) {}
        audioRecord = null
        // keep channel open for next recording, drain only
        scope.launch { try { audioChannel.tryReceive().getOrNull() } catch (_: Exception) {} }
    }
    
    private fun sendToSTT(audioData: ByteArray) {
        scope.launch {
            try {
                val base64Audio = Base64.encodeToString(audioData, Base64.NO_WRAP)
                
                val request = VoiceTranscript(
                    transcript = base64Audio, // In real impl, send raw audio
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
            }
        }
    }
    
    fun playTTS(audioBase64: String) {
        scope.launch {
            try {
                val audioBytes = Base64.decode(audioBase64, Base64.NO_WRAP)
                
                val track = android.media.AudioTrack.Builder()
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
                
                // Wait for playback to finish
                while (track.playState == android.media.AudioTrack.PLAYSTATE_PLAYING) {
                    kotlinx.coroutines.delay(100)
                }
                
                track.release()
            } catch (e: Exception) {
                Log.e("VoiceManager", "TTS playback error", e)
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
    }
}