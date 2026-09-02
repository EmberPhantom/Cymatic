using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.Networking;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json;
using Newtonsoft.Json.Linq;
using Cymatic.Pooling;
using Cymatic.Prefabs;
using Cymatic.Materials;
using Cymatic.Navigation;

public class Vector3Converter : JsonConverter<Vector3>
{
    public override Vector3 ReadJson(JsonReader reader, Type objectType, Vector3 existingValue, bool hasExistingValue, JsonSerializer serializer)
    {
        var arr = JArray.Load(reader);
        if (arr.Count >= 3) return new Vector3((float)arr[0], (float)arr[1], (float)arr[2]);
        return Vector3.zero;
    }
    public override void WriteJson(JsonWriter writer, Vector3 value, JsonSerializer serializer)
    {
        writer.WriteStartArray(); writer.WriteValue(value.x); writer.WriteValue(value.y); writer.WriteValue(value.z); writer.WriteEndArray();
    }
}

namespace Cymatic
{
    public class CopilotPolicyComponent : MonoBehaviour
    {
        public CopilotPolicyData policy;
    }

    /// <summary>
    /// Scene Loader - Downloads and instantiates scene packages from MinIO.
    /// </summary>
    public class SceneLoader : MonoBehaviour
    {
        [Header("Settings")]
        [SerializeField] private string _minioEndpoint = "http://localhost:9000";
        [SerializeField] private string _bucketName = "cymatic";
        
        // Current scene
        private GameObject _sceneRoot;
        private CymaticScenePackage _currentPackage;
        private Dictionary<string, GameObject> _prefabCache = new Dictionary<string, GameObject>();
        
        public CymaticScenePackage CurrentPackage => _currentPackage;
        
        public async UniTask<CymaticScenePackage> LoadFromUrl(string url)
        {
            Debug.Log($"[SceneLoader] Downloading scene package from {url}");
            
            // Download JSON
            using (var request = UnityWebRequest.Get(url))
            {
                await request.SendWebRequest();
                
                if (request.result != UnityWebRequest.Result.Success)
                {
                    Debug.LogError($"[SceneLoader] Failed to download: {request.error}");
                    return null;
                }
                
                var json = request.downloadHandler.text;
                var settings = new JsonSerializerSettings();
                settings.Converters.Add(new Vector3Converter());
                var package = JsonConvert.DeserializeObject<CymaticScenePackage>(json, settings);
                return package;
            }
        }
        
        public async UniTask<bool> InstantiateScene(CymaticScenePackage package)
        {
            _currentPackage = package;
            
            // Clear previous scene
            await UnloadScene();
            
            // Create scene root
            _sceneRoot = new GameObject($"Scene_{package.metadata.domain}_{package.metadata.spec_version}");
            _sceneRoot.transform.position = Vector3.zero;
            
            // Ensure MaterialManager is initialized
            if (MaterialManager.Instance == null)
            {
                var matManagerGO = new GameObject("MaterialManager");
                matManagerGO.AddComponent<MaterialManager>();
            }
            
            // Instantiate entities using object pooling
            foreach (var entity in package.entities)
            {
                await InstantiateEntity(entity, _sceneRoot.transform);
            }
            
            // Setup lighting
            SetupLighting(package.lighting);
            
            // Setup navigation
            SetupNavigation(package.navigation);
            
            // Setup copilot
            SetupCopilot(package.copilot_policy);
            
            // Initialize NavigationManager
            if (NavigationManager.Instance == null)
            {
                var navManagerGO = new GameObject("NavigationManager");
                navManagerGO.AddComponent<NavigationManager>();
            }
            
            // Build NavMesh
            if (NavigationManager.Instance != null)
            {
                await UniTask.NextFrame();
                NavigationManager.Instance.BuildNavMesh();
            }
            
            Debug.Log($"[SceneLoader] Scene instantiated with {package.entities.Count} entities");
            return true;
        }
        
