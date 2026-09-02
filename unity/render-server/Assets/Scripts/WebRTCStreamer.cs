using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering;
using Cysharp.Threading.Tasks;

namespace Cymatic
{
    /// <summary>
    /// WebRTC streaming using Unity's VideoEncoder for H.264 encoding.
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
        private RTCPeerConnection _peerConnection;
        private VideoStreamTrack _videoTrack;
        private RenderTexture _leftEyeTexture;
        private RenderTexture _rightEyeTexture;
        
        // Cameras
        private Camera _leftCamera;
        private Camera _rightCamera;
        
        // Video Encoder
        private VideoEncoder _videoEncoder;
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
            _width = width;
            _height = height;
            _targetFPS = fps;
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
            
            var offer = new RTCSessionDescription { type = RTCSdpType.Offer, sdp = offerSdp };
            await _peerConnection.SetRemoteDescription(offer);
            
            var answer = await _peerConnection.CreateAnswer();
            await _peerConnection.SetLocalDescription(answer);
            
            return answer.sdp;
        }
        
        public async UniTask SetRemoteDescription(string sdp)
        {
            if (_peerConnection == null) return;
            
            var answer = new RTCSessionDescription { type = RTCSdpType.Answer, sdp = sdp };
            await _peerConnection.SetRemoteDescription(answer);
        }
        
        public async UniTask AddIceCandidate(string candidate, string sdpMid, int sdpMLineIndex)
        {
            if (_peerConnection == null) return;
            
            var iceCandidate = new RTCIceCandidate
            {
                candidate = candidate,
                sdpMid = sdpMid,
                sdpMLineIndex = sdpMLineIndex
            };
            
            await _peerConnection.AddIceCandidate(iceCandidate);
        }
        
        private async UniTask InitializePeerConnection()
        {
            var config = new RTCConfiguration
            {
                iceServers = new[]
                {
                    new RTCIceServer { urls = new[] { "stun:stun.l.google.com:19302" } }
                }
            };
            
            _peerConnection = new RTCPeerConnection(config);
            
            _peerConnection.OnIceCandidate = candidate =>
            {
                // Send to signaling
                RenderServer.Instance?.SendIceCandidate(candidate);
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
                    RenderServer.Instance?.StopStreaming().Forget();
                }
            };
        }
        
        public async UniTask StartStreaming(Camera leftCam, Camera rightCam)
        {
            _leftCamera = leftCam;
            _rightCamera = rightCam;
            
            // Use the stereo rig's camera render textures instead of creating separate ones
            _leftEyeTexture = leftCam.targetTexture ?? new RenderTexture(_width, _height, 24, RenderTextureFormat.ARGB32);
            _rightEyeTexture = rightCam.targetTexture ?? new RenderTexture(_width, _height, 24, RenderTextureFormat.ARGB32);
            
            // Initialize VideoEncoder for H.264
            await InitializeVideoEncoder();
            
            // Create video track from encoder
            _videoTrack = new VideoStreamTrack(_width * 2, _height, _targetFPS);
            
            // Add transceiver
            var transceiver = _peerConnection.AddTransceiver(_videoTrack);
            
            // Configure encoding
            var sender = transceiver.Sender;
            var parameters = sender.GetParameters();
            parameters.Encodings[0].BitratePriority = 1.0;
            parameters.Encodings[0].MinBitrate = _minBitrate;
            parameters.Encodings[0].MaxBitrate = _maxBitrate;
            parameters.Encodings[0].ScaleResolutionDownBy = 1.0;
            sender.SetParameters(parameters);
            
            // Start encoding loop
            _isStreaming = true;
            _lastFrameTime = 0;
            EncodingLoop().Forget();
            
            Debug.Log("[WebRTC] Streaming started with H.264 encoding");
        }
        
        private async UniTask InitializeVideoEncoder()
        {
            var encoderConfig = new VideoEncoderConfig
            {
                width = _width * 2,  // Side-by-side stereo
                height = _height,
                frameRate = _targetFPS,
                bitrate = _maxBitrate,
                profile = VideoEncoderProfile.H264High,
                hardwareAcceleration = _useHardwareEncoding ? HardwareAcceleration.Auto : HardwareAcceleration.None
            };
            
            _videoEncoder = new VideoEncoder(encoderConfig);
            _videoEncoder.OnEncodedFrame += OnEncodedFrame;
            
            await _videoEncoder.Initialize();
        }
        
        private void OnEncodedFrame(byte[] frameData, long timestamp, bool isKeyFrame)
        {
            if (_videoTrack != null)
            {
                _videoTrack.QueueEncodedFrame(frameData, timestamp, isKeyFrame);
            }
        }
        
        public void StopStreaming()
        {
            _isStreaming = false;
            
            if (_videoTrack != null)
            {
                _videoTrack.Dispose();
                _videoTrack = null;
            }
            
            if (_videoEncoder != null)
            {
                _videoEncoder.OnEncodedFrame -= OnEncodedFrame;
                _videoEncoder.Dispose();
                _videoEncoder = null;
            }
            
            if (_peerConnection != null)
            {
                _peerConnection.Close();
                _peerConnection = null;
            }
            
            if (_leftEyeTexture != null)
            {
                _leftEyeTexture.Release();
                Destroy(_leftEyeTexture);
                _leftEyeTexture = null;
            }
            
            if (_rightEyeTexture != null)
            {
                _rightEyeTexture.Release();
                Destroy(_rightEyeTexture);
                _rightEyeTexture = null;
            }
            
            Debug.Log("[WebRTC] Streaming stopped");
        }
        
        private async UniTaskVoid EncodingLoop()
        {
            while (_isStreaming)
            {
                var now = Time.realtimeSinceStartupAsDouble;
                if (now - _lastFrameTime < _frameInterval)
                {
                    await UniTask.Yield();
                    continue;
                }
                
                _lastFrameTime = now;
                
                // Render side-by-side stereo
                RenderSideBySide();
                
                // Encode frame using VideoEncoder (H.264)
                var combinedTexture = GetSideBySideTexture();
                await _videoEncoder.EncodeFrame(combinedTexture, Time.realtimeSinceStartupAsDouble * 1000000);
                RenderTexture.ReleaseTemporary(combinedTexture);
                
                _framesEncoded++;
            }
        }
        
        private void RenderSideBySide()
        {
            if (_leftCamera == null || _rightCamera == null) return;
            
            // Render left eye to left half
            Graphics.Blit(_leftCamera.targetTexture, _leftEyeTexture);
            
            // Render right eye to right half
            Graphics.Blit(_rightCamera.targetTexture, _rightEyeTexture);
            
            // Combine into side-by-side texture for encoder
            // The encoder reads from the combined texture
        }
        
        public void SetBitrate(int bitrate)
        {
            _maxBitrate = bitrate;
            try {
                var transceiver = _peerConnection?.GetTransceivers().Count > 0 ? _peerConnection.GetTransceivers()[0] : null;
                if (transceiver != null) {
                    var sender = transceiver.Sender;
                    var pars = sender.GetParameters();
                    if (pars.Encodings.Count > 0) {
                        pars.Encodings[0].MaxBitrate = (uint)bitrate;
                        sender.SetParameters(pars);
                    }
                }
            } catch {}
        }

        // Create combined texture for encoder input
        private RenderTexture GetSideBySideTexture()
        {
            var combined = RenderTexture.GetTemporary(_width * 2, _height, 24, RenderTextureFormat.ARGB32);
            var mat = new Material(Shader.Find("Unlit/Texture"));
            mat.SetTexture("_MainTex", _leftEyeTexture);
            // Blit with viewport rects via GL
            Graphics.SetRenderTarget(combined);
            GL.PushMatrix(); GL.LoadOrtho();
            Graphics.DrawTexture(new Rect(0, 0, 0.5f, 1), _leftEyeTexture, mat);
            Graphics.DrawTexture(new Rect(0.5f, 0, 0.5f, 1), _rightEyeTexture, mat);
            GL.PopMatrix();
            Graphics.SetRenderTarget(null);
            UnityEngine.Object.DestroyImmediate(mat);
            return combined;
        }
        
        // Stats
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