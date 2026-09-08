using System;
using System.Collections.Generic;
using System.IO;
using System.Text;
using UnityEngine;
using UnityEngine.Networking;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json;

namespace Cymatic
{
    /// <summary>
    /// Signaling Client - WebSocket connection for WebRTC signaling.
    /// </summary>
    public class SignalingClient : MonoBehaviour
    {
        [Header("Configuration")]
        [SerializeField] private string _signalingUrl = "ws://localhost:8080/ws";
        [SerializeField] private float _reconnectInterval = 5f;
        [SerializeField] private float _pingInterval = 10f;
        
        // WebSocket
        private WebSocket _webSocket;
        private bool _isConnected = false;
        private bool _shouldReconnect = true;
        
        // Message handlers
        public event Action<string, string> OnOfferReceived; // sessionId, sdp
        public event Action<string, string> OnAnswerReceived; // sessionId, sdp
        public event Action<string, string, string, int> OnCandidateReceived; // sessionId, candidate, sdpMid, sdpMLineIndex
        public event Action<string, InputManager.InputPacket> OnInputReceived; // sessionId, input
        public event Action<string> OnSessionEnded; // sessionId
        public event Action OnConnected;
        public event Action OnDisconnected;
        
        // Pending requests
        private Dictionary<string, Action<string>> _pendingRequests = new Dictionary<string, Action<string>>();
        private int _requestId = 0;
        
        public bool IsConnected => _isConnected;
        
        public void Configure(string url)
        {
            _signalingUrl = url;
        }
        
        public async UniTask Connect()
        {
            if (_isConnected) return;
            
            _shouldReconnect = true;
            await ConnectWebSocket();
        }
        
        private async UniTask ConnectWebSocket()
        {
            try
            {
                _webSocket = new WebSocket();
                _webSocket.OnOpen += OnWebSocketOpen;
                _webSocket.OnMessage += OnWebSocketMessage;
                _webSocket.OnError += OnWebSocketError;
                _webSocket.OnClose += OnWebSocketClose;
                
                await _webSocket.Connect(_signalingUrl);
            }
            catch (Exception e)
            {
                Debug.LogError($"[Signaling] Connection failed: {e.Message}");
                await ScheduleReconnect();
            }
        }
        
        private void OnWebSocketOpen()
        {
            _isConnected = true;
            Debug.Log("[Signaling] Connected");
            OnConnected?.Invoke();
            
            // Register as render server - P0 FIX: 79 server_id should use RenderServerId not gameObject.name
            string serverId = "render-server-01";
            try
            {
                if (RenderServer.Instance != null)
                {
                    // Use RenderServerId if available, fallback to configured id
                    serverId = RenderServer.Instance.RenderServerId;
                    if (string.IsNullOrEmpty(serverId))
                        serverId = RenderServer.Instance.gameObject.name;
                }
            }
            catch {}
            
            Send(new SignalingMessage
            {
                type = "register",
                payload = new RegisterPayload
                {
                    server_id = serverId,
                    type = "render_server"
                }
            });
            
            // Start ping
            PingLoop().Forget();
        }
        
        private void OnWebSocketMessage(string message)
        {
            try
            {
                var msg = JsonConvert.DeserializeObject<SignalingMessage>(message);
                HandleMessage(msg);
            }
            catch (Exception e)
            {
                Debug.LogError($"[Signaling] Failed to parse message: {e.Message}");
            }
        }
        
        private void HandleMessage(SignalingMessage msg)
        {
            if (msg == null) return;
            switch (msg.type)
            {
                case "offer":
                    var offerPayload = JsonConvert.DeserializeObject<OfferPayload>(msg.payload.ToString());
                    OnOfferReceived?.Invoke(offerPayload.session_id, offerPayload.sdp);
                    break;
                    
                case "answer":
                    var answerPayload = JsonConvert.DeserializeObject<AnswerPayload>(msg.payload.ToString());
                    OnAnswerReceived?.Invoke(answerPayload.session_id, answerPayload.sdp);
                    break;
                    
                case "candidate":
                    var candidatePayload = JsonConvert.DeserializeObject<CandidatePayload>(msg.payload.ToString());
                    OnCandidateReceived?.Invoke(candidatePayload.session_id, candidatePayload.candidate, candidatePayload.sdp_mid, candidatePayload.sdp_mline_index);
                    break;
                    
                case "input":
                    var inputPayload = JsonConvert.DeserializeObject<InputPayload>(msg.payload.ToString());
                    OnInputReceived?.Invoke(inputPayload.session_id, inputPayload.input);
                    break;
                    
                case "end_session":
                    var endPayload = JsonConvert.DeserializeObject<EndSessionPayload>(msg.payload.ToString());
                    OnSessionEnded?.Invoke(endPayload.session_id);
                    break;
                    
                case "response":
                    HandleResponse(msg);
                    break;
                    
                case "ping":
                    Send(new SignalingMessage { type = "pong", id = msg.id });
                    break;
            }
        }
        
