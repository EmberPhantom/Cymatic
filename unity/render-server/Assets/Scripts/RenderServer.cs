using System.Collections;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using System;
using System.IO;
using System.Text;
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
        public StereoCameraRig StereoRig => _stereoRig;
        public WebRTCStreamer WebRTCStreamer => _webRTCStreamer;
        public InputManager InputManager => _inputManager;
        public PerformanceManager PerformanceManager => _performanceManager;
        
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
            _eventBridge.Configure(backendUrl, renderServerId);
            var signalingHost = "localhost";
            try { signalingHost = new System.Uri(backendUrl).Host; } catch {}
            _signalingClient.Configure($"ws://{signalingHost}:{signalingPort}");
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
                _currentSessionId = sessionId;
                Debug.Log($"[RenderServer] Received offer for session {sessionId}");
                var sessionInfo = await _eventBridge.GetSessionInfo(sessionId);
                if (sessionInfo != null && !string.IsNullOrEmpty(sessionInfo.scenePackageUrl))
                {
                    await LoadScene(sessionInfo.scenePackageUrl);
                }
                var answer = await _webRTCStreamer.CreateAnswer(sdp);
                await _signalingClient.SendAnswer(sessionId, answer);
            } catch (System.Exception e) { Debug.LogError($"[RenderServer] HandleOffer error: {e}"); }
        }
        
        private async void HandleAnswerReceived(string sessionId, string sdp)
        {
            await _webRTCStreamer.SetRemoteDescription(sdp);
        }
        
        private async void HandleCandidateReceived(string sessionId, string candidate, string sdpMid, int sdpMLineIndex)
        {
            await _webRTCStreamer.AddIceCandidate(candidate, sdpMid, sdpMLineIndex);
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
            _webRTCStreamer.StopStreaming();
            _inputManager.StopProcessing();
            _performanceManager.StopMonitoring();
            await _sceneLoader.UnloadScene();
            await _eventBridge.SendEvent(endedId, "stream_ended", new { });
            _currentSessionId = null;
            Debug.Log("[RenderServer] Streaming stopped");
        }
        
        private void Update()
        {
            if (!_isStreaming) return;
            
            // Process input
            var inputPacket = _inputManager.GetInputPacket();
            if (inputPacket != null)
            {
                _signalingClient.SendInput(_currentSessionId, inputPacket);
            }
            
            // Update stereo rig with head pose
            if (_inputManager.HasHeadPose)
            {
                _stereoRig.UpdateHeadPose(_inputManager.HeadPosition, _inputManager.HeadRotation);
            }
            
            // Performance management
            _performanceManager.Update();
        }
        
        private void OnDestroy()
        {
            if (_isStreaming)
                StopStreaming().Forget();
            
            _signalingClient.Disconnect();
        }
    }
}