        private async UniTask InstantiateEntity(SceneEntity entity, Transform parent)
        {
            var go = new GameObject(entity.name);
            go.transform.SetParent(parent);
            go.transform.localPosition = entity.position;
            go.transform.localRotation = Quaternion.Euler(entity.rotation);
            go.transform.localScale = entity.scale;
            if (entity.type == "room" || entity.type == "floor" || entity.type == "wall") go.isStatic = true;
            
            // Add components
            foreach (var comp in entity.components)
            {
                AddComponent(go, comp);
            }
            
            // Load prefab if specified
            if (!string.IsNullOrEmpty(entity.prefab_path))
            {
                var prefab = await LoadPrefab(entity.prefab_path);
                if (prefab != null)
                {
                    var instance = Instantiate(prefab, go.transform);
                    instance.transform.localPosition = Vector3.zero;
                    instance.transform.localRotation = Quaternion.identity;
                    instance.transform.localScale = Vector3.one;
                }
            }
            
            // Set properties
            ApplyProperties(go, entity.properties);
            
            // Add entity type component
            AddEntityTypeComponent(go, entity);
            
            // Instantiate children
            foreach (var child in entity.children)
            {
                await InstantiateEntity(child, go.transform);
            }
        }
        
        private void AddComponent(GameObject go, ComponentData comp)
        {
            var type = Type.GetType($"UnityEngine.{comp.type}, UnityEngine.CoreModule")
                         ?? Type.GetType($"UnityEngine.{comp.type}, UnityEngine");
            if (type == null) type = System.AppDomain.CurrentDomain.GetAssemblies().SelectMany(a => a.GetTypes()).FirstOrDefault(t => t.Name == comp.type);
            if (type != null)
            {
                var component = go.AddComponent(type);
                foreach (var prop in comp.properties)
                {
                    var field = type.GetField(prop.Key) ?? type.GetProperty(prop.Key)?.GetGetMethod() != null ? type.GetProperty(prop.Key) : null;
                    try {
                        var targetType = (field as System.Reflection.FieldInfo)?.FieldType ?? (field as System.Reflection.PropertyInfo)?.PropertyType;
                        if (targetType != null) {
                            object val = prop.Value is JToken jt ? jt.ToObject(targetType) : Convert.ChangeType(prop.Value, targetType);
                            if (field is System.Reflection.FieldInfo fi) fi.SetValue(component, val);
                            else if (field is System.Reflection.PropertyInfo pi) pi.SetValue(component, val);
                        }
                    } catch {}
                }
            }
        }
        
        private void ApplyProperties(GameObject go, Dictionary<string, object> properties)
        {
            // Store properties for runtime access
            var propComponent = go.GetComponent<EntityProperties>();
            if (propComponent == null)
                propComponent = go.AddComponent<EntityProperties>();
            
            propComponent.properties = properties;
        }
        
        private void AddEntityTypeComponent(GameObject go, SceneEntity entity)
        {
            // Add entity type component for runtime identification
            switch (entity.type)
            {
                case "room":
                    var roomComp = go.AddComponent<RoomComponent>();
                    roomComp.name = entity.name;
                    if (entity.properties != null)
                    {
                        roomComp.isFurnished = entity.properties.GetValueOrDefault("furnished", true);
                        roomComp.style = entity.properties.GetValueOrDefault("style", "modern");
                    }
                    break;
                    
                case "poi":
                    var poiComp = go.AddComponent<POIComponent>();
                    poiComp.name = entity.name;
                    if (entity.properties != null)
                    {
                        poiComp.description = entity.properties.GetValueOrDefault("description", "");
                        poiComp.hasNarration = entity.properties.GetValueOrDefault("has_narration", true);
                    }
                    break;
                    
                case "navigation_point":
                    var navPoint = go.AddComponent<NavigationPoint>();
                    navPoint.Initialize(entity.id, entity.name, entity.properties?.GetValueOrDefault("description", ""), new List<string>());
                    break;
                    
                case "light":
                    var light = go.AddComponent<Light>();
                    if (entity.properties != null)
                    {
                        if (entity.properties.TryGetValue("light_type", out var lt))
                            light.type = Enum.TryParse<LightType>(lt.ToString(), true, out var lt2) ? lt2 : LightType.Directional;
                        if (entity.properties.TryGetValue("intensity", out var intensity))
                            light.intensity = Convert.ToSingle(intensity);
                        if (entity.properties.TryGetValue("color", out var color) && color is List<object> colorList && colorList.Count == 3)
                            light.color = new Color(Convert.ToSingle(colorList[0]), Convert.ToSingle(colorList[1]), Convert.ToSingle(colorList[2]));
                    }
                    break;
            }
        }
        
