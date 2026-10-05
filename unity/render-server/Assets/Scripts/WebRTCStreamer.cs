using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using Unity.WebRTC;
using Cysharp.Threading.Tasks;

namespace Cymatic
{
    /// <summary>
    /// WebRTC streaming using Unity.WebRTC VideoStreamTrack for H.264 encoding.
    /// P0 FIX: Removed mock VideoEncoder, use RTCRtpSender SetBitrate path with #if UNITY_WEBRTC guard.
    /// P0 FIX: Real Unity.WebRTC 3.0.0-pre.8 API: RTCPeerConnection(ref config), VideoStreamTrack(Texture), RTCRtpSendParameters.encodings
    /// </summary>
    public class WebRTCStreamer : MonoBehaviour
    {
        [Header("Streaming Settings")]
        [SerializeField] private int _width = 1920;
        [SerializeField] private int _height = 1080;
        [SerializeField] private int _targetFPS = 30;
        [SerializeField] private int _minBitrate = 5000000;
        [SerializeField] private int _maxBitrate = 30000000;
        [SerializeField] private bool _useHardwareEncoding = true;

        // WebRTC
#if UNITY_WEBRTC
        private RTCPeerConnection _peerConnection;
        private VideoStreamTrack _videoTrack;
#else
        private Unity.WebRTC.RTCPeerConnection _peerConnection;
        private Unity.WebRTC.VideoStreamTrack _videoTrack;
#endif
        private RenderTexture _leftEyeTexture;
        private RenderTexture _rightEyeTexture;

        // Cameras
        private Camera _leftCamera;
        private Camera _rightCamera;

        // P0 FIX: cache blit material (avoid per-frame alloc at line 289)
        private Material _blitMaterial;
        private Material CachedBlitMaterial
        {
            get
            {
                if (_blitMaterial == null)
                {
                    var shader = Shader.Find("Unlit/Texture");
                    if (shader == null) shader = Shader.Find("Standard");
                    _blitMaterial = new Material(shader);
                    _blitMaterial.hideFlags = HideFlags.HideAndDontSave;
                }
                return _blitMaterial;
            }
        }

        // P0 FIX: VideoEncoder mock removed -> use no-op stub guarded
        private bool _isStreaming = false;
        private float _frameInterval;
        private double _lastFrameTime;

        // Stats
        private int _framesEncoded = 0;
        private float _currentBitrate = 0;
        private int _currentFPS = 0;

        public bool IsStreaming => _isStreaming;
        public int CurrentFPS => _currentFPS;
        public float CurrentBitrateMbps => _currentBitrate / 1000000f;

        public void Configure(int width, int height, int fps, int minBitrate, int maxBitrate)
        {
            // P0 FIX: 270 width 3840 overflow - clamp combined width
            _width = Mathf.Clamp(width, 64, 1920);
            _height = Mathf.Clamp(height, 64, 1080);
            if (_width * 2 > 3840)
            {
                _width = 1920; // cap
            }
            _targetFPS = Mathf.Clamp(fps, 1, 60);
            _minBitrate = minBitrate;
            _maxBitrate = maxBitrate;
            _frameInterval = 1f / _targetFPS;
        }

