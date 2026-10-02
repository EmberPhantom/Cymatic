package com.cymatic.client.webrtc

import android.content.Context
import android.util.Log
import com.cymatic.client.input.InputManager
import com.cymatic.client.network.model.InputPacket
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import org.webrtc.*
import java.util.concurrent.Executors

class WebRTCManager(private val context: Context, private val eglBase: EglBase) {

    private val scope = CoroutineScope(Dispatchers.IO)
    private val factory: PeerConnectionFactory
    private var peerConnection: PeerConnection? = null
    private var audioTrack: AudioTrack? = null
    private var audioSource: AudioSource? = null
    private val cachedInputManager = InputManager()
    
    private var signalingClient: SignalingClient? = null
    private var currentSessionId: String? = null
    
    // Bitrate delta state (285)
    private var lastBytesReceived = -1L
    private var lastBitrateCalcTimeMs = 0L
    private var lastBitrateKbps = 0

    // Audio send throttling (233) — avoid log spam per 20ms chunk
    private var audioSendCount = 0
    private var lastAudioLogMs = 0L
    
    // Callbacks
    private var onConnected: ((String) -> Unit)? = null
    private var onDisconnected: ((String) -> Unit)? = null
    private var onError: ((String) -> Unit)? = null
    private var onStats: ((StreamStats) -> Unit)? = null
    private var onRemoteVideoFrame: ((VideoFrame) -> Unit)? = null
    
    // Stats
    private val statsExecutor = Executors.newSingleThreadScheduledExecutor()
    private var statsJob: java.util.concurrent.ScheduledFuture<*>? = null
    
    // Input channel — bounded to avoid backpressure on low-end
    private val inputChannel = Channel<InputPacket>(10)
    
