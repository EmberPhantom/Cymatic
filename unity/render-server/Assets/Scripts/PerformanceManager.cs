using System;
using System.Collections.Generic;
using UnityEngine;
using Cysharp.Threading.Tasks;

namespace Cymatic
{
    /// <summary>
    /// Performance Manager - Monitors and adapts rendering quality for mobile VR.
    /// </summary>
    public class PerformanceManager : MonoBehaviour
    {
        private static PerformanceManager _instance;
        public static PerformanceManager Instance => _instance;

        [Header("Target Settings")]
        [SerializeField] private int _targetFPS = 60;
        [SerializeField] private bool _adaptiveQuality = true;
        [SerializeField] private float _updateInterval = 1f;
        
        [Header("Quality Levels")]
        [SerializeField] private QualityPreset[] _qualityPresets = new QualityPreset[]
        {
            new QualityPreset { name = "Ultra", renderScale = 1.5f, msaa = 4, shadowQuality = ShadowQuality.All, pixelLightCount = 4, textureQuality = 0 },
            new QualityPreset { name = "High", renderScale = 1.25f, msaa = 2, shadowQuality = ShadowQuality.HardOnly, pixelLightCount = 3, textureQuality = 0 },
            new QualityPreset { name = "Medium", renderScale = 1.0f, msaa = 2, shadowQuality = ShadowQuality.HardOnly, pixelLightCount = 2, textureQuality = 1 },
            new QualityPreset { name = "Low", renderScale = 0.75f, msaa = 0, shadowQuality = ShadowQuality.Disable, pixelLightCount = 1, textureQuality = 2 },
            new QualityPreset { name = "Minimum", renderScale = 0.5f, msaa = 0, shadowQuality = ShadowQuality.Disable, pixelLightCount = 0, textureQuality = 2 }
        };
        
        [Header("Thermal")]
        [SerializeField] private bool _monitorThermal = true;
        [SerializeField] private float _thermalThrottleThreshold = 0.8f; // 80%
        
        // State
        private int _currentQualityIndex = 2; // Medium
        private bool _isMonitoring = false;
        private float _lastUpdateTime = 0f;
        
        // Metrics
        private float _currentFPS = 0f;
        private float _avgFrameTime = 0f;
        private float _gpuTime = 0f;
        private float _cpuTime = 0f;
        private int _drawCalls = 0;
        private int _triangles = 0;
        private float _memoryUsage = 0f;
        private float _thermalLevel = 0f;
        
        // History for averaging
        private Queue<float> _fpsHistory = new Queue<float>();
        private Queue<float> _frameTimeHistory = new Queue<float>();
        private const int HistorySize = 60;
        
        public int CurrentQualityIndex => _currentQualityIndex;
        public string CurrentQualityName => _qualityPresets[_currentQualityIndex].name;
        public float CurrentFPS => _currentFPS;
        public float AvgFrameTime => _avgFrameTime;
        public float ThermalLevel => _thermalLevel;
        
        void Start() { _instance = this; }

        public event Action<int> OnQualityChanged;
        public event Action<float> OnThermalThrottle;
        
        public void Configure(int targetFPS, bool adaptiveQuality)
        {
            _targetFPS = targetFPS;
            _adaptiveQuality = adaptiveQuality;
            
            // Apply initial quality
            ApplyQuality(_currentQualityIndex);
        }
        
        public void StartMonitoring()
        {
            _isMonitoring = true;
            _lastUpdateTime = Time.time;
            MonitoringLoop().Forget();
        }
        
        public void StopMonitoring()
        {
            _isMonitoring = false;
        }
        
        private void Update()
        {
            if (!_isMonitoring) return;
            
            // Collect frame metrics
            _fpsHistory.Enqueue(1f / Time.unscaledDeltaTime);
            _frameTimeHistory.Enqueue(Time.unscaledDeltaTime * 1000f);
            
            if (_fpsHistory.Count > HistorySize)
            {
                _fpsHistory.Dequeue();
                _frameTimeHistory.Dequeue();
            }
            
            // Update thermal
            if (_monitorThermal)
            {
                UpdateThermal();
            }
        }
        
        private async UniTaskVoid MonitoringLoop()
        {
            while (_isMonitoring)
            {
                await UniTask.Delay(TimeSpan.FromSeconds(_updateInterval));
                
                if (!_isMonitoring) break;
                
                CalculateMetrics();
                CheckAdaptiveQuality();
            }
        }
        
        private void CalculateMetrics()
        {
            // FPS
            if (_fpsHistory.Count > 0)
            {
                float sum = 0;
                foreach (var fps in _fpsHistory) sum += fps;
                _currentFPS = sum / _fpsHistory.Count;
            }
            
            // Frame time
            if (_frameTimeHistory.Count > 0)
            {
                float sum = 0;
                foreach (var ft in _frameTimeHistory) sum += ft;
                _avgFrameTime = sum / _frameTimeHistory.Count;
            }
            
            // Draw calls & triangles (from Unity stats)
            _drawCalls = (int)UnityEngine.Rendering.GraphicsSettings.GetGraphicsSettings().GetType().GetProperty("drawCalls")?.GetValue(null) ?? 0;
            _triangles = (int)UnityEngine.Rendering.GraphicsSettings.GetGraphicsSettings().GetType().GetProperty("triangles")?.GetValue(null) ?? 0;
            
            // Memory
            _memoryUsage = Profiler.GetTotalAllocatedMemoryLong() / (1024f * 1024f); // MB
        }
        
