using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json;

namespace Cymatic
{
    /// <summary>
    /// Event Bridge - Communicates with backend API for runtime events.
    /// </summary>
    public class EventBridge : MonoBehaviour
    {
        [Header("Configuration")]
        [SerializeField] private string _backendUrl = "http://localhost:8000";
        [SerializeField] private string _renderServerId = "render-server-01";
        [SerializeField] private float _heartbeatInterval = 5f;
        
        // State
        private bool _isRegistered = false;
        private string _authToken;
        
        public event Action<string, string, string> OnCommandReceived; // sessionId, command, payload
        
        public void Configure(string backendUrl, string renderServerId)
        {
            _backendUrl = backendUrl;
            _renderServerId = renderServerId;
        }
        
        public async UniTask RegisterRenderServer()
        {
            var request = new RegisterRequest
            {
                server_id = _renderServerId,
                capabilities = new ServerCapabilities
                {
                    max_sessions = 1,
                    supports_hand_tracking = false,
                    supports_voice = true,
                    max_resolution = "1920x1080",
                    supported_codecs = new[] { "H264" },
                    gpu_info = SystemInfo.graphicsDeviceName
                }
            };
            
            var response = await PostAsync<RegisterResponse>("/v1/render/register", request);
            
            if (response != null)
            {
                _authToken = response.auth_token;
                _isRegistered = true;
                Debug.Log($"[EventBridge] Registered as {_renderServerId}");
                
                // Start heartbeat
                HeartbeatLoop().Forget();
            }
        }
        
        public async UniTask<SessionInfo> GetSessionInfo(string sessionId)
        {
            var response = await GetAsync<SessionInfo>($"/v1/stream/sessions/{sessionId}");
            return response;
        }
        
        public async UniTask SendEvent(string sessionId, string eventType, object payload)
        {
            if (string.IsNullOrEmpty(sessionId)) return;
            
            var evt = new RuntimeEvent
            {
                session_id = sessionId,
                event_type = eventType,
                payload = JsonConvert.SerializeObject(payload),
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                server_id = _renderServerId
            };
            
            await PostAsync<object>("/v1/stream/events", evt);
        }
        
        public async UniTask SendInput(string sessionId, InputPacket input)
        {
            if (string.IsNullOrEmpty(sessionId)) return;
            
            await PostAsync<object>($"/v1/stream/sessions/{sessionId}/input", input);
        }
        
        public async UniTask SendIceCandidate(string sessionId, RTCIceCandidate candidate)
        {
            if (string.IsNullOrEmpty(sessionId)) return;
            
            var ice = new IceCandidateMessage
            {
                session_id = sessionId,
                candidate = candidate.candidate,
                sdp_mid = candidate.sdpMid,
                sdp_mline_index = candidate.sdpMLineIndex
            };
            
            await PostAsync<object>($"/v1/stream/sessions/{sessionId}/candidate", ice);
        }
        
        private async UniTaskVoid HeartbeatLoop()
        {
            while (_isRegistered)
            {
                await UniTask.Delay(TimeSpan.FromSeconds(_heartbeatInterval));
                
                if (!_isRegistered) break;
                
                await SendHeartbeat();
            }
        }
        
        private async UniTask SendHeartbeat()
        {
            var heartbeat = new HeartbeatMessage
            {
                server_id = _renderServerId,
                status = "healthy",
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds(),
                metrics = PerformanceManager.Instance?.GetMetrics()
            };
            
            await PostAsync<object>("/v1/render/heartbeat", heartbeat);
        }
        
        // HTTP Helpers
        private async UniTask<T> GetAsync<T>(string path)
        {
            using (var request = UnityWebRequest.Get(_backendUrl + path))
            {
                request.SetRequestHeader("Authorization", $"Bearer {_authToken}");
                request.SetRequestHeader("Content-Type", "application/json");
                
                await request.SendWebRequest();
                
                if (request.result == UnityWebRequest.Result.Success)
                {
                    return JsonConvert.DeserializeObject<T>(request.downloadHandler.text);
                }
                else
                {
                    Debug.LogWarning($"[EventBridge] GET {path} failed: {request.error}");
                    return default;
                }
            }
        }
        
        private async UniTask<T> PostAsync<T>(string path, object data)
        {
            var json = JsonConvert.SerializeObject(data);
            var bytes = System.Text.Encoding.UTF8.GetBytes(json);
            
            using (var request = new UnityWebRequest(_backendUrl + path, "POST"))
            {
                request.uploadHandler = new UploadHandlerRaw(bytes);
                request.downloadHandler = new DownloadHandlerBuffer();
                request.SetRequestHeader("Authorization", $"Bearer {_authToken}");
                request.SetRequestHeader("Content-Type", "application/json");
                
                await request.SendWebRequest();
                
                if (request.result == UnityWebRequest.Result.Success)
                {
                    if (request.downloadHandler.text.Length > 0)
                        return JsonConvert.DeserializeObject<T>(request.downloadHandler.text);
                    return default;
                }
                else
                {
                    Debug.LogWarning($"[EventBridge] POST {path} failed: {request.error}");
                    return default;
                }
            }
        }
    }
    
    [System.Serializable]
    public class RegisterRequest
    {
        public string server_id;
        public ServerCapabilities capabilities;
    }
    
    [System.Serializable]
    public class ServerCapabilities
    {
        public int max_sessions;
        public bool supports_hand_tracking;
        public bool supports_voice;
        public string max_resolution;
        public string[] supported_codecs;
        public string gpu_info;
    }
    
    [System.Serializable]
    public class RegisterResponse
    {
        public string auth_token;
        public string server_id;
    }
    
    [System.Serializable]
    public class SessionInfo
    {
        public string id;
        public int project_id;
        public int user_id;
        public string device_info;
        public string status;
        public string scene_package_url;
    }
    
    [System.Serializable]
    public class RuntimeEvent
    {
        public string session_id;
        public string event_type;
        public string payload;
        public long timestamp;
        public string server_id;
    }
    
    [System.Serializable]
    public class IceCandidateMessage
    {
        public string session_id;
        public string candidate;
        public string sdp_mid;
        public int sdp_mline_index;
    }
    
    [System.Serializable]
    public class HeartbeatMessage
    {
        public string server_id;
        public string status;
        public long timestamp;
        public PerformanceManager.PerformanceMetrics metrics;
    }
}