        private async UniTask<GameObject> LoadPrefab(string path)
        {
            if (_prefabCache.ContainsKey(path))
                return _prefabCache[path];
            
            // Try Resources first
            var prefab = Resources.Load<GameObject>(path);
            
            if (prefab == null)
            {
                // Try Addressables or AssetBundle
                // For now, create primitive based on name
                prefab = CreatePrimitiveFromPath(path);
            }
            
            if (prefab != null)
                _prefabCache[path] = prefab;
            
            return prefab;
        }
        
        private GameObject CreatePrimitiveFromPath(string path)
        {
            var name = path.ToLower();
            
            if (name.Contains("room") || name.Contains("floor"))
                return CreateRoomPrimitive();
            else if (name.Contains("wall"))
                return CreateWallPrimitive();
            else if (name.Contains("light"))
                return CreateLightPrimitive();
            else if (name.Contains("poi") || name.Contains("navigation"))
                return CreatePOIPrimitive();
            
            return GameObject.CreatePrimitive(PrimitiveType.Cube);
        }
        
        private GameObject CreateRoomPrimitive()
        {
            var go = new GameObject("Room");
            var renderer = go.AddComponent<MeshRenderer>();
            var filter = go.AddComponent<MeshFilter>();
            
            // Create room mesh (floor + walls)
            var mesh = new Mesh();
            // Simplified: just a floor plane for now
            filter.mesh = CreateFloorMesh(10, 10);
            
            renderer.material = MaterialManager.Instance?.GetWallMaterial() 
                ?? new Material(Shader.Find("Standard")) { color = new Color(0.8f, 0.8f, 0.8f) };
            
            var collider = go.AddComponent<BoxCollider>();
            collider.size = new Vector3(10, 3, 10);
            collider.center = new Vector3(0, 1.5f, 0);
            
            // Add room component
            var roomComp = go.AddComponent<RoomComponent>();
            roomComp.name = "Room";
            
            return go;
        }
        
        private GameObject CreateWallPrimitive()
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.transform.localScale = new Vector3(0.2f, 3, 5);
            return go;
        }
        
        private GameObject CreateLightPrimitive()
        {
            var go = new GameObject("Light");
            var light = go.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1f;
            return go;
        }
        
        private GameObject CreatePOIPrimitive()
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            go.transform.localScale = Vector3.one * 0.5f;
            var collider = go.GetComponent<SphereCollider>();
            collider.isTrigger = true;
            collider.radius = 2f;
            
            // Add POI component
            var poi = go.AddComponent<POIComponent>();
            poi.name = "POI";
            
