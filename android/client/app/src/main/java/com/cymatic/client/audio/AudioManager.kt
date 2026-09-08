package com.cymatic.client.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.media.MediaCodec
import android.media.MediaFormat
import android.os.Build
import android.util.Log
import kotlinx.coroutines.channels.Channel

class AudioManager(private val context: Context) {

    private var audioTrack: AudioTrack? = null
    private var audioDecoder: MediaCodec? = null
    @Volatile private var isPlaying = false
    
    private val sampleRate = 48000
    private val channelConfig = AudioFormat.CHANNEL_OUT_STEREO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    
    // Reduced buffer: *2 vs *4 halves latency and memory for low-end (≈30ms vs 60ms)
    private val bufferSize = AudioTrack.getMinBufferSize(
        sampleRate,
        channelConfig,
        audioFormat
    ).coerceAtLeast(4096) * 2
    
    // Audio focus
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val focusRequest = android.media.AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .build()
        )
        .setOnAudioFocusChangeListener { focusChange ->
            when (focusChange) {
                AudioManager.AUDIOFOCUS_LOSS -> pause()
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> pause()
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> { /* lower volume not needed for voice */ }
                AudioManager.AUDIOFOCUS_GAIN -> resume()
            }
        }
        .build()
    
    // Jitter buffer — small bounded (10) to cap latency; adaptive sleep reduces wakeups
    private val jitterBuffer = Channel<ByteArray>(10)
    private val playbackExecutor = java.util.concurrent.Executors.newSingleThreadExecutor()
    @Volatile private var playbackStarted = false
    
    fun start() {
        if (isPlaying) return
        
        requestAudioFocus()
        createAudioTrack()
        isPlaying = true
        startPlayback()
    }
    
    private fun requestAudioFocus() {
        val result = audioManager.requestAudioFocus(focusRequest)
        if (result != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            Log.w("AudioManager", "Audio focus not granted")
        }
    }
    
    private fun createAudioTrack() {
        val attrs = AudioAttributes.Builder()
            .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
            .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
            .build()
        val fmt = AudioFormat.Builder()
            .setSampleRate(sampleRate)
            .setEncoding(audioFormat)
            .setChannelMask(channelConfig)
            .build()
        audioTrack = AudioTrack.Builder()
            .setAudioAttributes(attrs)
            .setAudioFormat(fmt)
            .setBufferSizeInBytes(bufferSize)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .apply {
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    setPerformanceMode(AudioTrack.PERFORMANCE_MODE_LOW_LATENCY)
                }
            }
            .build()
        
        audioTrack?.play()
    }
    
    private fun startPlayback() {
        if (playbackStarted) return
        playbackStarted = true
        playbackExecutor.execute {
            // Adaptive jitter: target 2 buffered packets (~40ms) — sleep longer when empty to save CPU/thermal
            var emptyStreak = 0
            while (isPlaying) {
                val data = jitterBuffer.tryReceive().getOrNull()
                if (data != null && audioTrack != null) {
                    emptyStreak = 0
                    try {
                        audioTrack?.write(data, 0, data.size, AudioTrack.WRITE_BLOCKING)
                    } catch (e: Exception) {
                        Log.w("AudioManager", "write failed", e)
                    }
                } else {
                    emptyStreak++
                    // Backoff: 10ms base, 20ms when starved to halve wakeups (100/s vs 200/s)
                    val sleepMs = if (emptyStreak > 5) 20L else 10L
                    try { Thread.sleep(sleepMs) } catch (_: InterruptedException) { break }
                }
            }
            playbackStarted = false
        }
    }
    
    fun enqueueAudioData(data: ByteArray) {
        if (!isPlaying) return
        // Bounded drop-oldest to keep latency low on low-end (never grow to 50)
        val result = jitterBuffer.trySend(data.copyOf())
        if (!result.isSuccess) {
            // Drop oldest and retry once
            jitterBuffer.tryReceive().getOrNull()
            jitterBuffer.trySend(data.copyOf())
        }
    }
    
    fun pause() {
        try { audioTrack?.pause() } catch (_: Exception) {}
    }
    
    fun resume() {
        try { audioTrack?.play() } catch (_: Exception) {}
    }
    
    fun stop() {
        isPlaying = false
        try { audioTrack?.stop() } catch (_: Exception) {}
        try { audioTrack?.release() } catch (_: Exception) {}
        audioTrack = null
        try { audioDecoder?.stop() } catch (_: Exception) {}
        try { audioDecoder?.release() } catch (_: Exception) {}
        audioDecoder = null
        try { audioManager.abandonAudioFocusRequest(focusRequest) } catch (_: Exception) {}
        // Do not close channel here — keep reusable; close only in dispose()
    }
    
    fun setVolume(volume: Float) {
        audioTrack?.setVolume(volume.coerceIn(0f, 1f))
    }
    
    private fun setupOpusDecoder() {
        try {
            val format = MediaFormat.createAudioFormat(MediaFormat.MIMETYPE_AUDIO_OPUS, sampleRate, 2)
            audioDecoder = MediaCodec.createDecoderByType(MediaFormat.MIMETYPE_AUDIO_OPUS)
            audioDecoder?.configure(format, null, null, 0)
            audioDecoder?.start()
        } catch (e: Exception) {
            Log.e("AudioManager", "Failed to create Opus decoder", e)
        }
    }
    
    fun dispose() {
        isPlaying = false
        try { stop() } catch (_: Exception) {}
        try { if (!jitterBuffer.isClosedForSend) jitterBuffer.close() } catch (_: Exception) {}
        try { playbackExecutor.shutdownNow() } catch (_: Exception) {}
    }
}
