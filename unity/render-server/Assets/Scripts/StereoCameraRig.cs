using System.Collections.Generic;
using UnityEngine;

namespace Cymatic
{
    /// <summary>
    /// Stereo camera rig for true stereo rendering.
    /// Left and right eye cameras with configurable IPD.
    /// Head pose driven by phone orientation.
    /// </summary>
    public class StereoCameraRig : MonoBehaviour
    {
        [Header("Camera Settings")]
        [SerializeField] private Camera _leftCamera;
        [SerializeField] private Camera _rightCamera;
        [SerializeField] private float _ipd = 0.064f; // 64mm default
        [SerializeField] private int _renderWidth = 1920;
        [SerializeField] private int _renderHeight = 1080;
        [SerializeField] private float _nearClip = 0.1f;
        [SerializeField] private float _farClip = 1000f;
        [SerializeField] private float _fov = 90f;
        
        [Header("Tracking")]
        [SerializeField] private Transform _headAnchor;
        [SerializeField] private bool _useHeadTracking = true;
        
        // Navigation
        private List<NavigationPointData> _navigationPoints = new List<NavigationPointData>();
        private int _currentNavIndex = 0;
        
        // Head pose
        private Vector3 _headPosition = Vector3.zero;
        private Quaternion _headRotation = Quaternion.identity;
        private Vector3 _smoothedPosition = Vector3.zero;
        private Quaternion _smoothedRotation = Quaternion.identity;
        [SerializeField] private float _positionSmoothing = 10f;
        [SerializeField] private float _rotationSmoothing = 15f;
        
        public Camera LeftCamera => _leftCamera;
        public Camera RightCamera => _rightCamera;
        public float IPD => _ipd;
        public Vector3 HeadPosition => _smoothedPosition;
        public Quaternion HeadRotation => _smoothedRotation;
        public IReadOnlyList<NavigationPointData> NavigationPoints => _navigationPoints;
        
        private void Awake()
        {
            if (_leftCamera == null || _rightCamera == null)
            {
                CreateCameras();
            }
            
            if (_headAnchor == null)
            {
                _headAnchor = new GameObject("HeadAnchor").transform;
                _headAnchor.SetParent(transform);
                _headAnchor.localPosition = Vector3.zero;
            }
        }
        
        private void CreateCameras()
        {
            // Left camera
            var leftGO = new GameObject("LeftCamera");
            leftGO.transform.SetParent(transform);
            _leftCamera = leftGO.AddComponent<Camera>();
            _leftCamera.stereoTargetEye = StereoTargetEyeMask.Left;
            
            // Right camera
            var rightGO = new GameObject("RightCamera");
            rightGO.transform.SetParent(transform);
            _rightCamera = rightGO.AddComponent<Camera>();
            _rightCamera.stereoTargetEye = StereoTargetEyeMask.Right;
        }
        
        public void Configure(float ipd, int width, int height)
        {
            _ipd = ipd / 1000f; // Convert mm to meters
            _renderWidth = width;
            _renderHeight = height;
            
            ConfigureCamera(_leftCamera);
            ConfigureCamera(_rightCamera);
            
            // Position cameras for IPD
            _leftCamera.transform.localPosition = new Vector3(-_ipd / 2f, 0, 0);
            _rightCamera.transform.localPosition = new Vector3(_ipd / 2f, 0, 0);
        }
        
        private void ConfigureCamera(Camera cam)
        {
            cam.nearClipPlane = _nearClip;
            cam.farClipPlane = _farClip;
            cam.fieldOfView = _fov;
            cam.aspect = (float)_renderWidth / _renderHeight;
            cam.useOcclusionCulling = true;
            cam.allowHDR = true;
            cam.allowMSAA = true;
        }
        
        private void LateUpdate()
        {
            if (!_useHeadTracking) return;
            
            // Smooth head pose
            _smoothedPosition = Vector3.Lerp(_smoothedPosition, _headPosition, Time.deltaTime * _positionSmoothing);
            _smoothedRotation = Quaternion.Slerp(_smoothedRotation, _headRotation, Time.deltaTime * _rotationSmoothing);
            
            // Apply to head anchor
            _headAnchor.position = _smoothedPosition;
            _headAnchor.rotation = _smoothedRotation;
            
            // Cameras follow head anchor
            transform.position = _headAnchor.position;
            transform.rotation = _headAnchor.rotation;
        }
        
        public void UpdateHeadPose(Vector3 position, Quaternion rotation)
        {
            _headPosition = position;
            _headRotation = rotation;
        }
        
        public void SetNavigationPoints(List<NavigationPointData> points)
        {
            _navigationPoints = points;
            _currentNavIndex = 0;
        }
        
        public void TeleportToNavigationPoint(int index)
        {
            if (index < 0 || index >= _navigationPoints.Count) return;
            
            var point = _navigationPoints[index];
            _headPosition = point.position;
            _headRotation = Quaternion.Euler(0, point.rotation.y, 0);
            _smoothedPosition = _headPosition;
            _smoothedRotation = _headRotation;
            _currentNavIndex = index;
        }
        
        public NavigationPointData GetCurrentNavigationPoint()
        {
            if (_currentNavIndex >= 0 && _currentNavIndex < _navigationPoints.Count)
                return _navigationPoints[_currentNavIndex];
            return null;
        }
        
        public NavigationPointData GetNextNavigationPoint()
        {
            int next = (_currentNavIndex + 1) % _navigationPoints.Count;
            return _navigationPoints[next];
        }
        
        public NavigationPointData GetPreviousNavigationPoint()
        {
            int prev = (_currentNavIndex - 1 + _navigationPoints.Count) % _navigationPoints.Count;
            return _navigationPoints[prev];
        }
        
        // Render textures for WebRTC
        public RenderTexture GetLeftEyeTexture()
        {
            if (_leftCamera.targetTexture == null)
            {
                _leftCamera.targetTexture = new RenderTexture(_renderWidth, _renderHeight, 24, RenderTextureFormat.ARGB32);
                _leftCamera.targetTexture.antiAliasing = 2;
            }
            return _leftCamera.targetTexture;
        }
        
        public RenderTexture GetRightEyeTexture()
        {
            if (_rightCamera.targetTexture == null)
            {
                _rightCamera.targetTexture = new RenderTexture(_renderWidth, _renderHeight, 24, RenderTextureFormat.ARGB32);
                _rightCamera.targetTexture.antiAliasing = 2;
            }
            return _rightCamera.targetTexture;
        }
        
        // Side-by-side stereo rendering
        public RenderTexture GetSideBySideTexture()
        {
            var leftTex = GetLeftEyeTexture();
            var rightTex = GetRightEyeTexture();
            
            // Create combined texture if needed
            var combined = new RenderTexture(_renderWidth * 2, _renderHeight, 24, RenderTextureFormat.ARGB32);
            
            // Blit left eye to left half
            Graphics.Blit(leftTex, combined, new Rect(0, 0, 0.5f, 1));
            // Blit right eye to right half
            Graphics.Blit(rightTex, combined, new Rect(0.5f, 0, 0.5f, 1));
            
            return combined;
        }
    }
    
    [System.Serializable]
    public class NavigationPointData
    {
        public string id;
        public string name;
        public Vector3 position;
        public string description;
        public List<string> connections;
        public Vector3 rotation; // Euler angles
    }
}