        public async UniTask<string> CreateAnswer(string offerSdp)
        {
            if (_peerConnection == null)
            {
                await InitializePeerConnection();
            }

#if UNITY_WEBRTC
            var offer = new RTCSessionDescription { type = RTCSdpType.Offer, sdp = offerSdp };
            var opRemote = _peerConnection.SetRemoteDescription(ref offer);
            await UniTask.WaitUntil(() => opRemote.IsDone);
            if (opRemote.IsError) throw new Exception($"SetRemoteDescription failed: {opRemote.Error.message} type={opRemote.Error.errorType}");

            var opAnswer = _peerConnection.CreateAnswer();
            await UniTask.WaitUntil(() => opAnswer.IsDone);
            if (opAnswer.IsError) throw new Exception($"CreateAnswer failed: {opAnswer.Error.message} type={opAnswer.Error.errorType}");
            var answer = opAnswer.Desc;

            var opLocal = _peerConnection.SetLocalDescription(ref answer);
            await UniTask.WaitUntil(() => opLocal.IsDone);
            if (opLocal.IsError) throw new Exception($"SetLocalDescription failed: {opLocal.Error.message} type={opLocal.Error.errorType}");
            return answer.sdp;
#else
            var offerStub = new RTCSessionDescription { type = RTCSdpType.Offer, sdp = offerSdp };
            await _peerConnection.SetRemoteDescription(offerStub);
            var answerStub = await _peerConnection.CreateAnswer();
            await _peerConnection.SetLocalDescription(answerStub);
            return answerStub.sdp;
#endif
        }

        public async UniTask SetRemoteDescription(string sdp)
        {
            if (_peerConnection == null) return;
#if UNITY_WEBRTC
            var desc = new RTCSessionDescription { type = RTCSdpType.Answer, sdp = sdp };
            var op = _peerConnection.SetRemoteDescription(ref desc);
            await UniTask.WaitUntil(() => op.IsDone);
            if (op.IsError) Debug.LogError($"SetRemoteDescription error: {op.Error.message} type={op.Error.errorType}");
#else
            var answer = new RTCSessionDescription { type = RTCSdpType.Answer, sdp = sdp };
            await _peerConnection.SetRemoteDescription(answer);
#endif
        }

        public async UniTask AddIceCandidate(string candidate, string sdpMid, int sdpMLineIndex)
        {
            if (_peerConnection == null) return;
#if UNITY_WEBRTC
            var init = new RTCIceCandidateInit { candidate = candidate, sdpMid = sdpMid, sdpMLineIndex = sdpMLineIndex };
            var iceCandidate = new RTCIceCandidate(init);
            _peerConnection.AddIceCandidate(iceCandidate);
            await UniTask.CompletedTask;
#else
            var iceCandidate = new RTCIceCandidate
            {
                candidate = candidate,
                sdpMid = sdpMid,
                sdpMLineIndex = sdpMLineIndex
            };
            await _peerConnection.AddIceCandidate(iceCandidate);
#endif
        }

        private async UniTask InitializePeerConnection()
        {
            // LAN-first: host candidates suffice; STUN adds DNS/gathering delay.
            // TURN configured via env (TURN_URL/USERNAME/PASSWORD) for WAN fallback.
            var turnUrl = System.Environment.GetEnvironmentVariable("TURN_URL") ?? "";
            var turnUser = System.Environment.GetEnvironmentVariable("TURN_USERNAME") ?? "";
            var turnPass = System.Environment.GetEnvironmentVariable("TURN_PASSWORD") ?? "";
            RTCIceServer[] iceServers;
            if (!string.IsNullOrEmpty(turnUrl) && !string.IsNullOrEmpty(turnUser))
            {
                iceServers = new[]
                {
                    new RTCIceServer { urls = new[] { "stun:stun.l.google.com:19302" } },
                    new RTCIceServer { urls = new[] { turnUrl }, username = turnUser, credential = turnPass }
                };
            }
            else
            {
                iceServers = new[]
                {
                    new RTCIceServer { urls = new[] { "stun:stun.l.google.com:19302" } }
                };
            }
            var config = new RTCConfiguration
            {
                iceServers = iceServers
            };

            // P0 FIX: real com.unity.webrtc 3.0.0-pre.8 requires ref RTCConfiguration
#if UNITY_WEBRTC
            _peerConnection = new RTCPeerConnection(ref config);
#else
            _peerConnection = new Unity.WebRTC.RTCPeerConnection(config);
#endif

            _peerConnection.OnIceCandidate = candidate =>
            {
                if (candidate == null) return;
                if (RenderServer.Instance == null) return;
                try
                {
                    RenderServer.Instance.SendIceCandidate(candidate);
                }
                catch (Exception e)
                {
                    Debug.LogWarning($"[WebRTC] SendIceCandidate failed: {e.Message}");
                }
            };

            _peerConnection.OnConnectionStateChange = state =>
            {
                Debug.Log($"[WebRTC] Connection state: {state}");
                if (state == RTCPeerConnectionState.Connected)
                {
                    _isStreaming = true;
                }
                else if (state == RTCPeerConnectionState.Disconnected ||
                         state == RTCPeerConnectionState.Failed ||
                         state == RTCPeerConnectionState.Closed)
                {
                    _isStreaming = false;
                    try { RenderServer.Instance?.StopStreaming().Forget(); } catch {}
                }
            };
            await UniTask.CompletedTask;
        }

