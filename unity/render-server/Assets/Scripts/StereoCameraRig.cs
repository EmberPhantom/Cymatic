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
        [SerializeField] private float _positionSmoothing = 30f;
        [SerializeField] private float _rotationSmoothing = 45f;

        // P0: cached material for blit (avoid per-frame alloc)
        private Material _blitMaterial;
        private Material BlitMaterial
        {
            get
            {
                if (_blitMaterial == null)
                {
                    var shader = Shader.Find("Unlit/Texture");
                    if (shader == null) shader = Shader.Find("Standard");
                    _blitMaterial = new Material(shader);
                    _blitMaterial.hideFlags = HideFlags.HideAndDontSave;
                }
                return _blitMaterial;
            }
        }
        
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
                // P0 FIX: 55 feedback loop - do NOT parent headAnchor to this transform
                // Parenting creates feedback: LateUpdate sets headAnchor.position then transform.position = headAnchor.position
                // If headAnchor is child, moving parent moves child again => loop/instability.
                // Create as independent GameObject at world origin.
                var go = new GameObject("HeadAnchor");
                _headAnchor = go.transform;
                _headAnchor.position = transform.position;
                _headAnchor.rotation = transform.rotation;
                // Keep unparented (world space) to break loop
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
            // P0 FIX: clamp to prevent VRAM overflow (width*2 = 3840 etc)
            _renderWidth = Mathf.Clamp(width, 64, 1920);
            _renderHeight = Mathf.Clamp(height, 64, 1080);
            
            ConfigureCamera(_leftCamera);
            ConfigureCamera(_rightCamera);
            
            // Position cameras for IPD
            if (_leftCamera != null)
                _leftCamera.transform.localPosition = new Vector3(-_ipd / 2f, 0, 0);
            if (_rightCamera != null)
                _rightCamera.transform.localPosition = new Vector3(_ipd / 2f, 0, 0);
        }
        
        private void ConfigureCamera(Camera cam)
        {
            if (cam == null) return;
            cam.nearClipPlane = _nearClip;
            cam.farClipPlane = _farClip;
            cam.fieldOfView = _fov;
            cam.aspect = (float)_renderWidth / _renderHeight;
            cam.useOcclusionCulling = true;
            // P0 FIX: 90 allowHDR - disable HDR for low-end Android / LAN streaming (saves VRAM/bandwidth)
            cam.allowHDR = false;
            cam.allowMSAA = false;
            // Use 1x MSAA implicitly via render texture antiAliasing=1
        }
        
        private void LateUpdate()
        {
            if (!_useHeadTracking) return;
            if (_headAnchor == null) return;
            
            // Smooth head pose
            _smoothedPosition = Vector3.Lerp(_smoothedPosition, _headPosition, Time.deltaTime * _positionSmoothing);
            _smoothedRotation = Quaternion.Slerp(_smoothedRotation, _headRotation, Time.deltaTime * _rotationSmoothing);
            
            // Apply to head anchor (world space, not child, so no feedback)
            _headAnchor.position = _smoothedPosition;
            _headAnchor.rotation = _smoothedRotation;
            
            // Cameras follow head anchor - rig itself follows anchor
            // Since headAnchor is NOT child, this is safe (no loop)
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
            _navigationPoints = points ?? new List<NavigationPointData>();
            _currentNavIndex = 0;
        }

        // P0 FIX: overload for NavigationSpec (RenderServer passes package.navigation)
        public void SetNavigationPoints(NavigationSpec spec)
        {
            if (spec?.points != null)
                SetNavigationPoints(spec.points);
            else
                _navigationPoints = new List<NavigationPointData>();
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

        // P0 FIX: 268 Teleport int vs string - add string overload for CopilotAgent
        public void TeleportToNavigationPoint(string id)
        {
            if (string.IsNullOrEmpty(id)) return;
            // Try id or name lookup
            int idx = _navigationPoints.FindIndex(p => p != null && (p.id == id || p.name == id));
            if (idx >= 0)
            {
                TeleportToNavigationPoint(idx);
                return;
            }
            // Fallback: try parse as int index
            if (int.TryParse(id, out var parsedIndex))
            {
                TeleportToNavigationPoint(parsedIndex);
                return;
            }
            Debug.LogWarning($"[StereoCameraRig] Teleport target not found: {id}");
        }
        
        public NavigationPointData GetCurrentNavigationPoint()
        {
            if (_currentNavIndex >= 0 && _currentNavIndex < _navigationPoints.Count)
                return _navigationPoints[_currentNavIndex];
            return null;
        }
        
        public NavigationPointData GetNextNavigationPoint()
        {
            if (_navigationPoints.Count == 0) return null;
            int next = (_currentNavIndex + 1) % _navigationPoints.Count;
            return _navigationPoints[next];
        }
        
        public NavigationPointData GetPreviousNavigationPoint()
        {
            if (_navigationPoints.Count == 0) return null;
            int prev = (_currentNavIndex - 1 + _navigationPoints.Count) % _navigationPoints.Count;
            return _navigationPoints[prev];
        }
        
        // Render textures for WebRTC
        public RenderTexture GetLeftEyeTexture()
        {
            if (_leftCamera == null) return null;
            if (_leftCamera.targetTexture == null)
            {
                // P0 FIX: 162 VRAM - use lower depth (16 vs 24), Default format, AA=1, no HDR
                var rt = new RenderTexture(_renderWidth, _renderHeight, 16, RenderTextureFormat.Default);
                rt.antiAliasing = 1;
                rt.filterMode = FilterMode.Bilinear;
                rt.useMipMap = false;
                rt.autoGenerateMips = false;
                rt.Create();
                _leftCamera.targetTexture = rt;
            }
            return _leftCamera.targetTexture;
        }
        
        public RenderTexture GetRightEyeTexture()
        {
            if (_rightCamera == null) return null;
            if (_rightCamera.targetTexture == null)
            {
                var rt = new RenderTexture(_renderWidth, _renderHeight, 16, RenderTextureFormat.Default);
                rt.antiAliasing = 1;
                rt.filterMode = FilterMode.Bilinear;
                rt.useMipMap = false;
                rt.autoGenerateMips = false;
                rt.Create();
                _rightCamera.targetTexture = rt;
            }
            return _rightCamera.targetTexture;
        }
        
        // Side-by-side stereo rendering - P0 FIX: use GetTemporary + cached material, not new RenderTexture / Graphics.Blit(Rect)
        public RenderTexture GetSideBySideTexture()
        {
            var leftTex = GetLeftEyeTexture();
            var rightTex = GetRightEyeTexture();
            if (leftTex == null || rightTex == null) return null;
            
            // P0 FIX: 184 leak new RenderTexture -> use GetTemporary
            // Clamp combined width to avoid 3840 overflow on low-end
            int combinedWidth = _renderWidth * 2;
            combinedWidth = Mathf.Clamp(combinedWidth, 64, 3840);
            var combined = RenderTexture.GetTemporary(combinedWidth, _renderHeight, 0, RenderTextureFormat.Default);
            combined.filterMode = FilterMode.Bilinear;
            combined.antiAliasing = 1;

            // P0 FIX: 192 Graphics.Blit(Rect) invalid -> use DrawTexture with cached material
            // Previously: Graphics.Blit(leftTex, combined, new Rect(...)) is invalid overload
            Graphics.SetRenderTarget(combined);
            GL.PushMatrix();
            GL.LoadOrtho();
            // Use cached material to avoid per-frame alloc
            var mat = BlitMaterial;
            Graphics.DrawTexture(new Rect(0, 0, 0.5f, 1), leftTex, mat);
            Graphics.DrawTexture(new Rect(0.5f, 0, 0.5f, 1), rightTex, mat);
            GL.PopMatrix();
            Graphics.SetRenderTarget(null);
            
            return combined; // Caller must ReleaseTemporary
        }

        // Helper to release temporary side-by-side texture
        public void ReleaseSideBySideTexture(RenderTexture rt)
        {
            if (rt != null)
                RenderTexture.ReleaseTemporary(rt);
        }

        private void OnDestroy()
        {
            // Cleanup RenderTextures to avoid leak
            if (_leftCamera != null && _leftCamera.targetTexture != null)
            {
                _leftCamera.targetTexture.Release();
                Destroy(_leftCamera.targetTexture);
                _leftCamera.targetTexture = null;
            }
            if (_rightCamera != null && _rightCamera.targetTexture != null)
            {
                _rightCamera.targetTexture.Release();
                Destroy(_rightCamera.targetTexture);
                _rightCamera.targetTexture = null;
            }
            if (_blitMaterial != null)
            {
                Destroy(_blitMaterial);
                _blitMaterial = null;
            }
        }
    }
    
    // P0 FIX: NavigationPointData is defined in SceneLoader.cs to avoid duplicate type error.
    // StereoCameraRig uses that same type (Cymatic.NavigationPointData) for navigation.
}
