using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using System;
using System.IO;
using System.Text;
using Unity.WebRTC;
using Cysharp.Threading.Tasks;

namespace Cymatic
{
    /// <summary>
    /// Main entry point for the CYMATIC Render Server.
    /// Handles scene loading, WebRTC streaming, and input processing.
    /// </summary>
    public class RenderServer : MonoBehaviour
    {
        [Header("Configuration")]
        [SerializeField] private string backendUrl = "http://localhost:8000";
        [SerializeField] private string renderServerId = "render-server-01";
        [SerializeField] private int signalingPort = 8080;
        
        [Header("Streaming Settings")]
        [SerializeField] private int targetFPS = 60;
        [SerializeField] private int renderWidth = 1920;
        [SerializeField] private int renderHeight = 1080;
        [SerializeField] private int ipd = 64; // mm
        
        [Header("Quality Settings")]
        [SerializeField] private bool adaptiveQuality = true;
        [SerializeField] private int minBitrate = 5000000; // 5 Mbps
        [SerializeField] private int maxBitrate = 30000000; // 30 Mbps
        
        // Components
        private StereoCameraRig _stereoRig;
        private WebRTCStreamer _webRTCStreamer;
        private InputManager _inputManager;
        private SceneLoader _sceneLoader;
        private PerformanceManager _performanceManager;
        private EventBridge _eventBridge;
        private SignalingClient _signalingClient;
        
        // State
        private bool _isStreaming = false;
        private string _currentSessionId;
        private CymaticScenePackage _currentScenePackage;
        
        public static RenderServer Instance { get; private set; }
        public bool IsStreaming => _isStreaming;
        public string CurrentSessionId => _currentSessionId;
        public string RenderServerId => renderServerId;
        public StereoCameraRig StereoRig => _stereoRig;
        public WebRTCStreamer WebRTCStreamer => _webRTCStreamer;
        public InputManager InputManager => _inputManager;
        public PerformanceManager PerformanceManager => _performanceManager;
        public SignalingClient SignalingClient => _signalingClient;
        public EventBridge EventBridge => _eventBridge;
        
        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            
            InitializeComponents();
        }
        
        private void InitializeComponents()
        {
            _stereoRig = GetComponentInChildren<StereoCameraRig>();
            if (_stereoRig == null)
            {
                var rigGO = new GameObject("StereoCameraRig");
                rigGO.transform.SetParent(transform);
                _stereoRig = rigGO.AddComponent<StereoCameraRig>();
            }
            
            _webRTCStreamer = GetComponent<WebRTCStreamer>();
            if (_webRTCStreamer == null)
                _webRTCStreamer = gameObject.AddComponent<WebRTCStreamer>();
            
            _inputManager = GetComponent<InputManager>();
            if (_inputManager == null)
                _inputManager = gameObject.AddComponent<InputManager>();
            
            _sceneLoader = GetComponent<SceneLoader>();
            if (_sceneLoader == null)
                _sceneLoader = gameObject.AddComponent<SceneLoader>();
            
            _performanceManager = GetComponent<PerformanceManager>();
            if (_performanceManager == null)
                _performanceManager = gameObject.AddComponent<PerformanceManager>();
            
            _eventBridge = GetComponent<EventBridge>();
            if (_eventBridge == null)
                _eventBridge = gameObject.AddComponent<EventBridge>();
            
            _signalingClient = GetComponent<SignalingClient>();
            if (_signalingClient == null)
                _signalingClient = gameObject.AddComponent<SignalingClient>();
            
            // Configure components
            _stereoRig.Configure(ipd, renderWidth, renderHeight);
            _webRTCStreamer.Configure(renderWidth, renderHeight, targetFPS, minBitrate, maxBitrate);
            _performanceManager.Configure(targetFPS, adaptiveQuality);
            _performanceManager.OnQualityChanged += (idx) => {
                // Link adaptive quality to WebRTC bitrate (5-30 Mbps range)
                var bitrates = new int[]{30000000, 20000000, 10000000, 5000000, 2500000};
                var br = bitrates[Mathf.Clamp(idx, 0, bitrates.Length-1)];
                try { _webRTCStreamer.SetBitrate(br); } catch {}
            };
            _eventBridge.Configure(backendUrl, renderServerId);
            var signalingHost = "localhost";
            try { signalingHost = new System.Uri(backendUrl).Host; } catch {}
            _signalingClient.Configure($"ws://{signalingHost}:{signalingPort}/ws");
        }
        
        private async void Start()
        {
            Application.targetFrameRate = targetFPS;
            QualitySettings.vSyncCount = 0;
            
            // Register with backend
            await _eventBridge.RegisterRenderServer();
            
            // Start signaling connection
            _signalingClient.OnOfferReceived += HandleOfferReceived;
            _signalingClient.OnAnswerReceived += HandleAnswerReceived;
            _signalingClient.OnCandidateReceived += HandleCandidateReceived;
            await _signalingClient.Connect();
            
            Debug.Log("[RenderServer] Started and ready for sessions");
        }
        
        private async void HandleOfferReceived(string sessionId, string sdp)
        {
            try {
                // MVP single-stream guard per AGENTS.md
                if (_isStreaming)
                {
                    Debug.LogWarning($"[RenderServer] Busy, rejecting session {sessionId}");
                    _signalingClient.Send(new SignalingMessage { type = "error", payload = new { session_id = sessionId, error = "busy: one concurrent stream in MVP" } });
                    return;
                }
                _currentSessionId = sessionId;
                Debug.Log($"[RenderServer] Received offer for session {sessionId}");
                // Create answer immediately for low latency, load scene in parallel
                var answerTask = _webRTCStreamer.CreateAnswer(sdp);
                var sessionInfoTask = _eventBridge.GetSessionInfo(sessionId);
                var answer = await answerTask;
                _signalingClient.SendAnswer(sessionId, answer);
                var sessionInfo = await sessionInfoTask;
                if (sessionInfo != null && !string.IsNullOrEmpty(sessionInfo.scenePackageUrl))
                {
                    await LoadScene(sessionInfo.scenePackageUrl);
                }
            } catch (System.Exception e) { Debug.LogError($"[RenderServer] HandleOffer error: {e}"); }
        }
        