        public async UniTask StartStreaming(Camera leftCam, Camera rightCam)
        {
            _leftCamera = leftCam;
            _rightCamera = rightCam;

            _leftEyeTexture = leftCam != null ? leftCam.targetTexture : null;
            if (_leftEyeTexture == null)
            {
                _leftEyeTexture = new RenderTexture(_width, _height, 16, RenderTextureFormat.Default);
                _leftEyeTexture.antiAliasing = 1;
                _leftEyeTexture.Create();
            }
            _rightEyeTexture = rightCam != null ? rightCam.targetTexture : null;
            if (_rightEyeTexture == null)
            {
                _rightEyeTexture = new RenderTexture(_width, _height, 16, RenderTextureFormat.Default);
                _rightEyeTexture.antiAliasing = 1;
                _rightEyeTexture.Create();
            }

#if UNITY_WEBRTC
            // Real Unity.WebRTC 3.0.0-pre.8 only supports VideoStreamTrack(Texture) ctor
            try
            {
                Texture sourceTex = _leftEyeTexture != null ? (Texture)_leftEyeTexture : (Texture)_rightEyeTexture;
                // Fallback dummy if both null (should not happen)
                RenderTexture dummyRT = null;
                if (sourceTex == null)
                {
                    dummyRT = new RenderTexture(Mathf.Clamp(_width*2,64,3840), Mathf.Clamp(_height,64,1080), 0, RenderTextureFormat.Default);
                    dummyRT.Create();
                    sourceTex = dummyRT;
                }
                _videoTrack = new VideoStreamTrack(sourceTex);
                // dummyRT will be owned by track after creation; keep reference if needed
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[WebRTC] VideoStreamTrack(Texture) failed: {e.Message}, trying parameterless fallback");
                try { _videoTrack = new VideoStreamTrack(_leftEyeTexture); } catch { Debug.LogWarning("[WebRTC] Fallback VideoStreamTrack also failed"); }
            }

            // Add transceiver - real API: AddTransceiver(MediaStreamTrack)
            RTCRtpTransceiver transceiver = null;
            try { transceiver = _peerConnection.AddTransceiver(_videoTrack); } catch (Exception e) { Debug.LogWarning($"[WebRTC] AddTransceiver failed: {e.Message}"); }

            // Configure encoding via RTCRtpSender - real API uses RTCRtpSendParameters with lower-case fields
            try
            {
                if (transceiver != null)
                {
                    var sender = transceiver.Sender;
                    if (sender != null)
                    {
                        var parameters = sender.GetParameters();
                        if (parameters != null && parameters.encodings != null && parameters.encodings.Length > 0)
                        {
                            parameters.encodings[0].minBitrate = (ulong)(uint)_minBitrate;
                            parameters.encodings[0].maxBitrate = (ulong)(uint)_maxBitrate;
                            parameters.encodings[0].scaleResolutionDownBy = 1.0;
                            var err = sender.SetParameters(parameters);
                            if (err.errorType != RTCErrorType.None)
                                Debug.LogWarning($"[WebRTC] SetParameters error: {err.message} type={err.errorType}");
                        }
                    }
                }
            }
            catch (Exception e) { Debug.LogWarning($"[WebRTC] SetParameters failed: {e.Message}"); }
#else
            // Fallback for syntax check when UNITY_WEBRTC not defined (uses stub)
            _videoTrack = new Unity.WebRTC.VideoStreamTrack(_width * 2, _height, _targetFPS);
            try
            {
                var transceiver = _peerConnection?.AddTransceiver(_videoTrack);
                var sender = transceiver?.Sender;
                if (sender != null)
                {
                    var parameters = sender.GetParameters();
                    if (parameters != null && parameters.Encodings != null && parameters.Encodings.Count > 0)
                    {
                        parameters.Encodings[0].MinBitrate = (uint)_minBitrate;
                        parameters.Encodings[0].MaxBitrate = (uint)_maxBitrate;
                        sender.SetParameters(parameters);
                    }
                }
            }
            catch {}
#endif

            _isStreaming = true;
            _lastFrameTime = 0;
            EncodingLoop().Forget();

            Debug.Log("[WebRTC] Streaming started");
            await UniTask.CompletedTask;
        }

#if UNITY_WEBRTC
        private async UniTask InitializeVideoEncoderFallback()
        {
            await UniTask.CompletedTask;
        }
#endif