    init {
        // Initialize WebRTC — tracer disabled for perf
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context)
                .setEnableInternalTracer(false)
                .createInitializationOptions()
        )
        
        val options = PeerConnectionFactory.Options()
        options.networkIgnoreMask = 0
        
        factory = PeerConnectionFactory.builder()
            .setOptions(options)
            .createPeerConnectionFactory()
    }
    
    fun setCallbacks(
        onConnected: ((String) -> Unit)? = null,
        onDisconnected: ((String) -> Unit)? = null,
        onError: ((String) -> Unit)? = null,
        onStats: ((StreamStats) -> Unit)? = null,
        onRemoteVideoFrame: ((VideoFrame) -> Unit)? = null
    ) {
        this.onConnected = onConnected
        this.onDisconnected = onDisconnected
        this.onError = onError
        this.onStats = onStats
        this.onRemoteVideoFrame = onRemoteVideoFrame
    }
    
    fun connect(signalingUrl: String, sessionId: String, authToken: String? = null) {
        currentSessionId = sessionId
        lastBytesReceived = -1L
        lastBitrateCalcTimeMs = 0L
        lastBitrateKbps = 0

        // Backend expects client type via query (?type=android) and JWT via
        // Authorization header (query ?token= deprecated, leaks in logs).
        val urlWithType = if (signalingUrl.contains("type=")) signalingUrl
            else if (signalingUrl.contains("?")) "$signalingUrl&type=android"
            else "$signalingUrl?type=android"

        // Create peer connection
        createPeerConnection()

        // Connect signaling
        signalingClient = SignalingClient(urlWithType, { currentSessionId }, onError, authTokenProvider = { authToken })
        signalingClient?.setCallbacks(
            onOffer = { sdp ->
                handleOffer(sdp)
            },
            onAnswer = { sdp ->
                handleAnswer(sdp)
            },
            onCandidate = { candidate, sdpMid, sdpMLineIndex ->
                handleIceCandidate(candidate, sdpMid, sdpMLineIndex)
            },
            onInput = { input ->
                inputChannel.trySend(input)
            },
            onEndSession = {
                disconnect()
            },
            onConnected = { sid ->
                onConnected?.invoke(sid)
            },
            onDisconnected = { reason ->
                onDisconnected?.invoke(reason)
            }
        )
        
        signalingClient?.connect()
    }
    
    private fun createPeerConnection() {
        // 107 STUN LAN: Local LAN streaming should not require internet STUN (adds DNS + gathering delay).
        // For MVP over LAN, use no STUN; host candidates suffice. WAN fallback can add STUN via config.
        val configuration = PeerConnection.RTCConfiguration(emptyList<PeerConnection.IceServer>()).apply {
            iceServers = emptyList<PeerConnection.IceServer>()
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            bundlePolicy = PeerConnection.BundlePolicy.MAX_BUNDLE
            rtcpMuxPolicy = PeerConnection.RtcpMuxPolicy.REQUIRE
            // Prefer low latency: host candidates only via empty iceServers (LAN)
        }
        
        val constraints = MediaConstraints()
        constraints.mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
        constraints.mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "true"))
        
        peerConnection = factory.createPeerConnection(configuration, constraints, object : PeerConnection.Observer {
            override fun onIceCandidate(candidate: IceCandidate) {
                val sid = currentSessionId ?: return
                candidate.sdpMid?.let { mid ->
                    signalingClient?.sendIceCandidate(sid, candidate.sdp, mid, candidate.sdpMLineIndex)
                } ?: run {
                    Log.w("WebRTC", "IceCandidate sdpMid null, skipping")
                }
            }
            
            override fun onAddTrack(rtpReceiver: RtpReceiver, mediaStreams: Array<MediaStream>) {
                if (rtpReceiver.track()?.kind() == "video") {
                    rtpReceiver.track()?.addSink { frame ->
                        onRemoteVideoFrame?.invoke(frame)
                    }
                }
            }
            
            override fun onConnectionChange(newState: PeerConnection.PeerConnectionState) {
                when (newState) {
                    PeerConnection.PeerConnectionState.CONNECTED -> {
                        startStatsCollection()
                    }
                    PeerConnection.PeerConnectionState.DISCONNECTED,
                    PeerConnection.PeerConnectionState.FAILED,
                    PeerConnection.PeerConnectionState.CLOSED -> {
                        stopStatsCollection()
                        onDisconnected?.invoke("Connection state: $newState")
                    }
                    else -> {}
                }
            }
            override fun onIceCandidatesRemoved(candidates: Array<IceCandidate>) {}
            override fun onSignalingChange(newState: PeerConnection.SignalingState) {}
            override fun onIceConnectionChange(newState: PeerConnection.IceConnectionState) {}
            override fun onIceConnectionReceivingChange(receiving: Boolean) {}
            override fun onIceGatheringChange(newState: PeerConnection.IceGatheringState) {}
            override fun onAddStream(stream: MediaStream) {}
            override fun onRemoveStream(stream: MediaStream) {}
            override fun onDataChannel(channel: DataChannel) {}
            override fun onRenegotiationNeeded() {}
        })
        
        // Create audio track — mono for low-end (send only when PTT, not always)
        audioSource = factory.createAudioSource(MediaConstraints().apply {
            // Disable echo cancellation heavy processing on low-end? Keep but low cost
            mandatory.add(MediaConstraints.KeyValuePair("echoCancellation", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("noiseSuppression", "true"))
            mandatory.add(MediaConstraints.KeyValuePair("autoGainControl", "true"))
        })
        audioTrack = factory.createAudioTrack("audio", audioSource)
        // Do NOT add audio track until needed — 233 audio send: creating always wastes encoder/CPU.
        // Keep created but set enabled false to avoid sending silence.
        audioTrack?.setEnabled(false)
        audioTrack?.let { track -> peerConnection?.addTrack(track, listOf("stream")) }
    }
    
    private fun handleOffer(sdp: String) {
        val offer = SessionDescription(SessionDescription.Type.OFFER, sdp)
        peerConnection?.setRemoteDescription(object : SdpObserver {
            override fun onCreateSuccess(desc: SessionDescription?) {}
            override fun onSetSuccess() {
                createAnswer()
            }
            override fun onCreateFailure(error: String) {
                onError?.invoke("Create offer failed: $error")
            }
            override fun onSetFailure(error: String) {
                onError?.invoke("Set remote offer failed: $error")
            }
        }, offer)
    }
    
    private fun createAnswer() {
        val constraints = MediaConstraints()
        constraints.mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
        constraints.mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "true"))
        
        peerConnection?.createAnswer(object : SdpObserver {
            override fun onCreateSuccess(desc: SessionDescription?) {
                desc?.let { answer ->
                    peerConnection?.setLocalDescription(object : SdpObserver {
                        override fun onSetSuccess() {
                            currentSessionId?.let { sid -> signalingClient?.sendAnswer(sid, answer.description) }
                        }
                        override fun onSetFailure(error: String) {
                            onError?.invoke("Set local answer failed: $error")
                        }
                        override fun onCreateSuccess(desc: SessionDescription?) {}
                        override fun onCreateFailure(error: String) {}
                    }, answer)
                }
            }
            override fun onCreateFailure(error: String) {
                onError?.invoke("Create answer failed: $error")
            }
            override fun onSetSuccess() {}
            override fun onSetFailure(error: String) {}
        }, constraints)
    }
    
    private fun handleAnswer(sdp: String) {
        val answer = SessionDescription(SessionDescription.Type.ANSWER, sdp)
        peerConnection?.setRemoteDescription(object : SdpObserver {
            override fun onSetSuccess() {}
            override fun onSetFailure(error: String) {
                onError?.invoke("Set remote answer failed: $error")
            }
            override fun onCreateSuccess(desc: SessionDescription?) {}
            override fun onCreateFailure(error: String) {}
        }, answer)
    }
    
    private fun handleIceCandidate(candidate: String, sdpMid: String, sdpMLineIndex: Int) {
        val iceCandidate = IceCandidate(sdpMid, sdpMLineIndex, candidate)
        peerConnection?.addIceCandidate(iceCandidate)
    }
    
    fun sendHeadPose(position: FloatArray, rotation: FloatArray) {
        val input = InputManager.HeadPosePacket(
            timestamp = System.currentTimeMillis(),
            position = position,
            rotation = rotation
        )
        val packet = cachedInputManager.createInputPacket(input, FloatArray(3))
        signalingClient?.sendInput(packet)
    }

    fun sendControllerState(state: com.cymatic.client.input.ControllerManager.ControllerState) {
        val packet = cachedInputManager.createControllerPacket(state)
        signalingClient?.sendInput(packet)
    }
    
    fun sendAudioData(data: ByteArray) {
        // 233 audio send: previously logged per 20ms chunk (50 logs/s) and blocked with no throttling.
        // Now: enable track only when actually sending, throttle logs.
        audioTrack?.setEnabled(true)
        audioSendCount++
        val now = System.currentTimeMillis()
        if (now - lastAudioLogMs > 2000) {
            Log.d("WebRTC", "Audio send active: bytes=${data.size} chunks=$audioSendCount")
            lastAudioLogMs = now
            audioSendCount = 0
        }
        // Real impl: push to audioSource or data channel. For MVP, routing via signaling is avoided for perf;
        // keep cap to avoid flooding: coalesce or drop if backpressure.
        // Signaling path for voice is handled by VoiceManager batching, not per-chunk here.
    }

    fun notifyAudioStop() {
        audioTrack?.setEnabled(false)
    }
    
    fun sendInput(input: InputPacket) {
        inputChannel.trySend(input)
    }
    
    fun resume() {
        peerConnection?.let { /* resume */ }
        audioTrack?.setEnabled(false) // resume muted until PTT
    }
    
    fun pause() {
        peerConnection?.let { /* pause */ }
        audioTrack?.setEnabled(false)
    }
    
    fun disconnect() {
        stopStatsCollection()
        signalingClient?.disconnect()
        try { peerConnection?.close() } catch (_: Exception) {}
        peerConnection = null
        currentSessionId = null
        audioTrack?.setEnabled(false)
    }
    
    fun reduceQuality() {
        // Guard: getSenders may be empty if remote-only; check encodings size
        peerConnection?.getSenders()?.forEach { sender ->
            try {
                val params = sender.parameters
                if (params.encodings.isNotEmpty()) {
                    // 1.5 Mbps for thermal-low-end (was 5Mbps)
                    @Suppress("DEPRECATION")
                    params.encodings[0].maxBitrate = 1_500_000
                    params.encodings[0].scaleResolutionDownBy = 2.0
                    sender.parameters = params
                }
            } catch (e: Exception) {
                Log.w("WebRTC", "reduceQuality failed", e)
            }
        }
    }
    
    fun dispose() {
        disconnect()
        try { audioTrack?.dispose() } catch (_: Exception) {}
        try { audioSource?.dispose() } catch (_: Exception) {}
        try { factory.dispose() } catch (_: Exception) {}
        try { inputChannel.close() } catch (_: Exception) {}
        try { statsExecutor.shutdownNow() } catch (_: Exception) {}
    }
    
    private fun startStatsCollection() {
        // Throttle to 2s vs 1s to halve CPU on low-end
        if (statsJob != null) return
        lastBytesReceived = -1L
        lastBitrateCalcTimeMs = System.currentTimeMillis()
        statsJob = statsExecutor.scheduleAtFixedRate({
            try {
                peerConnection?.getStats { report ->
                    val stats = parseStatsNew(report)
                    onStats?.invoke(stats)
                }
            } catch (_: Exception) {
                try {
                    @Suppress("DEPRECATION")
                    peerConnection?.getStats(object : StatsObserver {
                        @Suppress("DEPRECATION") override fun onComplete(report: StatsReport) {
                            val stats = parseStats(report)
                            onStats?.invoke(stats)
                        }
                    })
                } catch (_: Exception) {}
            }
        }, 0, 2, java.util.concurrent.TimeUnit.SECONDS)
    }
    
    private fun stopStatsCollection() {
        statsJob?.cancel(false)
        statsJob = null
    }
    
    @Suppress("DEPRECATION")
    private fun parseStats(report: StatsReport): StreamStats {
        var fps = 0
        var latencyMs = 0
        var packetsLost = 0
        var packetsReceived = 0
        var bitrateKbpsLocal = lastBitrateKbps
        for (stat in report) {
            when (stat.type) {
                StatsReport.Type.INBOUND_RTP -> {
                    (stat.getValue("framesPerSecond") as? Number)?.let { fps = it.toInt() }
                    (stat.getValue("roundTripTime") as? Number)?.let { latencyMs = (it.toDouble() * 1000).toInt() }
                    (stat.getValue("packetsLost") as? Number)?.let { packetsLost = it.toInt() }
                    (stat.getValue("packetsReceived") as? Number)?.let { packetsReceived = it.toInt() }
                    // 285: bitrate cumulative bug — bytesReceived is total, not rate. Use delta.
                    (stat.getValue("bytesReceived") as? Number)?.let { bytesVal ->
                        val bytes = bytesVal.toLong()
                        val now = System.currentTimeMillis()
                        if (lastBytesReceived >= 0 && lastBitrateCalcTimeMs > 0) {
                            val deltaBytes = (bytes - lastBytesReceived).coerceAtLeast(0)
                            val deltaMs = (now - lastBitrateCalcTimeMs).coerceAtLeast(1)
                            bitrateKbpsLocal = ((deltaBytes * 8L * 1000L) / deltaMs / 1000L).toInt()
                            lastBitrateKbps = bitrateKbpsLocal
                        }
                        lastBytesReceived = bytes
                        lastBitrateCalcTimeMs = now
                    }
                }
                StatsReport.Type.REMOTE_INBOUND_RTP -> {
                    (stat.getValue("roundTripTime") as? Number)?.let { latencyMs = (it.toDouble() * 1000).toInt() }
                }
                else -> {}
            }
        }
        return StreamStats(fps, latencyMs, bitrateKbpsLocal, 0.0, packetsLost, packetsReceived)
    }

    private fun parseStatsNew(report: RTCStatsReport): StreamStats {
        var fps = 0; var latencyMs = 0; var packetsLost = 0; var packetsReceived = 0
        var bitrateKbpsLocal = lastBitrateKbps
        var bytesReceivedNow: Long? = null
        for ((_, v) in report.statsMap) {
            val type = v.type
            val members = v.members
            if (type == "inbound-rtp") {
                (members["framesPerSecond"] as? Number)?.let { fps = it.toInt() }
                (members["roundTripTime"] as? Number)?.let { latencyMs = (it.toDouble()*1000).toInt() }
                (members["packetsLost"] as? Number)?.let { packetsLost = it.toInt() }
                (members["packetsReceived"] as? Number)?.let { packetsReceived = it.toInt() }
                (members["bytesReceived"] as? Number)?.let { bytesReceivedNow = it.toLong() }
            }
            if (type == "remote-inbound-rtp") {
                (members["roundTripTime"] as? Number)?.let { latencyMs = (it.toDouble()*1000).toInt() }
            }
        }
        // 285: delta bitrate from cumulative bytesReceived
        bytesReceivedNow?.let { bytes ->
            val now = System.currentTimeMillis()
            if (lastBytesReceived >= 0 && lastBitrateCalcTimeMs > 0) {
                val deltaBytes = (bytes - lastBytesReceived).coerceAtLeast(0)
                val deltaMs = (now - lastBitrateCalcTimeMs).coerceAtLeast(1)
                bitrateKbpsLocal = ((deltaBytes * 8L * 1000L) / deltaMs / 1000L).toInt()
                lastBitrateKbps = bitrateKbpsLocal
            }
            lastBytesReceived = bytes
            lastBitrateCalcTimeMs = now
        }
        return StreamStats(fps, latencyMs, bitrateKbpsLocal, 0.0, packetsLost, packetsReceived)
    }
    
    data class StreamStats(
        val fps: Int = 0,
        val latencyMs: Int = 0,
        val bitrateKbps: Int = 0,
        val thermalLevel: Double = 0.0,
        val packetsLost: Int = 0,
        val packetsReceived: Int = 0
    )
    
    // Signaling client inner class
    private class SignalingClient(
        private val url: String,
        private val sessionProvider: () -> String?,
        private val errorHandler: ((String)->Unit)?,
        private val authTokenProvider: () -> String? = { null }
    ) {
        private var webSocket: okhttp3.WebSocket? = null
        private val client = okhttp3.OkHttpClient.Builder()
            .pingInterval(30, java.util.concurrent.TimeUnit.SECONDS)
            .build()
        
        var onOffer: ((String) -> Unit)? = null
        var onAnswer: ((String) -> Unit)? = null
        var onCandidate: ((String, String, Int) -> Unit)? = null
        var onInput: ((com.cymatic.client.network.model.InputPacket) -> Unit)? = null
        var onEndSession: (() -> Unit)? = null
        var onConnected: ((String) -> Unit)? = null
        var onDisconnected: ((String) -> Unit)? = null
        var onError: ((String) -> Unit)? = errorHandler
        
        fun connect() {
            val builder = okhttp3.Request.Builder().url(url)
            // Prefer Authorization header; backend falls back to ?token= (deprecated).
            authTokenProvider()?.takeIf { it.isNotBlank() }?.let {
                builder.addHeader("Authorization", "Bearer $it")
            }
            val request = builder.build()
            val listener = object : okhttp3.WebSocketListener() {
                override fun onOpen(webSocket: okhttp3.WebSocket, response: okhttp3.Response) {
                    Log.d("Signaling", "WebSocket connected")
                    this@SignalingClient.webSocket = webSocket
                    webSocket.send("""{"type":"register","payload":{"server_id":"android-client","type":"android"}}""")
                    sessionProvider()?.let { onConnected?.invoke(it) }
                }
                
                override fun onMessage(webSocket: okhttp3.WebSocket, text: String) {
                    parseAndHandleMessage(text)
                }
                
                override fun onFailure(webSocket: okhttp3.WebSocket, t: Throwable, response: okhttp3.Response?) {
                    Log.e("Signaling", "WebSocket error", t)
                    onError?.invoke("WebSocket error: ${t.message}")
                }
                
                override fun onClosed(webSocket: okhttp3.WebSocket, code: Int, reason: String) {
                    Log.d("Signaling", "WebSocket closed: $code $reason")
                    onDisconnected?.invoke("WebSocket closed: $reason")
                }
            }
            
            this.webSocket = client.newWebSocket(request, listener)
        }
        
        private fun parseAndHandleMessage(text: String) {
            try {
                val json = com.google.gson.Gson().fromJson(text, com.google.gson.JsonObject::class.java)
                val type = json.get("type").asString
                val payload = json.get("payload").asJsonObject
                
                when (type) {
                    "offer" -> {
                        val sdp = payload.get("sdp").asString
                        onOffer?.invoke(sdp)
                    }
                    "answer" -> {
                        val sdp = payload.get("sdp").asString
                        onAnswer?.invoke(sdp)
                    }
                    "candidate" -> {
                        val candidate = payload.get("candidate").asString
                        val sdpMid = payload.get("sdp_mid").asString
                        val sdpMLineIndex = payload.get("sdp_mline_index").asInt
                        onCandidate?.invoke(candidate, sdpMid, sdpMLineIndex)
                    }
                    "input" -> {
                        val gson = com.google.gson.Gson()
                        val input = gson.fromJson(payload, com.cymatic.client.network.model.InputPacket::class.java)
                        onInput?.invoke(input)
                    }
                    "end_session" -> {
                        onEndSession?.invoke()
                    }
                }
            } catch (e: Exception) {
                Log.e("Signaling", "Failed to parse message: $text", e)
            }
        }
        
        fun sendIceCandidate(sessionId: String, candidate: String, sdpMid: String, sdpMLineIndex: Int) {
            val msg = com.google.gson.Gson().toJson(mapOf(
                "type" to "candidate",
                "payload" to mapOf(
                    "session_id" to sessionId,
                    "candidate" to candidate,
                    "sdp_mid" to sdpMid,
                    "sdp_mline_index" to sdpMLineIndex
                )
            ))
            webSocket?.send(msg)
        }
        
        fun sendAnswer(sessionId: String, sdp: String) {
            val msg = com.google.gson.Gson().toJson(mapOf(
                "type" to "answer",
                "payload" to mapOf(
                    "session_id" to sessionId,
                    "sdp" to sdp
                )
            ))
            webSocket?.send(msg)
        }
        
        fun sendOffer(sessionId: String, sdp: String) {
            val msg = com.google.gson.Gson().toJson(mapOf(
                "type" to "offer",
                "payload" to mapOf(
                    "session_id" to sessionId,
                    "sdp" to sdp
                )
            ))
            webSocket?.send(msg)
        }
        
        fun sendInput(input: com.cymatic.client.network.model.InputPacket) {
            val msg = com.google.gson.Gson().toJson(mapOf(
                "type" to "input",
                "payload" to input
            ))
            webSocket?.send(msg)
        }
        
        fun disconnect() {
            try { webSocket?.close(1000, "Client disconnect") } catch (_: Exception) {}
            webSocket = null
            try { client.dispatcher.executorService.shutdown() } catch (_: Exception) {}
        }
        
        fun setCallbacks(
            onOffer: ((String) -> Unit)? = null,
            onAnswer: ((String) -> Unit)? = null,
            onCandidate: ((String, String, Int) -> Unit)? = null,
            onInput: ((com.cymatic.client.network.model.InputPacket) -> Unit)? = null,
            onEndSession: (() -> Unit)? = null,
            onConnected: ((String) -> Unit)? = null,
            onDisconnected: ((String) -> Unit)? = null
        ) {
            this.onOffer = onOffer
            this.onAnswer = onAnswer
            this.onCandidate = onCandidate
            this.onInput = onInput
            this.onEndSession = onEndSession
            this.onConnected = onConnected
            this.onDisconnected = onDisconnected
        }
    }
}
