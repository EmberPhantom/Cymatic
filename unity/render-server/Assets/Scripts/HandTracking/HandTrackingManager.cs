using System.Collections.Generic;
using UnityEngine;
using Cysharp.Threading.Tasks;

namespace Cymatic.HandTracking
{
    /// <summary>
    /// Hand Tracking Manager - Receives hand tracking data from Android client
    /// Renders virtual hands and handles gesture recognition
    /// </summary>
    public class HandTrackingManager : MonoBehaviour
    {
        [Header("Hand Models")]
        [SerializeField] private GameObject _leftHandPrefab;
        [SerializeField] private GameObject _rightHandPrefab;
        [SerializeField] private Material _handMaterial;
        [SerializeField] private Material _handHighlightMaterial;
        
        [Header("Settings")]
        [SerializeField] private bool _showHands = true;
        [SerializeField] private float _handScale = 1.0f;
        [SerializeField] private float _smoothingFactor = 10f;
        [SerializeField] private float _minConfidence = 0.5f;
        
        [Header("Gesture Visualization")]
        [SerializeField] private GameObject _pinchEffectPrefab;
        [SerializeField] private GameObject _pointEffectPrefab;
        [SerializeField] private GameObject _swipeEffectPrefab;
        
        // Hand instances
        private GameObject _leftHandInstance;
        private GameObject _rightHandInstance;
        
        // Hand data
        private HandData _leftHandData;
        private HandData _rightHandData;
        private bool _leftHandVisible = false;
        private bool _rightHandVisible = false;
        
        // Joint transforms
        private readonly Dictionary<string, Transform> _leftJoints = new Dictionary<string, Transform>();
        private readonly Dictionary<string, Transform> _rightJoints = new Dictionary<string, Transform>();
        
        // MediaPipe hand joint names (21 landmarks)
        private static readonly string[] JointNames = new[]
        {
            "wrist",
            "thumb_cmc", "thumb_mcp", "thumb_ip", "thumb_tip",
            "index_finger_mcp", "index_finger_pip", "index_finger_dip", "index_finger_tip",
            "middle_finger_mcp", "middle_finger_pip", "middle_finger_dip", "middle_finger_tip",
            "ring_finger_mcp", "ring_finger_pip", "ring_finger_dip", "ring_finger_tip",
            "pinky_finger_mcp", "pinky_finger_pip", "pinky_finger_dip", "pinky_finger_tip"
        };
        
        // Gesture state
        private InputManager.HandGesture _leftGesture = InputManager.HandGesture.None;
        private InputManager.HandGesture _rightGesture = InputManager.HandGesture.None;
        
        // Events
        public event System.Action<InputManager.HandGesture, bool> OnGestureDetected; // gesture, isLeftHand
        public event System.Action<Vector3, bool> OnPinchPosition; // position, isLeftHand
        public event System.Action<Vector3, Vector3, bool> OnPointDirection; // origin, direction, isLeftHand
        
        private void Awake()
        {
            InitializeHands();
        }
        
        private void InitializeHands()
        {
            if (_leftHandPrefab != null)
            {
                _leftHandInstance = Instantiate(_leftHandPrefab, transform);
                _leftHandInstance.name = "LeftHand";
                _leftHandInstance.SetActive(false);
                CacheJoints(_leftHandInstance, _leftJoints, true);
            }
            
            if (_rightHandPrefab != null)
            {
                _rightHandInstance = Instantiate(_rightHandPrefab, transform);
                _rightHandInstance.name = "RightHand";
                _rightHandInstance.SetActive(false);
                CacheJoints(_rightHandInstance, _rightJoints, false);
            }
        }
        
        private void CacheJoints(GameObject hand, Dictionary<string, Transform> jointDict, bool isLeft)
        {
            // Find all joint transforms in the hand hierarchy
            var joints = hand.GetComponentsInChildren<Transform>();
            foreach (var joint in joints)
            {
                var name = joint.name.ToLower();
                foreach (var jointName in JointNames)
                {
                    if (name.Contains(jointName.ToLower()))
                    {
                        jointDict[jointName] = joint;
                        break;
                    }
                }
            }
        }
        
        private void Update()
        {
            if (!_showHands) return;
            
            UpdateHandVisibility();
            UpdateHandPoses();
            UpdateGestureEffects();
        }
        
        private void UpdateHandVisibility()
        {
            var leftVisible = _leftHandData != null && _leftHandData.confidence >= _minConfidence;
            var rightVisible = _rightHandData != null && _rightHandData.confidence >= _minConfidence;
            
            if (_leftHandInstance != null)
                _leftHandInstance.SetActive(leftVisible && _showHands);
            if (_rightHandInstance != null)
                _rightHandInstance.SetActive(rightVisible && _showHands);
            
            _leftHandVisible = leftVisible;
            _rightHandVisible = rightVisible;
        }
        
