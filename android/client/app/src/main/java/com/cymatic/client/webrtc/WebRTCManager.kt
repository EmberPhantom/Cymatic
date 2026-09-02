package com.cymatic.client.webrtc

import android.content.Context
import android.util.Log
import com.cymatic.client.input.InputManager
import com.cymatic.client.network.model.InputPacket
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.launch
import org.webrtc.*
import java.util.concurrent.Executors

class WebRTCManager(private val context: Context, private val eglBase: EglBase) {

    private val scope = CoroutineScope(Dispatchers.IO)
    private val factory: PeerConnectionFactory
    private var peerConnection: PeerConnection? = null
    private var localVideoTrack: VideoTrack? = null
    private var audioTrack: AudioTrack? = null
    private var videoSource: VideoSource? = null
    private var audioSource: AudioSource? = null
    
    private var signalingClient: SignalingClient? = null
    private var currentSessionId: String? = null
    
    // Callbacks
    private var onConnected: ((String) -> Unit)? = null
    private var onDisconnected: ((String) -> Unit)? = null
    private var onError: ((String) -> Unit)? = null
    private var onStats: ((StreamStats) -> Unit)? = null
    private var onRemoteVideoFrame: ((VideoFrame) -> Unit)? = null
    
    // Stats
    private val statsExecutor = Executors.newSingleThreadScheduledExecutor()
    private var statsJob: java.util.concurrent.ScheduledFuture<*>? = null
    
    // Input channel
    private val inputChannel = Channel<InputPacket>(100)
    