        private void HandleResponse(SignalingMessage msg)
        {
            if (msg == null || string.IsNullOrEmpty(msg.id)) return;
            if (_pendingRequests.TryGetValue(msg.id, out var callback))
            {
                _pendingRequests.Remove(msg.id);
                callback?.Invoke(msg.payload?.ToString());
            }
        }
        
        private void OnWebSocketError(string error)
        {
            Debug.LogError($"[Signaling] Error: {error}");
        }
        
        private void OnWebSocketClose(int code, string reason)
        {
            _isConnected = false;
            Debug.Log($"[Signaling] Disconnected: {code} - {reason}");
            OnDisconnected?.Invoke();
            
            if (_shouldReconnect)
            {
                ScheduleReconnect().Forget();
            }
        }
        
        private async UniTaskVoid ScheduleReconnect()
        {
            await UniTask.Delay(TimeSpan.FromSeconds(_reconnectInterval));
            if (_shouldReconnect && !_isConnected)
            {
                await ConnectWebSocket();
            }
        }
        
        private async UniTaskVoid PingLoop()
        {
            while (_isConnected)
            {
                await UniTask.Delay(TimeSpan.FromSeconds(_pingInterval));
                if (_isConnected)
                {
                    Send(new SignalingMessage { type = "ping", id = GenerateId() });
                }
            }
        }
        
        public void Send(SignalingMessage message)
        {
            if (!_isConnected || _webSocket == null) return;
            
            if (string.IsNullOrEmpty(message.id))
                message.id = GenerateId();
            
            var json = JsonConvert.SerializeObject(message);
            _webSocket.Send(json);
        }
        
        public void SendOffer(string sessionId, string sdp)
        {
            Send(new SignalingMessage
            {
                type = "offer",
                payload = new OfferPayload { session_id = sessionId, sdp = sdp }
            });
        }
        
        public void SendAnswer(string sessionId, string sdp)
        {
            Send(new SignalingMessage
            {
                type = "answer",
                payload = new AnswerPayload { session_id = sessionId, sdp = sdp }
            });
        }
        
        public void SendIceCandidate(string sessionId, string candidate, string sdpMid, int sdpMLineIndex)
        {
            Send(new SignalingMessage
            {
                type = "candidate",
                payload = new CandidatePayload
                {
                    session_id = sessionId,
                    candidate = candidate,
                    sdp_mid = sdpMid,
                    sdp_mline_index = sdpMLineIndex
                }
            });
        }
        
        public void SendInput(string sessionId, InputManager.InputPacket input)
        {
            Send(new SignalingMessage
            {
                type = "input",
                payload = new InputPayload { session_id = sessionId, input = input }
            });
        }
        
        public void Disconnect()
        {
            _shouldReconnect = false;
            if (_webSocket != null)
            {
                _webSocket.Close();
                _webSocket = null;
            }
            _isConnected = false;
        }
        
        private string GenerateId()
        {
            return $"{++_requestId}_{Guid.NewGuid().ToString("N")[..8]}";
        }
        
        private void OnDestroy()
        {
            Disconnect();
        }
    }
    
    [System.Serializable]
    public class SignalingMessage
    {
        public string id;
        public string type;
        public object payload;
    }
    
    [System.Serializable]
    public class RegisterPayload
    {
        public string server_id;
        public string type;
    }
    
    [System.Serializable]
    public class OfferPayload
    {
        public string session_id;
        public string sdp;
    }
    
    [System.Serializable]
    public class AnswerPayload
    {
        public string session_id;
        public string sdp;
    }
    
    [System.Serializable]
    public class CandidatePayload
    {
        public string session_id;
        public string candidate;
        public string sdp_mid;
        public int sdp_mline_index;
    }
    
    [System.Serializable]
    public class InputPayload
    {
        public string session_id;
        public InputManager.InputPacket input;
    }
    
    [System.Serializable]
    public class EndSessionPayload
    {
        public string session_id;
    }
}

