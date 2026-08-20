using UnityEngine;

namespace Cymatic.Prefabs
{
    /// <summary>
    /// Lighting configuration component for scene lighting.
    /// </summary>
    public class LightingComponent : MonoBehaviour
    {
        [Header("Lighting Preset")]
        [SerializeField] private LightingPreset preset = LightingPreset.Warm;
        [SerializeField] private LightingTimeOfDay timeOfDay = LightingTimeOfDay.Evening;
        [SerializeField, Range(0f, 2f)] private float ambientIntensity = 1f;
        
        [Header("Sun Light")]
        [SerializeField] private Light sunLight;
        [SerializeField] private Vector3 sunDirection = new Vector3(0.5f, -1f, 0.3f);
        [SerializeField, Range(0f, 5f)] private float sunIntensity = 1f;
        [SerializeField] private Color sunColor = new Color(1f, 0.95f, 0.9f);
        [SerializeField] private bool autoRotateSun = false;
        [SerializeField, Range(0f, 360f)] private float sunRotationSpeed = 1f;
        
        [Header("Ambient")]
        [SerializeField] private Color ambientColor = new Color(0.3f, 0.25f, 0.2f);
        [SerializeField] private bool useSkybox = false;
        
        [Header("Custom Lights")]
        [SerializeField] private CustomLightData[] customLights;
        
        [Header("Shadows")]
        [SerializeField] private bool enableShadows = true;
        [SerializeField] private LightShadows shadowType = LightShadows.Soft;
        [SerializeField, Range(0f, 1f)] private float shadowStrength = 1f;
        [SerializeField] private float shadowDistance = 100f;
        [SerializeField, Range(0f, 1f)] private float shadowNearPlane = 0.1f;
        
        [Header("Quality")]
        [SerializeField] private ShadowResolution shadowResolution = ShadowResolution.High;
        [SerializeField] private int shadowCascades = 4;
        
        private Light _sunLight;
        private Light[] _customLights;
        private float _sunRotationAngle = 0f;
        
        public LightingPreset Preset => preset;
        public LightingTimeOfDay TimeOfDay => timeOfDay;
        public float AmbientIntensity => ambientIntensity;
        
        public enum LightingPreset
        {
            Warm,
            Cool,
            Neutral,
            GoldenHour,
            BlueHour,
            Custom
        }
        
        public enum LightingTimeOfDay
        {
            Morning,
            Noon,
            Evening,
            Night
        }
        
        void Awake()
        {
            InitializeLighting();
        }
        
        void Start()
        {
            ApplyLighting();
        }
        
        void Update()
        {
            if (autoRotateSun && sunLight != null)
            {
                _sunRotationAngle += sunRotationSpeed * Time.deltaTime;
                if (_sunRotationAngle >= 360f) _sunRotationAngle -= 360f;
                sunLight.transform.rotation = Quaternion.Euler(sunDirection.x, _sunRotationAngle, sunDirection.z);
            }
        }
        
        void InitializeLighting()
        {
            // Find or create sun light
            if (sunLight == null)
            {
                var sunObj = new GameObject("Sun Light");
                sunLight = sunObj.AddComponent<Light>();
                sunLight.type = LightType.Directional;
            }
            
            if (sunLight != null)
            {
                sunLight.type = LightType.Directional;
                sunLight.intensity = sunIntensity;
                sunLight.color = sunColor;
                sunLight.transform.rotation = Quaternion.Euler(sunDirection);
                sunLight.shadows = enableShadows ? shadowType : LightShadows.None;
                sunLight.shadowStrength = shadowStrength;
                sunLight.shadowResolution = shadowResolution;
                sunLight.shadows = enableShadows ? shadowType : LightShadows.None;
                sunLight.shadowBias = 0.05f;
                sunLight.shadowNormalBias = 0.1f;
                sunLight.shadowNearPlane = shadowNearPlane;
            }
            
            // Create custom lights
            if (customLights != null && customLights.Length > 0)
            {
                var customLightsArray = new Light[customLights.Length];
                for (int i = 0; i < customLights.Length; i++)
                {
                    var custom = customLights[i];
                    if (custom == null) continue;
                    
                    var lightObj = new GameObject($"CustomLight_{i}");
                    var light = lightObj.AddComponent<Light>();
                    light.type = custom.type == 0 ? LightType.Directional : 
                                 custom.type == 1 ? LightType.Point : 
                                 custom.type == 2 ? LightType.Spot : LightType.Area;
                    light.color = new Color(custom.color[0], custom.color[1], custom.color[2]);
                    light.intensity = custom.intensity;
                    light.range = custom.range ?? 10f;
                    light.spotAngle = custom.angle ?? 60f;
                    lightObj.transform.position = new Vector3(custom.position[0], custom.position[1], custom.position[2]);
                    light.transform.rotation = Quaternion.Euler(custom.rotation ?? Vector3.zero);
                    light.shadows = enableShadows ? custom.shadows : LightShadows.None;
                }
            }
            
            ApplyPreset();
        }
        
