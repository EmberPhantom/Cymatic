using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using UnityEngine;
using Newtonsoft.Json;

namespace Cymatic
{
    public partial class InputManager : MonoBehaviour
    {
        public enum HandGesture
        {
            None, Pinch, Fist, OpenPalm, Point,
            SwipeLeft, SwipeRight, SwipeUp, SwipeDown
        }

        [Serializable]
        public class InputPacket
        {
            public string input_type;
            public Dictionary<string, object> payload;
            public long timestamp;
        }

        public event Action<string> OnCopilotMessage;
        public event Action<Vector3, Quaternion> OnHeadPoseReceived;
        public event Action<Dictionary<string, object>> OnControllerInput;
        public event Action<Vector3, Quaternion> OnGazeInput;
        public event Action<string> OnVoiceCommand;
        public event Action<string> OnTextCommand;
        public event Action<Dictionary<string, object>> OnHandTracking;

        private ConcurrentQueue<InputPacket> _packetQueue = new ConcurrentQueue<InputPacket>();
        private bool _isProcessing;

        public bool HasHeadPose { get; private set; }
        public Vector3 HeadPosition { get; private set; }
        public Quaternion HeadRotation { get; private set; }

        public void StartProcessing() => _isProcessing = true;
        public void StopProcessing() => _isProcessing = false;

        public InputPacket GetInputPacket()
        {
            return _packetQueue.TryDequeue(out var packet) ? packet : null;
        }

        /// <summary>
        /// Drain all queued packets (for coalescing). Replaces per-frame single dequeues.
        /// </summary>
        public List<InputPacket> DrainQueue()
        {
            var list = new List<InputPacket>();
            while (_packetQueue.TryDequeue(out var p))
                list.Add(p);
            return list;
        }

        public int PendingCount => _packetQueue.Count;

        /// <summary>
        /// Coalesce packets: keep only latest per input_type to avoid 60Hz spam.
        /// </summary>
        public List<InputPacket> GetCoalescedPackets()
        {
            var all = DrainQueue();
            if (all.Count <= 1) return all;
            var latest = new Dictionary<string, InputPacket>();
            foreach (var p in all)
            {
                if (p == null || string.IsNullOrEmpty(p.input_type)) continue;
                latest[p.input_type] = p; // overwrite keeps latest
            }
            return new List<InputPacket>(latest.Values);
        }

        public void HandleInputMessage(string json)
        {
            if (!_isProcessing) return;
            try
            {
                var packet = JsonConvert.DeserializeObject<InputPacket>(json);
                if (packet != null)
                {
                    _packetQueue.Enqueue(packet);
                    DispatchPacket(packet);
                }
            }
            catch (Exception e)
            {
                Debug.LogWarning($"[InputManager] Failed to parse input: {e.Message}");
            }
        }

        public void HandleVoiceCommand(string transcript)
        {
            Debug.Log($"[InputManager] Voice command: {transcript}");
            _packetQueue.Enqueue(new InputPacket
            {
                input_type = "voice",
                payload = new Dictionary<string, object> { { "transcript", transcript } },
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            });
            OnVoiceCommand?.Invoke(transcript);
            OnCopilotMessage?.Invoke(transcript);
        }

        public void HandleTextCommand(string text)
        {
            Debug.Log($"[InputManager] Text command: {text}");
            _packetQueue.Enqueue(new InputPacket
            {
                input_type = "text",
                payload = new Dictionary<string, object> { { "text", text } },
                timestamp = DateTimeOffset.UtcNow.ToUnixTimeMilliseconds()
            });
            OnTextCommand?.Invoke(text);
            OnCopilotMessage?.Invoke(text);
        }

        private void DispatchPacket(InputPacket packet)
        {
            switch (packet.input_type)
            {
                case "head_pose":
                    if (packet.payload != null)
                    {
                        HasHeadPose = true;
                        HeadPosition = GetVector3(packet.payload, "position");
                        HeadRotation = GetQuaternion(packet.payload, "rotation");
                        OnHeadPoseReceived?.Invoke(HeadPosition, HeadRotation);
                    }
                    break;
                case "controller":
                    OnControllerInput?.Invoke(packet.payload);
                    break;
                case "gaze":
                    if (packet.payload != null)
                    {
                        var pos = GetVector3(packet.payload, "position");
                        var rot = GetQuaternion(packet.payload, "rotation");
                        OnGazeInput?.Invoke(pos, rot);
                    }
                    break;
                case "hand_tracking":
                    OnHandTracking?.Invoke(packet.payload);
                    break;
            }
        }

        private Vector3 GetVector3(Dictionary<string, object> d, string key)
        {
            if (d.TryGetValue(key, out var val) && val is List<object> list && list.Count >= 3)
                return new Vector3(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]), Convert.ToSingle(list[2]));
            return Vector3.zero;
        }

        private Quaternion GetQuaternion(Dictionary<string, object> d, string key)
        {
            if (d.TryGetValue(key, out var val) && val is List<object> list && list.Count >= 4)
                return new Quaternion(Convert.ToSingle(list[0]), Convert.ToSingle(list[1]), Convert.ToSingle(list[2]), Convert.ToSingle(list[3]));
            return Quaternion.identity;
        }
    }
}