// Simple WebSocket wrapper for Unity - P0 FIX: buffer truncation + Send Forget
public class WebSocket
{
    public event Action OnOpen;
    public event Action<string> OnMessage;
    public event Action<string> OnError;
    public event Action<int, string> OnClose;
    
    private System.Net.WebSockets.ClientWebSocket _ws;
    private System.Threading.CancellationTokenSource _cts;
    private bool _isConnected = false;
    
    public async Cysharp.Threading.Tasks.UniTask Connect(string url)
    {
        _ws = new System.Net.WebSockets.ClientWebSocket();
        _cts = new System.Threading.CancellationTokenSource();
        
        await _ws.ConnectAsync(new Uri(url), _cts.Token);
        _isConnected = true;
        
        OnOpen?.Invoke();
        
        // Start receiving
        ReceiveLoop().Forget();
    }
    
    private async Cysharp.Threading.Tasks.UniTaskVoid ReceiveLoop()
    {
        // P0 FIX: 347 buffer 4096 truncation -> use larger buffer and handle fragmentation via MemoryStream
        var buffer = new byte[16384];
        var messageStream = new MemoryStream();
        
        while (_isConnected && _cts != null && !_cts.Token.IsCancellationRequested)
        {
            try
            {
                var segment = new ArraySegment<byte>(buffer);
                var result = await _ws.ReceiveAsync(segment, _cts.Token);
                
                if (result.MessageType == System.Net.WebSockets.WebSocketMessageType.Close)
                {
                    await CloseAsync(System.Net.WebSockets.WebSocketCloseStatus.NormalClosure, "Closed by server");
                    break;
                }

                // Write fragment to stream
                messageStream.Write(buffer, 0, result.Count);

                // Only process when EndOfMessage is true (handles truncation for >16k messages via concatenation)
                if (!result.EndOfMessage)
                {
                    // Continue to next fragment; if message exceeds 16k, we will keep appending
                    // Expand if needed: if messageStream length approaches buffer, we continue accumulating
                    continue;
                }

                // Complete message assembled
                var messageBytes = messageStream.ToArray();
                messageStream.SetLength(0);
                messageStream.Position = 0;

                var message = System.Text.Encoding.UTF8.GetString(messageBytes, 0, messageBytes.Length);
                OnMessage?.Invoke(message);
            }
            catch (Exception e)
            {
                // Check if cancellation
                if (_cts != null && _cts.Token.IsCancellationRequested) break;
                OnError?.Invoke(e.Message);
                break;
            }
        }
        
        _isConnected = false;
        OnClose?.Invoke(0, "Disconnected");
        messageStream?.Dispose();
    }
    
    public void Send(string message)
    {
        if (!_isConnected || _ws == null) return;
        if (_cts == null || _cts.Token.IsCancellationRequested) return;
        
        var bytes = System.Text.Encoding.UTF8.GetBytes(message);
        var segment = new ArraySegment<byte>(bytes);
        // P0 FIX: 375 Send Forget -> avoid .Forget() on Task (no UniTask extension for Task)
        // Use discard to avoid warning and properly handle async without Forget
        try
        {
#if UNITY_WEBRTC
            // In Unity, use UniTask wrapper to allow Forget
            Cysharp.Threading.Tasks.UniTask.Create(async () =>
            {
                await _ws.SendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, _cts.Token);
            }).Forget();
#else
            // Non-Unity compile: fire-and-forget via Task
            _ = _ws.SendAsync(segment, System.Net.WebSockets.WebSocketMessageType.Text, true, _cts.Token);
#endif
        }
        catch (Exception e)
        {
            UnityEngine.Debug.LogWarning($"[WebSocket] Send failed: {e.Message}");
        }
    }
    
    public async Cysharp.Threading.Tasks.UniTask CloseAsync(System.Net.WebSockets.WebSocketCloseStatus status, string reason)
    {
        _isConnected = false;
        try { _cts?.Cancel(); } catch {}
        
        if (_ws != null)
        {
            try
            {
                if (_ws.State == System.Net.WebSockets.WebSocketState.Open || _ws.State == System.Net.WebSockets.WebSocketState.CloseReceived)
                    await _ws.CloseAsync(status, reason, System.Threading.CancellationToken.None);
            }
            catch {}
            try { _ws.Dispose(); } catch {}
            _ws = null;
        }
    }
    
    public void Close()
    {
        // P0 FIX: use UniTask Forget properly with CloseAsync
        CloseAsync(System.Net.WebSockets.WebSocketCloseStatus.NormalClosure, "Client closed").Forget();
    }
}
