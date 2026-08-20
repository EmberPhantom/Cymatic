using System;
using System.Collections.Generic;
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
            
            // Register as render server
            Send(new SignalingMessage
            {
                type = "register",
                payload = new RegisterPayload
                {
                    server_id = RenderServer.Instance?.gameObject.name ?? "render-server",
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

// Simple WebSocket wrapper for Unity
public class WebSocket
{
    public event Action OnOpen;
    public event Action<string> OnMessage;
    public event Action<string> OnError;
    public event Action<int, string> OnClose;
    
    private System.Net.WebSockets.ClientWebSocket _ws;
    private System.Threading.CancellationTokenSource _cts;
    private bool _isConnected = false;
    
    public async UniTask Connect(string url)
    {
        _ws = new System.Net.WebSockets.ClientWebSocket();
        _cts = new System.Threading.CancellationTokenSource();
        
        await _ws.ConnectAsync(new Uri(url), _cts.Token);
        _isConnected = true;
        
        OnOpen?.Invoke();
        
        // Start receiving
        ReceiveLoop().Forget();
    }
    
    private async UniTaskVoid ReceiveLoop()
    {
        var buffer = new byte[4096];
        
        while (_isConnected && !_cts.Token.IsCancellationRequested)
        {
            try
            {
                var result = await _ws.ReceiveAsync(new ArraySegment<byte>(buffer), _cts.Token);
                
                if (result.MessageType == System.Net.WebSockets.WebSocketMessageType.Close)
                {
                    await CloseAsync(System.Net.WebSockets.WebSocketCloseStatus.NormalClosure, "Closed by server");
                    break;
                }
                
                var message = System.Text.Encoding.UTF8.GetString(buffer, 0, result.Count);
                OnMessage?.Invoke(message);
            }
            catch (Exception e)
            {
                OnError?.Invoke(e.Message);
                break;
            }
        }
        
        _isConnected = false;
        OnClose?.Invoke(0, "Disconnected");
    }
    
    public void Send(string message)
    {
        if (!_isConnected || _ws == null) return;
        
        var bytes = System.Text.Encoding.UTF8.GetBytes(message);
        _ws.SendAsync(new ArraySegment<byte>(bytes), System.Net.WebSockets.WebSocketMessageType.Text, true, _cts.Token).Forget();
    }
    
    public async UniTask CloseAsync(System.Net.WebSockets.WebSocketCloseStatus status, string reason)
    {
        _isConnected = false;
        _cts?.Cancel();
        
        if (_ws != null)
        {
            await _ws.CloseAsync(status, reason, System.Threading.CancellationToken.None);
            _ws.Dispose();
            _ws = null;
        }
    }
    
    public void Close()
    {
        CloseAsync(System.Net.WebSockets.WebSocketCloseStatus.NormalClosure, "Client closed").Forget();
    }
}