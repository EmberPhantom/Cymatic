package com.cymatic.client.render

/**
 * Minimal WAV framing for 16-bit PCM push-to-talk uploads.
 *
 * The backend `POST /v1/render/sessions/{id}/voice/audio` takes multipart
 * audio bytes; the old client sent raw headerless PCM with an `audio/wav`
 * content type, which is not a valid WAV file. This helper prepends a
 * standard 44-byte RIFF header (PCM, mono, 16 kHz default matching the
 * AudioRecord sites). Pure byte math — JVM unit-tested.
 */
object WavUtil {

    const val SAMPLE_RATE_HZ = 16000
    const val CHANNELS_MONO = 1
    const val BITS_PER_SAMPLE_16 = 16
    const val HEADER_BYTES = 44

    /**
     * Wrap little-endian PCM bytes in a WAV container. [pcm] must already be
     * [bitsPerSample]-bit samples at [sampleRateHz]/[channels].
     */
    fun wrapPcmAsWav(
        pcm: ByteArray,
        sampleRateHz: Int = SAMPLE_RATE_HZ,
        channels: Int = CHANNELS_MONO,
        bitsPerSample: Int = BITS_PER_SAMPLE_16
    ): ByteArray {
        require(sampleRateHz > 0) { "sampleRateHz must be positive" }
        require(channels in 1..8) { "channels out of range" }
        require(bitsPerSample == 8 || bitsPerSample == 16 || bitsPerSample == 24 || bitsPerSample == 32) {
            "only 8/16/24/32-bit PCM supported"
        }
        val out = ByteArray(HEADER_BYTES + pcm.size)
        val byteRate = sampleRateHz * channels * bitsPerSample / 8
        val blockAlign = (channels * bitsPerSample / 8).toShort()

        fun ascii4(off: Int, s: String) {
            require(s.length == 4)
            for (i in 0 until 4) out[off + i] = s[i].code.toByte()
        }
        fun le16(off: Int, v: Int) {
            out[off] = (v and 0xFF).toByte()
            out[off + 1] = ((v ushr 8) and 0xFF).toByte()
        }
        fun le32(off: Int, v: Int) {
            out[off] = (v and 0xFF).toByte()
            out[off + 1] = ((v ushr 8) and 0xFF).toByte()
            out[off + 2] = ((v ushr 16) and 0xFF).toByte()
            out[off + 3] = ((v ushr 24) and 0xFF).toByte()
        }

        ascii4(0, "RIFF")
        le32(4, 36 + pcm.size) // chunk size = 36 + data bytes
        ascii4(8, "WAVE")
        ascii4(12, "fmt ")
        le32(16, 16) // PCM fmt chunk size
        le16(20, 1) // audio format = PCM
        le16(22, channels)
        le32(24, sampleRateHz)
        le32(28, byteRate)
        le16(32, blockAlign.toInt())
        le16(34, bitsPerSample)
        ascii4(36, "data")
        le32(40, pcm.size)
        System.arraycopy(pcm, 0, out, HEADER_BYTES, pcm.size)
        return out
    }

    /** Parse back the header fields (for tests / validation). */
    data class Header(
        val riff: String,
        val wave: String,
        val channels: Int,
        val sampleRateHz: Int,
        val bitsPerSample: Int,
        val dataBytes: Int
    )

    fun parseHeader(wav: ByteArray): Header? {
        if (wav.size < HEADER_BYTES) return null
        fun ascii4(off: Int) = String(byteArrayOf(wav[off], wav[off + 1], wav[off + 2], wav[off + 3]), Charsets.US_ASCII)
        fun le16(off: Int) = (wav[off].toInt() and 0xFF) or ((wav[off + 1].toInt() and 0xFF) shl 8)
        fun le32(off: Int) = (wav[off].toInt() and 0xFF) or
            ((wav[off + 1].toInt() and 0xFF) shl 8) or
            ((wav[off + 2].toInt() and 0xFF) shl 16) or
            ((wav[off + 3].toInt() and 0xFF) shl 24)
        if (ascii4(0) != "RIFF" || ascii4(8) != "WAVE" || ascii4(12) != "fmt " || ascii4(36) != "data") return null
        if (le16(20) != 1) return null
        return Header(
            riff = ascii4(0),
            wave = ascii4(8),
            channels = le16(22),
            sampleRateHz = le32(24),
            bitsPerSample = le16(34),
            dataBytes = le32(40)
        )
    }
}