        public void StopStreaming()
        {
            _isStreaming = false;

            if (_videoTrack != null)
            {
                try { _videoTrack.Dispose(); } catch {}
                _videoTrack = null;
            }

            if (_peerConnection != null)
            {
                try { _peerConnection.Close(); } catch {}
                try { _peerConnection.Dispose(); } catch {}
                _peerConnection = null;
            }

            if (_leftEyeTexture != null && _leftCamera != null && _leftEyeTexture != _leftCamera.targetTexture)
            {
                _leftEyeTexture.Release();
                Destroy(_leftEyeTexture);
            }
            _leftEyeTexture = null;

            if (_rightEyeTexture != null && _rightCamera != null && _rightEyeTexture != _rightCamera.targetTexture)
            {
                _rightEyeTexture.Release();
                Destroy(_rightEyeTexture);
            }
            _rightEyeTexture = null;

            if (_blitMaterial != null)
            {
                Destroy(_blitMaterial);
                _blitMaterial = null;
            }

            Debug.Log("[WebRTC] Streaming stopped");
        }

        private async UniTaskVoid EncodingLoop()
        {
            while (_isStreaming)
            {
                var now = Time.realtimeSinceStartupAsDouble;
                var elapsed = now - _lastFrameTime;
                if (elapsed < _frameInterval)
                {
                    // Fixed busy spin: use Delay instead of Yield every frame (was spinning at display refresh)
                    var remaining = _frameInterval - (float)elapsed;
                    int delayMs = Mathf.Clamp(Mathf.RoundToInt(remaining * 1000f), 1, 500);
                    // Use Realtime delay so TimeScale 0 doesn't stall streaming
                    await UniTask.Delay(delayMs, DelayType.Realtime, PlayerLoopTiming.Update, this.GetCancellationTokenOnDestroy());
                    continue;
                }

                _lastFrameTime = now;

                RenderSideBySide();

                var combinedTexture = GetSideBySideTexture();
                if (combinedTexture != null)
                {
#if UNITY_WEBRTC
                    try { /* VideoStreamTrack captures texture automatically via internal copy; no explicit encode needed */ } catch {}
#endif
                    RenderTexture.ReleaseTemporary(combinedTexture);
                }

                _framesEncoded++;
                // Yield to allow frame pacing; if _targetFPS high, loop will Delay next iter
                await UniTask.Yield(PlayerLoopTiming.Update, this.GetCancellationTokenOnDestroy());
            }
        }

