package com.cymatic.client.render

import org.junit.Assert.*
import org.junit.Test

class WavUtilTest {

    @Test
    fun `wrap produces valid 44-byte header`() {
        val wav = WavUtil.wrapPcmAsWav(ByteArray(4))
        assertEquals(48, wav.size)
        val h = WavUtil.parseHeader(wav)!!
        assertEquals("RIFF", h.riff)
        assertEquals("WAVE", h.wave)
        assertEquals(1, h.channels)
        assertEquals(16000, h.sampleRateHz)
        assertEquals(16, h.bitsPerSample)
        assertEquals(4, h.dataBytes)
    }

    @Test
    fun `pcm payload round-trips`() {
        val pcm = byteArrayOf(1, 2, 3, 4, 5, 6)
        val wav = WavUtil.wrapPcmAsWav(pcm)
        assertArrayEquals(pcm, wav.copyOfRange(WavUtil.HEADER_BYTES, wav.size))
    }

    @Test
    fun `empty pcm still yields a valid header`() {
        val wav = WavUtil.wrapPcmAsWav(ByteArray(0))
        assertEquals(WavUtil.HEADER_BYTES, wav.size)
        assertEquals(0, WavUtil.parseHeader(wav)!!.dataBytes)
    }

    @Test
    fun `header byte rate matches 16kHz mono 16-bit`() {
        // byteRate at offset 28, little-endian: 16000*1*2 = 32000.
        val wav = WavUtil.wrapPcmAsWav(ByteArray(0))
        val byteRate = (wav[28].toInt() and 0xFF) or ((wav[29].toInt() and 0xFF) shl 8)
        assertEquals(32000, byteRate)
    }
}