        private void UpdateThermal()
        {
            // Get thermal state (platform specific)
#if UNITY_ANDROID && !UNITY_EDITOR
            using (var thermal = new AndroidJavaClass("android.os.PowerManager"))
            using (var activity = new AndroidJavaClass("com.unity3d.player.UnityPlayer").GetStatic<AndroidJavaObject>("currentActivity"))
            using (var pm = activity.Call<AndroidJavaObject>("getSystemService", "power"))
            {
                var thermalStatus = pm.Call<int>("getThermalHeadroom");
                _thermalLevel = Mathf.Clamp01(1f - (thermalStatus / 100f));
            }
#else
            // Simulate thermal in editor
            _thermalLevel = Mathf.Lerp(_thermalLevel, UnityEngine.Random.Range(0.2f, 0.5f), 0.1f);
#endif
            
            if (_thermalLevel > _thermalThrottleThreshold)
            {
                OnThermalThrottle?.Invoke(_thermalLevel);
                if (_currentQualityIndex < _qualityPresets.Length - 1)
                {
                    SetQuality(_currentQualityIndex + 1);
                }
            }
        }
        
        private void CheckAdaptiveQuality()
        {
            if (!_adaptiveQuality) return;
            
            // Check if we need to adjust quality
            float fpsDiff = _targetFPS - _currentFPS;
            float fpsThreshold = _targetFPS * 0.1f; // 10% threshold
            
            if (fpsDiff > fpsThreshold && _currentQualityIndex < _qualityPresets.Length - 1)
            {
                // FPS too low, reduce quality
                SetQuality(_currentQualityIndex + 1);
            }
            else if (fpsDiff < -fpsThreshold && _currentQualityIndex > 0)
            {
                // FPS has headroom, increase quality
                SetQuality(_currentQualityIndex - 1);
            }
        }
        
        public void SetQuality(int index)
        {
            index = Mathf.Clamp(index, 0, _qualityPresets.Length - 1);
            
            if (index == _currentQualityIndex) return;
            
            _currentQualityIndex = index;
            ApplyQuality(index);
            OnQualityChanged?.Invoke(index);
            
            Debug.Log($"[Performance] Quality changed to: {_qualityPresets[index].name}");
        }
        
        private void ApplyQuality(int index)
        {
            var preset = _qualityPresets[index];
            
            // Render scale
            QualitySettings.renderPipeline = null; // Built-in RP
            ScalableBufferManager.ResizeBuffers(preset.renderScale, preset.renderScale);
            
            // MSAA
            QualitySettings.antiAliasing = preset.msaa;
            
            // Shadows
            QualitySettings.shadows = preset.shadowQuality;
            QualitySettings.shadowResolution = preset.shadowQuality == ShadowQuality.Disable 
                ? ShadowResolution.Low 
                : ShadowResolution.High;
            
            // Pixel lights
            QualitySettings.pixelLightCount = preset.pixelLightCount;
            
            // Texture quality
            QualitySettings.masterTextureLimit = preset.textureQuality;
            
            // VSync
            QualitySettings.vSyncCount = 0;
            
            // LOD bias
            QualitySettings.lodBias = 1f + (index * 0.2f);
            
            // Max frame rate
            Application.targetFrameRate = _targetFPS;
        }
        
        public void ForceMinimumQuality()
        {
            SetQuality(_qualityPresets.Length - 1);
        }
        
        public PerformanceMetrics GetMetrics()
        {
            return new PerformanceMetrics
            {
                fps = _currentFPS,
                avgFrameTime = _avgFrameTime,
                gpuTime = _gpuTime,
                cpuTime = _cpuTime,
                drawCalls = _drawCalls,
                triangles = _triangles,
                memoryMB = _memoryUsage,
                thermalLevel = _thermalLevel,
                qualityLevel = _qualityPresets[_currentQualityIndex].name,
                targetFPS = _targetFPS
            };
        }
    }
    
    [System.Serializable]
    public class QualityPreset
    {
        public string name;
        public float renderScale = 1f;
        public int msaa = 2;
        public ShadowQuality shadowQuality = ShadowQuality.HardOnly;
        public int pixelLightCount = 2;
        public int textureQuality = 0; // 0=Full, 1=Half, 2=Quarter
    }
    
    [System.Serializable]
    public class PerformanceMetrics
    {
        public float fps;
        public float avgFrameTime;
        public float gpuTime;
        public float cpuTime;
        public int drawCalls;
        public int triangles;
        public float memoryMB;
        public float thermalLevel;
        public string qualityLevel;
        public int targetFPS;
    }
}