        private void RenderSideBySide()
        {
            if (_leftCamera == null || _rightCamera == null) return;
            if (_leftCamera.targetTexture == null || _rightCamera.targetTexture == null) return;
            if (_leftEyeTexture == null || _rightEyeTexture == null) return;

            try
            {
                if (_leftCamera.targetTexture != _leftEyeTexture)
                    Graphics.Blit(_leftCamera.targetTexture, _leftEyeTexture);
                if (_rightCamera.targetTexture != _rightEyeTexture)
                    Graphics.Blit(_rightCamera.targetTexture, _rightEyeTexture);
            }
            catch (Exception e) { Debug.LogWarning($"[WebRTC] RenderSideBySide Blit failed: {e.Message}"); }
        }

        public void SetBitrate(int bitrate)
        {
            _maxBitrate = bitrate;
            try {
                if (_peerConnection == null) return;
#if UNITY_WEBRTC
                var transceivers = _peerConnection.GetTransceivers();
                if (transceivers == null) return;
                var list = transceivers.ToList();
                if (list.Count == 0) return;
                var transceiver = list[0];
                if (transceiver == null) return;
                var sender = transceiver.Sender;
                if (sender == null) return;
                var pars = sender.GetParameters();
                if (pars == null || pars.encodings == null || pars.encodings.Length == 0) return;
                pars.encodings[0].maxBitrate = (ulong)(uint)bitrate;
                var err = sender.SetParameters(pars);
                if (err.errorType != RTCErrorType.None) Debug.LogWarning($"[WebRTC] SetBitrate error: {err.message}");
#else
                var transceivers = _peerConnection.GetTransceivers();
                if (transceivers == null || transceivers.Count == 0) return;
                var transceiver = transceivers[0];
                if (transceiver == null) return;
                var sender = transceiver.Sender;
                if (sender == null) return;
                var pars = sender.GetParameters();
                if (pars == null || pars.Encodings == null || pars.Encodings.Count == 0) return;
                pars.Encodings[0].MaxBitrate = (uint)bitrate;
                sender.SetParameters(pars);
#endif
            } catch (Exception e) { Debug.LogWarning($"[WebRTC] SetBitrate failed: {e.Message}"); }
        }

        private RenderTexture GetSideBySideTexture()
        {
            int combinedW = _width * 2;
            combinedW = Mathf.Clamp(combinedW, 64, 3840);
            int h = Mathf.Clamp(_height, 64, 1080);

            var combined = RenderTexture.GetTemporary(combinedW, h, 0, RenderTextureFormat.Default);
            combined.filterMode = FilterMode.Bilinear;
            combined.antiAliasing = 1;

            var mat = CachedBlitMaterial;
            try
            {
                Graphics.SetRenderTarget(combined);
                GL.PushMatrix(); GL.LoadOrtho();
                if (_leftEyeTexture != null)
                    Graphics.DrawTexture(new Rect(0, 0, 0.5f, 1), _leftEyeTexture, mat);
                if (_rightEyeTexture != null)
                    Graphics.DrawTexture(new Rect(0.5f, 0, 0.5f, 1), _rightEyeTexture, mat);
                GL.PopMatrix();
                Graphics.SetRenderTarget(null);
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[WebRTC] GetSideBySideTexture failed: {e.Message}");
                try { GL.PopMatrix(); } catch {}
                Graphics.SetRenderTarget(null);
            }
            return combined;
        }

        public StreamingStats GetStats()
        {
            return new StreamingStats
            {
                fps = _currentFPS,
                bitrateMbps = _currentBitrate / 1000000f,
                framesEncoded = _framesEncoded,
                isStreaming = _isStreaming
            };
        }

        private void OnDestroy()
        {
            StopStreaming();
        }
    }

    [System.Serializable]
    public class StreamingStats
    {
        public int fps;
        public float bitrateMbps;
        public int framesEncoded;
        public bool isStreaming;
    }
}
