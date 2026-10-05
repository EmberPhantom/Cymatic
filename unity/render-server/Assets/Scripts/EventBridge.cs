using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Networking;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json;
using Unity.WebRTC;

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

        // Single-user MVP: there is no separate render-server identity/auth
        // system on the backend (no /v1/render/register endpoint exists). The
        // render server authenticates as the same user account the Android
        // headset belongs to, using a long-lived access token configured here.
        [Header("Auth (single-user MVP)")]
        [SerializeField] private string _userAccessToken = "";

        // State
        private bool _isRegistered = false;
        private string _authToken;

        // P0 Fix: expose auth token for CopilotAgent (was private)
        public string AuthToken => _authToken;
        public string GetAuthToken() => _authToken;
        public string RenderServerId => _renderServerId;

        public event Action<string, string, string> OnCommandReceived; // sessionId, command, payload

        public void Configure(string backendUrl, string renderServerId)
        {
            _backendUrl = backendUrl;
            _renderServerId = renderServerId;
        }

        /// <summary>
        /// There is no backend render-server registration endpoint (MVP is
        /// single-user, so no separate identity is needed). This just adopts
        /// the configured user access token and starts the heartbeat.
        /// </summary>
        public UniTask RegisterRenderServer()
        {
            if (string.IsNullOrEmpty(_userAccessToken))
            {
                Debug.LogError(
                    "[EventBridge] No user access token configured; render server " +
                    "cannot authenticate to the backend. Set it in the Inspector."
                );
                _isRegistered = false;
                return UniTask.CompletedTask;
            }

            _authToken = _userAccessToken;
            _isRegistered = true;
            Debug.Log($"[EventBridge] Using configured user access token as {_renderServerId}");

            // Note: no /v1/render/heartbeat endpoint exists on the backend yet
            // (there is no render-server fleet to health-check in single-user MVP),
            // so the heartbeat loop is intentionally not started here.
            return UniTask.CompletedTask;
        }

        public async UniTask<SessionInfo> GetSessionInfo(string sessionId)
        {
            var response = await GetAsync<SessionInfo>($"/v1/stream/sessions/{sessionId}");
            return response;
        }

        /// <summary>
        /// Polls for the caller's current pending/connecting/active session so the
        /// render server can discover which session to join (there is no push
        /// from the API — see docs/25 and RenderServer.SessionDiscoveryLoop).
        /// Returns null if none exists (404) or the request otherwise fails.
        /// </summary>
        public async UniTask<SessionInfo> GetActiveSession()
        {
            return await GetAsync<SessionInfo>("/v1/stream/sessions/active");
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

        public async UniTask SendInput(string sessionId, InputManager.InputPacket input)
        {
            if (string.IsNullOrEmpty(sessionId)) return;

            await PostAsync<object>($"/v1/stream/sessions/{sessionId}/input", input);
        }

        public async UniTask SendIceCandidate(string sessionId, Unity.WebRTC.RTCIceCandidate candidate)
        {
            if (string.IsNullOrEmpty(sessionId)) return;
            if (candidate == null) return;

            // P0 FIX: real Unity.WebRTC 3.0.0-pre.8 uses capital Candidate/SdpMid/SdpMLineIndex (nullable)
            var ice = new IceCandidateMessage
            {
                session_id = sessionId,
                candidate = candidate.Candidate,
                sdp_mid = candidate.SdpMid,
                sdp_mline_index = candidate.SdpMLineIndex ?? 0
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
                    // 404 is an expected, quiet result for polling endpoints like
                    // GetActiveSession (no session waiting yet) - don't spam warnings.
                    if (request.responseCode != 404)
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
    public class SessionInfo
    {
        public string id;
        public int project_id;
        public int user_id;
        public string device_info;
        public string status;
        public string scene_package_url;

        public string scenePackageUrl => scene_package_url;
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