        private async void HandleAnswerReceived(string sessionId, string sdp)
        {
            try { await _webRTCStreamer.SetRemoteDescription(sdp); } catch (System.Exception e) { Debug.LogError($"HandleAnswer error {e}"); }
        }
        
        private async void HandleCandidateReceived(string sessionId, string candidate, string sdpMid, int sdpMLineIndex)
        {
            try { await _webRTCStreamer.AddIceCandidate(candidate, sdpMid, sdpMLineIndex); } catch (System.Exception e) { Debug.LogError($"HandleCandidate error {e}"); }
        }
        
        public async UniTask LoadScene(string scenePackageUrl)
        {
            Debug.Log($"[RenderServer] Loading scene from {scenePackageUrl}");
            
            _currentScenePackage = await _sceneLoader.LoadFromUrl(scenePackageUrl);
            if (_currentScenePackage == null)
            {
                Debug.LogError("[RenderServer] Failed to load scene package");
                return;
            }
            
            // Instantiate scene
            await _sceneLoader.InstantiateScene(_currentScenePackage);
            
            // Configure stereo rig for scene
            _stereoRig.SetNavigationPoints(_currentScenePackage.navigation);
            
            // Notify backend
            await _eventBridge.SendEvent(_currentSessionId, "scene_loaded", new { scenePackageUrl });
            
            Debug.Log("[RenderServer] Scene loaded successfully");
        }
        
        public async UniTask StartStreaming(string sessionId)
        {
            _currentSessionId = sessionId;
            _isStreaming = true;
            
            // Start WebRTC streaming
            await _webRTCStreamer.StartStreaming(_stereoRig.LeftCamera, _stereoRig.RightCamera);
            
            // Start input processing
            _inputManager.StartProcessing();
            
            // Start performance monitoring
            _performanceManager.StartMonitoring();
            
            await _eventBridge.SendEvent(sessionId, "stream_started", new { });
            Debug.Log($"[RenderServer] Streaming started for session {sessionId}");
        }
        
        public async UniTask StopStreaming()
        {
            if (!_isStreaming) return;
            var endedId = _currentSessionId;
            _isStreaming = false;
            try { _webRTCStreamer.StopStreaming(); } catch {}
            try { _inputManager.StopProcessing(); } catch {}
            try { _performanceManager.StopMonitoring(); } catch {}
            try { await _sceneLoader.UnloadScene(); } catch {}
            try { await _eventBridge.SendEvent(endedId, "stream_ended", new { }); } catch {}
            _currentSessionId = null;
            Debug.Log("[RenderServer] Streaming stopped");
        }

        private float _lastInputSendTime;
        private const float InputSendInterval = 0.05f; // 20Hz coalesce (was 60Hz per-frame spam)

        // P0 FIX: WebRTCStreamer OnIceCandidate NRE - provide helper to route candidate to signaling/event bridge
        public void SendIceCandidate(Unity.WebRTC.RTCIceCandidate candidate)
        {
            if (candidate == null) return;
            if (string.IsNullOrEmpty(_currentSessionId))
            {
                Debug.LogWarning("[RenderServer] SendIceCandidate no session");
                return;
            }
            try
            {
                // P0 FIX: real Unity.WebRTC 3.0.0-pre.8 uses capital Candidate/SdpMid/SdpMLineIndex (nullable)
                _signalingClient?.SendIceCandidate(_currentSessionId, candidate.Candidate, candidate.SdpMid, candidate.SdpMLineIndex ?? 0);
            }
            catch (Exception e) { Debug.LogWarning($"[RenderServer] Signaling SendIceCandidate failed: {e.Message}"); }
            try
            {
                _eventBridge?.SendIceCandidate(_currentSessionId, candidate).Forget();
            }
            catch (Exception e) { Debug.LogWarning($"[RenderServer] EventBridge SendIceCandidate failed: {e.Message}"); }
        }

#if !UNITY_WEBRTC
        // stub for compile when package not present
#endif
        
        private void Update()
        {
            if (!_isStreaming) return;
            
            // Process input - coalesce to 20Hz instead of 60Hz per-frame spam; keep only latest per type
            if (Time.time - _lastInputSendTime >= InputSendInterval)
            {
                var coalesced = _inputManager.GetCoalescedPackets();
                if (coalesced.Count > 0)
                {
                    foreach (var pkt in coalesced)
                    {
                        _signalingClient.SendInput(_currentSessionId, pkt);
                    }
                    _lastInputSendTime = Time.time;
                }
                else if (_inputManager.PendingCount > 0)
                {
                    // Fallback drain unlikely (GetCoalescedPackets already drains)
                    var single = _inputManager.GetInputPacket();
                    if (single != null) _signalingClient.SendInput(_currentSessionId, single);
                }
            }
            // Still update head pose every frame for low latency (ring already has smoothed pose)
            if (_inputManager.HasHeadPose)
            {
                _stereoRig.UpdateHeadPose(_inputManager.HeadPosition, _inputManager.HeadRotation);
            }
            
            // Performance management is driven by PerformanceManager's own Update (MonoBehaviour auto-tick)
        }
        
        private void OnDestroy()
        {
            if (_isStreaming)
                StopStreaming().Forget();
            
            _signalingClient.Disconnect();
        }
    }
}