        public void ApplyPreset()
        {
            switch (preset)
            {
                case LightingPreset.Warm:
                    ambientColor = new Color(0.3f, 0.25f, 0.2f);
                    if (sunLight != null) sunLight.color = new Color(1f, 0.95f, 0.85f);
                    break;
                case LightingPreset.Cool:
                    ambientColor = new Color(0.2f, 0.25f, 0.3f);
                    if (sunLight != null) sunLight.color = new Color(0.9f, 0.95f, 1f);
                    break;
                case LightingPreset.Neutral:
                    ambientColor = Color.white;
                    if (sunLight != null) sunLight.color = Color.white;
                    break;
                case LightingPreset.GoldenHour:
                    ambientColor = new Color(0.4f, 0.3f, 0.2f);
                    if (sunLight != null) sunLight.color = new Color(1f, 0.8f, 0.5f);
                    break;
                case LightingPreset.BlueHour:
                    ambientColor = new Color(0.2f, 0.25f, 0.4f);
                    if (sunLight != null) sunLight.color = new Color(0.7f, 0.8f, 1f);
                    break;
                case LightingPreset.Custom:
                default:
                    break;
            }
        }
        
        public void ApplyLighting()
        {
            if (sunLight == null) return;
            
            // Apply sun settings
            sunLight.color = sunColor;
            sunLight.intensity = sunIntensity * ambientIntensity;
            sunLight.transform.rotation = Quaternion.Euler(sunDirection);
            
            // Apply shadows
            sunLight.shadows = enableShadows ? shadowType : LightShadows.None;
            sunLight.shadowStrength = shadowStrength;
            sunLight.shadowResolution = shadowResolution;
            sunLight.shadowDistance = shadowDistance;
            sunLight.shadowNearPlane = shadowNearPlane;
            
            // Apply ambient
            RenderSettings.ambientLight = ambientColor * ambientIntensity;
            RenderSettings.ambientIntensity = ambientIntensity;
            RenderSettings.ambientMode = useSkybox ? AmbientMode.Skybox : AmbientMode.Flat;
            
            // Apply custom lights
            if (customLights != null)
            {
                // Custom lights are already set up in InitializeLighting
            }
        }
        
        public void SetTimeOfDay(float timeOfDay)
        {
            // timeOfDay: 0 = midnight, 0.25 = sunrise, 0.5 = noon, 0.75 = sunset
            float angle = timeOfDay * 360f - 90f;
            var rotation = Quaternion.Euler(0, timeOfDay * 360f - 90f, 0);
            if (sunLight != null)
                sunLight.transform.rotation = rotation;
        }
        
        public void SetPreset(LightingPreset preset)
        {
            preset = preset;
            ApplyPreset();
            ApplyLighting();
        }
        
        public void SetSunRotation(float angle)
        {
            if (sunLight != null)
                sunLight.transform.rotation = Quaternion.Euler(0, angle, 0);
        }
    }
    
    [System.Serializable]
    public class CustomLightData
    {
        public int type = 0; // 0=Directional, 1=Point, 2=Spot, 3=Area
        public float[] position = new float[3];
        public float[] rotation = new float[3];
        public float[] color = new float[3] { 1, 1, 1 };
        public float intensity = 1f;
        public float range = 10f;
        public float angle = 60f;
        public bool shadows = true;
    }
}