        private void UpdateHandPoses()
        {
            if (_leftHandVisible && _leftHandData != null)
            {
                UpdateHandPose(_leftJoints, _leftHandData.landmarks, true);
                _leftHandInstance.transform.localScale = Vector3.one * _handScale;
            }
            
            if (_rightHandVisible && _rightHandData != null)
            {
                UpdateHandPose(_rightJoints, _rightHandData.landmarks, false);
                _rightHandInstance.transform.localScale = Vector3.one * _handScale;
            }
        }
        
        private void UpdateHandPose(Dictionary<string, Transform> joints, List<Vector3> landmarks, bool isLeft)
        {
            if (landmarks == null || landmarks.Count < 21) return;
            
            // Wrist position as root
            if (joints.TryGetValue("wrist", out var wrist))
            {
                wrist.localPosition = landmarks[0];
            }
            
            // Update each joint
            for (int i = 1; i < landmarks.Count && i < JointNames.Length; i++)
            {
                var jointName = JointNames[i];
                if (joints.TryGetValue(jointName, out var joint))
                {
                    joint.localPosition = landmarks[i];
                }
            }
            
            // Apply smoothing
            // In real implementation, would use lerp/slerp for smooth transitions
        }
        
        private void UpdateGestureEffects()
        {
            // Left hand gestures
            if (_leftGesture != InputManager.HandGesture.None)
            {
                HandleGestureEffect(_leftGesture, true, _leftHandData?.landmarks);
            }
            
            // Right hand gestures
            if (_rightGesture != InputManager.HandGesture.None)
            {
                HandleGestureEffect(_rightGesture, false, _rightHandData?.landmarks);
            }
        }
        
        private void HandleGestureEffect(InputManager.HandGesture gesture, bool isLeft, List<Vector3> landmarks)
        {
            Vector3 position = Vector3.zero;
            
            if (landmarks != null && landmarks.Count > 8) // Index tip
            {
                position = landmarks[8]; // Index tip
            }
            
            switch (gesture)
            {
                case InputManager.HandGesture.Pinch:
                    SpawnEffect(_pinchEffectPrefab, position, isLeft);
                    OnPinchPosition?.Invoke(position, isLeft);
                    break;
                    
                case InputManager.HandGesture.Point:
                    if (landmarks != null && landmarks.Count > 12) // Middle tip for direction
                    {
                        var direction = (landmarks[8] - landmarks[12]).normalized; // Index to middle
                        OnPointDirection?.Invoke(position, direction, isLeft);
                    }
                    SpawnEffect(_pointEffectPrefab, position, isLeft);
                    break;
                    
                case InputManager.HandGesture.SwipeLeft:
                case InputManager.HandGesture.SwipeRight:
                case InputManager.HandGesture.SwipeUp:
                case InputManager.HandGesture.SwipeDown:
                    SpawnEffect(_swipeEffectPrefab, position, isLeft);
                    break;
            }
            
            OnGestureDetected?.Invoke(gesture, isLeft);
        }
        
        private void SpawnEffect(GameObject prefab, Vector3 position, bool isLeft)
        {
            if (prefab == null) return;
            
            var effect = Instantiate(prefab, position, Quaternion.identity, transform);
            effect.transform.localScale = Vector3.one * 0.5f;
            Destroy(effect, 1f);
        }
        
        // Called from SignalingClient when hand data received
        public void SetLeftHandData(HandData data)
        {
            _leftHandData = data;
            _leftGesture = data.gesture;
        }
        
        public void SetRightHandData(HandData data)
        {
            _rightHandData = data;
            _rightGesture = data.gesture;
        }
        
        // Hand data structure (matches Android)
        [System.Serializable]
        public class HandData
        {
            public List<Vector3> landmarks = new List<Vector3>();
            public float confidence;
            public InputManager.HandGesture gesture;
            public Vector3? worldPosition;
        }
        
        // Public getters
        public bool IsLeftHandVisible => _leftHandVisible;
        public bool IsRightHandVisible => _rightHandVisible;
        public InputManager.HandGesture LeftGesture => _leftGesture;
        public InputManager.HandGesture RightGesture => _rightGesture;
        public bool IsAnyHandVisible => _leftHandVisible || _rightHandVisible;
        
        // Feature flag check
        public bool IsHandTrackingEnabled()
        {
            #if CYMATIC_HAND_TRACKING
            return true;
            #else
            return false;
            #endif
        }
    }
}