// Central stub for Unity.WebRTC when package not present (allows CI/syntax check compile)
// Mirrors real com.unity.webrtc 3.0.0-pre.8 API signatures with overloads for compatibility
#if !UNITY_WEBRTC
using System.Collections.Generic;
using UnityEngine;
using Cysharp.Threading.Tasks;

namespace Unity.WebRTC
{
    public enum RTCSdpType { Offer, Answer, PrAnswer, Rollback }
    public enum RTCPeerConnectionState { New, Connecting, Connected, Disconnected, Failed, Closed }
    public enum RTCErrorType { None, InvalidState, InvalidModification, NetworkError, InternalError }
    public struct RTCSessionDescription
    {
        public RTCSdpType type;
        public string sdp;
    }
    public struct RTCIceCandidateInit
    {
        public string candidate;
        public string sdpMid;
        public int sdpMLineIndex;
        public string usernameFragment;
    }
    public class RTCIceCandidate
    {
        public string Candidate => candidate;
        public string SdpMid => sdpMid;
        public int SdpMLineIndex => sdpMLineIndex;
        // Stub fields for simple initializer used in fallback code
        public string candidate;
        public string sdpMid;
        public int sdpMLineIndex;
        public string usernameFragment;
        public RTCIceCandidate(RTCIceCandidateInit init) { candidate = init.candidate; sdpMid = init.sdpMid; sdpMLineIndex = init.sdpMLineIndex; usernameFragment = init.usernameFragment; }
        public RTCIceCandidate() {}
    }
    public class RTCIceServer { public string[] urls; public string username; public string credential; }
    public struct RTCConfiguration
    {
        public RTCIceServer[] iceServers;
        public object bundlePolicy;
        public object rtcpMuxPolicy;
    }
    // Async operation stubs that mimic Unity's operations
    public class RTCSessionDescriptionAsyncOperation : CustomYieldInstruction
    {
        public bool IsDone => true;
        public bool IsError => false;
        public string Error => "";
        public RTCSessionDescription Desc => new RTCSessionDescription { type = RTCSdpType.Answer, sdp = "v=0\r\n" };
        public override bool keepWaiting => false;
    }
    public class RTCSetSessionDescriptionAsyncOperation : CustomYieldInstruction
    {
        public bool IsDone => true;
        public bool IsError => false;
        public string Error => "";
        public override bool keepWaiting => false;
    }

    public class RTCPeerConnection : System.IDisposable
    {
        public RTCPeerConnection() {}
        public RTCPeerConnection(RTCConfiguration config) {}
        public RTCPeerConnection(ref RTCConfiguration config) {}
        public System.Action<RTCIceCandidate> OnIceCandidate;
        public System.Action<RTCPeerConnectionState> OnConnectionStateChange;
        public System.Action<RTCPeerConnectionState> OnIceConnectionChange;
        // Real API returns operation, stub returns operation-like but awaitable via UniTask
        public RTCSessionDescriptionAsyncOperation CreateOffer() => new RTCSessionDescriptionAsyncOperation();
        public RTCSessionDescriptionAsyncOperation CreateOffer(ref RTCOfferAnswerOptions options) => new RTCSessionDescriptionAsyncOperation();
        public RTCSessionDescriptionAsyncOperation CreateAnswer() => new RTCSessionDescriptionAsyncOperation();
        public RTCSessionDescriptionAsyncOperation CreateAnswer(ref RTCOfferAnswerOptions options) => new RTCSessionDescriptionAsyncOperation();
        // Provide UniTask version for fallback code
        public UniTask<RTCSessionDescription> CreateAnswerUniTask() => UniTask.FromResult(new RTCSessionDescription{ sdp = "v=0\r\n", type = RTCSdpType.Answer });
        public RTCSetSessionDescriptionAsyncOperation SetLocalDescription(ref RTCSessionDescription desc) => new RTCSetSessionDescriptionAsyncOperation();
        public RTCSetSessionDescriptionAsyncOperation SetRemoteDescription(ref RTCSessionDescription desc) => new RTCSetSessionDescriptionAsyncOperation();
        // Overloads without ref for compatibility with earlier code
        public UniTask SetLocalDescription(RTCSessionDescription desc) => UniTask.CompletedTask;
        public UniTask SetRemoteDescription(RTCSessionDescription desc) => UniTask.CompletedTask;
        public UniTask AddIceCandidate(RTCIceCandidate c) => UniTask.CompletedTask;
        public bool AddIceCandidate(RTCIceCandidate candidate, out string error) { error = ""; return true; }
        public RTCRtpTransceiver AddTransceiver(UnityEngine.Texture track) => new RTCRtpTransceiver();
        public RTCRtpTransceiver AddTransceiver(VideoStreamTrack t) => new RTCRtpTransceiver();
        public RTCRtpTransceiver AddTransceiver(TrackKind kind) => new RTCRtpTransceiver();
        public List<RTCRtpTransceiver> GetTransceivers() => new List<RTCRtpTransceiver>{ new RTCRtpTransceiver() };
        public RTCSessionDescription LocalDescription => new RTCSessionDescription();
        public RTCSessionDescription RemoteDescription => new RTCSessionDescription();
        public void Close() {}
        public void Dispose() {}
    }
    public struct RTCOfferAnswerOptions { public bool voiceActivityDetection; public bool iceRestart; }
    public struct RTCAnswerOptions {}
    public enum TrackKind { Audio, Video }
    public class VideoStreamTrack : System.IDisposable
    {
        public VideoStreamTrack() {}
        public VideoStreamTrack(int w,int h,int fps) {}
        public VideoStreamTrack(UnityEngine.Texture tex) {}
        public VideoStreamTrack(string label) {}
        public void Dispose() {}
    }
    public class RTCRtpTransceiver { public RTCRtpSender Sender => new RTCRtpSender(); public RTCRtpTransceiverDirection Direction; public RTCRtpTransceiverInit Init; }
    public enum RTCRtpTransceiverDirection { SendRecv, SendOnly, RecvOnly, Inactive, Stopped }
    public struct RTCRtpTransceiverInit { public RTCRtpTransceiverDirection direction; }
    public class RTCRtpSender { public RTCRtpParameters GetParameters() => new RTCRtpParameters(); public void SetParameters(RTCRtpParameters p) {} public static RTCRtpCapabilities GetCapabilities(TrackKind kind) => new RTCRtpCapabilities(); }
    public class RTCRtpCapabilities { public RTCRtpCodecCapability[] codecs => new RTCRtpCodecCapability[0]; }
    public class RTCRtpCodecCapability { public string mimeType; public uint clockRate; public uint channels; }
    public class RTCRtpParameters { public List<RTCRtpEncoding> Encodings = new List<RTCRtpEncoding>{ new RTCRtpEncoding() }; public string transactionId; }
    public class RTCRtpEncoding { public double? BitratePriority; public uint? MinBitrate; public uint? MaxBitrate; public double? ScaleResolutionDownBy; public bool? active; }
    public enum RTCErrorType2 { None }
}
#endif