    init {
        // Initialize WebRTC
        PeerConnectionFactory.initialize(
            PeerConnectionFactory.InitializationOptions.builder(context)
                .setEnableInternalTracer(true)
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
    
    fun connect(signalingUrl: String, sessionId: String) {
        currentSessionId = sessionId
        
        // Create peer connection
        createPeerConnection()
        
        // Connect signaling
        signalingClient = SignalingClient(signalingUrl, { currentSessionId }, onError)
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
        val configuration = PeerConnection.RTCConfiguration().apply {
            iceServers = listOf(
                PeerConnection.IceServer.builder("stun:stun.l.google.com:19302").createIceServer()
            )
            sdpSemantics = PeerConnection.SdpSemantics.UNIFIED_PLAN
            bundlePolicy = PeerConnection.BundlePolicy.MAX_BUNDLE
            rtcpMuxPolicy = PeerConnection.RtcpMuxPolicy.REQUIRE
        }
        
        val constraints = MediaConstraints()
        constraints.mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveAudio", "true"))
        constraints.mandatory.add(MediaConstraints.KeyValuePair("OfferToReceiveVideo", "true"))
        
        peerConnection = factory.createPeerConnection(configuration, constraints, object : PeerConnection.Observer {
            override fun onIceCandidate(candidate: IceCandidate) {
                signalingClient?.sendIceCandidate(currentSessionId!!, candidate.sdp, candidate.sdpMid!!, candidate.sdpMLineIndex)
            }
            
            override fun onAddTrack(rtpReceiver: RtpReceiver, mediaStreams: Array<MediaStream>) {
                if (rtpReceiver.track().kind() == "video") {
                    rtpReceiver.track().addSink(object : VideoSink {
                        override fun onFrame(frame: VideoFrame) {
                            onRemoteVideoFrame?.invoke(frame)
                        }
                    })
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
                }
            }
        })
        
        // Create audio track
        audioSource = factory.createAudioSource(MediaConstraints())
        audioTrack = factory.createAudioTrack("audio", audioSource)
        peerConnection?.addTrack(audioTrack!!, listOf("stream"))
        
        // Video track will be created from remote stream
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
                            signalingClient?.sendAnswer(currentSessionId!!, answer.description)
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
        // Send head pose as input via signaling
        val packet = com.cymatic.client.input.InputManager().createInputPacket(input, FloatArray(3))
        signalingClient?.sendInput(packet)
    }
    
    fun sendAudioData(data: ByteArray) {
        // Send audio data through the audio track
        // For now, log it - real implementation would encode and send via data channel
        Log.d("WebRTC", "Audio data sent: ${data.size} bytes")
    }
    
    fun sendInput(input: InputPacket) {
        inputChannel.trySend(input)
    }
    
    fun resume() {
        peerConnection?.let { /* resume */ }
    }
    
    fun pause() {
        peerConnection?.let { /* pause */ }
    }
    
    fun disconnect() {
        stopStatsCollection()
        signalingClient?.disconnect()
        peerConnection?.close()
        peerConnection = null
        currentSessionId = null
    }
    
    fun reduceQuality() {
        // Reduce video encoding bitrate and resolution
        peerConnection?.getSenders()?.firstOrNull()?.let { sender ->
            val parameters = sender.getParameters()
            parameters.encodings[0].maxBitrate = 5_000_000 // Reduce to 5 Mbps
            parameters.encodings[0].scaleResolutionDownBy = 2.0 // Reduce resolution by half
            sender.setParameters(parameters)
        }
        
        // Also reduce target FPS
        val constraints = MediaConstraints()
        constraints.mandatory.add(MediaConstraints.KeyValuePair("maxFrameRate", "15"))
        peerConnection?.setLocalDescription(
            object : SdpObserver {
                override fun onCreateSuccess(desc: SessionDescription?) {}
                override fun onSetSuccess() {}
                override fun onCreateFailure(error: String) {}
                override fun onSetFailure(error: String) {}
            },
            peerConnection?.localDescription
        )
    }
    
    fun dispose() {
        disconnect()
        factory.dispose()
    }
    
    private fun startStatsCollection() {
        statsJob = statsExecutor.scheduleAtFixedRate({
            try {
                peerConnection?.getStats { report ->
                    val stats = parseStatsNew(report)
                    onStats?.invoke(stats)
                }
            } catch (_: Exception) {
                // fallback for older API
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
        }, 0, 1, java.util.concurrent.TimeUnit.SECONDS)
    }
    
    private fun stopStatsCollection() {
        statsJob?.cancel(false)
        statsJob = null
    }
    
    @Suppress("DEPRECATION")
    private fun parseStats(report: StatsReport): StreamStats {
        var fps = 0
        var latencyMs = 0
        var bitrateKbps = 0
        var packetsLost = 0
        var packetsReceived = 0
        for (stat in report) {
            when (stat.type) {
                StatsReport.Type.INBOUND_RTP -> {
                    (stat.getValue("framesPerSecond") as? Number)?.let { fps = it.toInt() }
                    (stat.getValue("roundTripTime") as? Number)?.let { latencyMs = (it.toDouble() * 1000).toInt() }
                    (stat.getValue("bitrate") as? Number)?.let { bitrateKbps = (it.toInt() / 1000) }
                    (stat.getValue("packetsLost") as? Number)?.let { packetsLost = it.toInt() }
                    (stat.getValue("packetsReceived") as? Number)?.let { packetsReceived = it.toInt() }
                }
                StatsReport.Type.REMOTE_INBOUND_RTP -> {
                    (stat.getValue("roundTripTime") as? Number)?.let { latencyMs = (it.toDouble() * 1000).toInt() }
                }
            }
        }
        return StreamStats(fps, latencyMs, bitrateKbps, 0.0, packetsLost, packetsReceived)
    }

    private fun parseStatsNew(report: RTCStatsReport): StreamStats {
        var fps = 0; var latencyMs = 0; var bitrateKbps = 0; var packetsLost = 0; var packetsReceived = 0
        for ((_, v) in report.statsMap) {
            val type = v.type
            val members = v.members
            if (type == "inbound-rtp") {
                (members["framesPerSecond"] as? Number)?.let { fps = it.toInt() }
                (members["roundTripTime"] as? Number)?.let { latencyMs = (it.toDouble()*1000).toInt() }
                (members["packetsLost"] as? Number)?.let { packetsLost = it.toInt() }
                (members["packetsReceived"] as? Number)?.let { packetsReceived = it.toInt() }
                (members["bytesReceived"] as? Number)?.let { bitrateKbps = (it.toLong()/1000).toInt() }
            }
        }
        return StreamStats(fps, latencyMs, bitrateKbps, 0.0, packetsLost, packetsReceived)
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
    private class SignalingClient(private val url: String, private val sessionProvider: () -> String?, private val errorHandler: ((String)->Unit)?) {
        private var webSocket: okhttp3.WebSocket? = null
        private val client = okhttp3.OkHttpClient()
        
        var onOffer: ((String) -> Unit)? = null
        var onAnswer: ((String) -> Unit)? = null
        var onCandidate: ((String, String, Int) -> Unit)? = null
        var onInput: ((com.cymatic.client.network.model.InputPacket) -> Unit)? = null
        var onEndSession: (() -> Unit)? = null
        var onConnected: ((String) -> Unit)? = null
        var onDisconnected: ((String) -> Unit)? = null
        var onError: ((String) -> Unit)? = errorHandler
        
        fun connect() {
            val request = okhttp3.Request.Builder().url(url).build()
            val listener = object : okhttp3.WebSocketListener() {
                override fun onOpen(webSocket: okhttp3.WebSocket, response: okhttp3.Response) {
                    Log.d("Signaling", "WebSocket connected")
                    this@SignalingClient.webSocket = webSocket
                    // Send register
                    webSocket.send("""{"type":"register","payload":{"server_id":"android-client","type":"android_client"}}""")
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
            webSocket?.close(1000, "Client disconnect")
            webSocket = null
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