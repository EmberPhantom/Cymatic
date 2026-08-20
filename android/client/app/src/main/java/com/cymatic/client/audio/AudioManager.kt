package com.cymatic.client.audio

import android.content.Context
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioTrack
import android.media.MediaCodec
import android.media.MediaFormat
import android.util.Log
import kotlinx.coroutines.channels.Channel
import java.nio.ByteBuffer

class AudioManager(private val context: Context) {

    private var audioTrack: AudioTrack? = null
    private var audioDecoder: MediaCodec? = null
    private var isPlaying = false
    
    // Opus decoder (would use libopus in real implementation)
    private val sampleRate = 48000
    private val channelConfig = AudioFormat.CHANNEL_OUT_STEREO
    private val audioFormat = AudioFormat.ENCODING_PCM_16BIT
    
    // Buffer
    private val bufferSize = AudioTrack.getMinBufferSize(
        sampleRate,
        channelConfig,
        audioFormat
    ) * 4
    
    // Audio focus
    private val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
    private val focusRequest = android.media.AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT)
        .setAudioAttributes(
            AudioAttributes.Builder()
                .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                .setFlags(AudioAttributes.FLAG_HW_AV_SYNC)
                .build()
        )
        .setOnAudioFocusChangeListener { focusChange ->
            when (focusChange) {
                AudioManager.AUDIOFOCUS_LOSS -> pause()
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT -> pause()
                AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> {
                    // Lower volume
                }
                AudioManager.AUDIOFOCUS_GAIN -> resume()
            }
        }
        .build()
    
    // Jitter buffer
    private val jitterBuffer = Channel<ByteArray>(50)
    private val playbackExecutor = java.util.concurrent.Executors.newSingleThreadExecutor()
    
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
        audioTrack = AudioTrack.Builder()
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .setFlags(AudioAttributes.FLAG_HW_AV_SYNC)
                    .build()
            )
            .setAudioFormat(
                AudioFormat.Builder()
                    .setSampleRate(sampleRate)
                    .setEncoding(audioFormat)
                    .setChannelMask(channelConfig)
                    .build()
            )
            .setBufferSizeInBytes(bufferSize)
            .setTransferMode(AudioTrack.MODE_STREAM)
            .build()
        
        audioTrack?.play()
    }
    
    private fun startPlayback() {
        playbackExecutor.execute {
            while (isPlaying) {
                val data = jitterBuffer.receiveOrNull()
                if (data != null && audioTrack != null) {
                    audioTrack.write(data, 0, data.size, AudioTrack.WRITE_BLOCKING)
                }
            }
        }
    }
    
    fun enqueueAudioData(data: ByteArray) {
        if (isPlaying) {
            jitterBuffer.trySend(data.copyOf())
        }
    }
    
    fun pause() {
        audioTrack?.pause()
    }
    
    fun resume() {
        audioTrack?.play()
    }
    
    fun stop() {
        isPlaying = false
        audioTrack?.stop()
        audioTrack?.release()
        audioTrack = null
        
        audioDecoder?.stop()
        audioDecoder?.release()
        audioDecoder = null
        
        audioManager.abandonAudioFocusRequest(focusRequest)
        jitterBuffer.close()
        playbackExecutor.shutdown()
    }
    
    fun setVolume(volume: Float) {
        audioTrack?.setVolume(volume.coerceIn(0f, 1f))
    }
    
    // For Opus decoding (would integrate libopus)
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
        stop()
        jitterBuffer.close()
        playbackExecutor.shutdownNow()
    }
}