            return go;
        }
        
        private Mesh CreateFloorMesh(float width, float depth)
        {
            var mesh = new Mesh();
            var vertices = new Vector3[4]
            {
                new Vector3(-width/2, 0, -depth/2),
                new Vector3(width/2, 0, -depth/2),
                new Vector3(-width/2, 0, depth/2),
                new Vector3(width/2, 0, depth/2)
            };
            var triangles = new int[6] { 0, 2, 1, 2, 3, 1 };
            var uvs = new Vector2[4]
            {
                new Vector2(0, 0), new Vector2(1, 0), new Vector2(0, 1), new Vector2(1, 1)
            };
            
            mesh.vertices = vertices;
            mesh.triangles = triangles;
            mesh.uv = uvs;
            mesh.RecalculateNormals();
            
            return mesh;
        }
        
        private void SetupLighting(LightingData lighting)
        {
            // Find or create main light
            var mainLight = FindObjectOfType<Light>();
            if (mainLight == null)
            {
                var lightGO = new GameObject("MainLight");
                mainLight = lightGO.AddComponent<Light>();
            }
            
            mainLight.type = LightType.Directional;
            mainLight.intensity = lighting.ambient_intensity;
            mainLight.color = Color.white;
            
            if (lighting.sun_direction != null && lighting.sun_direction.Length == 3)
            {
                mainLight.transform.rotation = Quaternion.Euler(lighting.sun_direction);
            }
            
            // Apply preset
            switch (lighting.preset)
            {
                case "warm":
                    mainLight.color = new Color(1f, 0.95f, 0.85f);
                    RenderSettings.ambientLight = new Color(0.3f, 0.25f, 0.2f);
                    break;
                case "cool":
                    mainLight.color = new Color(0.9f, 0.95f, 1f);
                    RenderSettings.ambientLight = new Color(0.2f, 0.25f, 0.3f);
                    break;
                case "neutral":
                    mainLight.color = Color.white;
                    RenderSettings.ambientLight = new Color(0.25f, 0.25f, 0.25f);
                    break;
                case "blue_hour":
                    mainLight.color = new Color(0.6f, 0.7f, 1f);
                    RenderSettings.ambientLight = new Color(0.15f, 0.18f, 0.25f);
                    break;
                case "custom":
                    if (lighting.custom_lights != null && lighting.custom_lights.Count > 0) {
                        // custom lights handled below
                        RenderSettings.ambientLight = Color.white * lighting.ambient_intensity;
                    }
                    break;
                case "golden_hour":
                    mainLight.color = new Color(1f, 0.8f, 0.5f);
                    RenderSettings.ambientLight = new Color(0.4f, 0.3f, 0.2f);
                    break;
                default:
                    mainLight.color = new Color(1f, 0.95f, 0.85f);
                    break;
            }
            
            // Custom lights
            foreach (var custom in lighting.custom_lights)
            {
                var lightGO = new GameObject($"CustomLight_{custom.type}");
                var light = lightGO.AddComponent<Light>();
                light.type = Enum.TryParse<LightType>(custom.type, true, out var lt) ? lt : LightType.Point;
                light.color = new Color(custom.color[0], custom.color[1], custom.color[2]);
                light.intensity = custom.intensity;
                light.range = custom.range ?? 10f;
                light.spotAngle = custom.angle ?? 60f;
                lightGO.transform.position = new Vector3(custom.position[0], custom.position[1], custom.position[2]);
            }
        }
        
        private void SetupNavigation(NavigationSpec navigation)
        {
            var navRoot = new GameObject("Navigation");
            navRoot.transform.SetParent(_sceneRoot.transform);
            
            foreach (var point in navigation.points)
            {
                var pointGO = new GameObject($"Nav_{point.name}");
                pointGO.transform.SetParent(navRoot.transform);
                pointGO.transform.position = point.position;
                
                var navPoint = pointGO.AddComponent<NavigationPoint>();
                navPoint.Initialize(point.id, point.name, point.description, point.connections);
                
                // Visual representation
                var sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                sphere.transform.SetParent(pointGO.transform);
                sphere.transform.localScale = Vector3.one * 0.3f;
                sphere.GetComponent<Renderer>().material = MaterialManager.Instance?.GetNavigationMarkerMaterial();
            }
            
            // Create paths
            var pathsRoot = new GameObject("Paths");
            pathsRoot.transform.SetParent(navRoot.transform);
            
            foreach (var path in navigation.paths)
            {
                var pathGO = new GameObject($"Path_{path.from_point}_to_{path.to_point}");
                pathGO.transform.SetParent(pathsRoot.transform);
                
                var lr = pathGO.AddComponent<LineRenderer>();
                lr.startWidth = 0.1f;
                lr.endWidth = 0.1f;
                lr.material = new Material(Shader.Find("Sprites/Default")) { color = Color.blue };
                
                // Find points
                var fromPoint = navRoot.transform.Find($"Nav_{path.from_point}");
                var toPoint = navRoot.transform.Find($"Nav_{path.to_point}");
                
                if (fromPoint != null && toPoint != null)
                {
                    lr.positionCount = 2;
                    lr.SetPosition(0, fromPoint.position);
                    lr.SetPosition(1, toPoint.position);
                }
            }
        }
        
        private void SetupCopilot(CopilotPolicyData copilot)
        {
            var copilotGO = new GameObject("CopilotSystem");
            copilotGO.transform.SetParent(_sceneRoot.transform);
            var dataComp = copilotGO.AddComponent<CopilotPolicyComponent>();
            dataComp.policy = copilot;
        }
        
        public async UniTask UnloadScene()
        {
            if (_sceneRoot != null)
            {
                Destroy(_sceneRoot);
                _sceneRoot = null;
            }
            
            _currentPackage = null;
            _prefabCache.Clear();
            Resources.UnloadUnusedAssets();
            
            await UniTask.Yield();
        }
    }
    
    [System.Serializable]
    public class CymaticScenePackage
    {
        public ScenePackageMetadata metadata;
        public string domain;
        public List<SceneEntity> entities;
        public NavigationSpec navigation;
        public LightingData lighting;
        public CopilotPolicyData copilot_policy;
        public PerformanceBudgetData performance_budget;
        public Dictionary<string, object> asset_manifest;
    }
    
    [System.Serializable]
    public class ScenePackageMetadata
    {
        public string format;
        public int spec_version;
        public string generated_at;
        public string title;
        public string generator;
        public string unity_version;
        public string target_platform;
        public string streaming_protocol;
    }
    
    [System.Serializable]
    public class SceneEntity
    {
        public string id;
        public string name;
        public string type;
        public Vector3 position;
        public Vector3 rotation;
        public Vector3 scale;
        public string prefab_path;
        public Dictionary<string, object> properties;
        public List<ComponentData> components;
        public List<SceneEntity> children;
    }
    
    [System.Serializable]
    public class ComponentData
    {
        public string type;
        public Dictionary<string, object> properties;
    }
    
    [System.Serializable]
    public class NavigationSpec
    {
        public List<NavigationPointData> points;
        public List<NavigationPathData> paths;
        public string default_start_point;
    }
    
    [System.Serializable]
    public class NavigationPointData
    {
        public string id;
        public string name;
        public Vector3 position;
        public string description;
        public List<string> connections;
        public Vector3 rotation;
    }
    
    [System.Serializable]
    public class NavigationPathData
    {
        public string from_point;
        public string to_point;
        public string type;
        public List<Vector3> waypoints;
    }
    
    [System.Serializable]
    public class LightingData
    {
        public string preset;
        public string time_of_day;
        public float ambient_intensity;
        public float[] sun_direction;
        public List<CustomLightData> custom_lights;
    }
    
    [System.Serializable]
    public class CustomLightData
    {
        public string type;
        public float[] position;
        public float[] color;
        public float intensity;
        public float? range;
        public float? angle;
    }
    
    [System.Serializable]
    public class CopilotPolicyData
    {
        public bool enabled;
        public List<string> languages;
        public string default_language;
        public string personality;
        public List<string> allowed_actions;
        public string knowledge_base;
    }
    
    [System.Serializable]
    public class PerformanceBudgetData
    {
        public int target_fps;
        public int max_triangles;
        public int max_draw_calls;
        public int texture_budget_mb;
        public int max_entities;
        public float[] lod_distances;
    }
    
}