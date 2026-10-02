#if UNITY_EDITOR
using UnityEngine;
using UnityEditor;
using UnityEditor.SceneManagement;

namespace Cymatic.Editor
{
    /// <summary>
    /// Editor script to set up the CYMATIC Render Server scene.
    /// Run from Unity Editor: Tools > CYMATIC > Setup Render Server Scene
    /// </summary>
    public class SetupRenderServerScene
    {
        [MenuItem("Tools/CYMATIC/Setup Render Server Scene")]
        public static void CreateRenderServerScene()
        {
            var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            
            // Create main RenderServer object
            var renderServerGO = new GameObject("RenderServer");
            var renderServer = renderServerGO.AddComponent<Cymatic.RenderServer>();
            
            // Configure
            var serializedObject = new SerializedObject(renderServer);
            serializedObject.FindProperty("backendUrl").stringValue = "http://localhost:8000";
            serializedObject.FindProperty("renderServerId").stringValue = "render-server-01";
            serializedObject.FindProperty("sessionPollInterval").floatValue = 3f;
            serializedObject.FindProperty("targetFPS").intValue = 60;
            serializedObject.FindProperty("renderWidth").intValue = 1920;
            serializedObject.FindProperty("renderHeight").intValue = 1080;
            serializedObject.FindProperty("ipd").intValue = 64;
            serializedObject.FindProperty("adaptiveQuality").boolValue = true;
            serializedObject.FindProperty("minBitrate").intValue = 5000000;
            serializedObject.FindProperty("maxBitrate").intValue = 30000000;
            serializedObject.ApplyModifiedProperties();
            
            // Create scene root for loaded scenes
            var sceneRoot = new GameObject("SceneRoot");
            sceneRoot.transform.SetParent(renderServerGO.transform);
            sceneRoot.transform.localPosition = Vector3.zero;
            
            // Setup lighting
            SetupLighting();
            
            // Setup physics
            Physics.defaultSolverIterations = 6;
            Physics.defaultSolverVelocityIterations = 4;
            Physics.sleepThreshold = 0.005f;
            Physics.autoSimulation = true;
            
            // Save scene
            var scenePath = "Assets/Scenes/RenderServer.unity";
            System.IO.Directory.CreateDirectory("Assets/Scenes");
            EditorSceneManager.SaveScene(scene, scenePath);
            
            // Add to build settings
            AddSceneToBuildSettings(scenePath);
            
            Debug.Log("[CYMATIC] Render Server scene created successfully!");
            Debug.Log("Next steps:");
            Debug.Log("1. Install required packages (WebRTC, Netcode)");
            Debug.Log("2. Configure Project Settings (see ProjectSettings.asset)");
            Debug.Log("3. Set Build Target to Windows/Standalone");
            Debug.Log("4. Build and run on gaming laptop");
        }
        
        private static void SetupLighting()
        {
            // Main directional light
            var lightGO = new GameObject("MainLight");
            var light = lightGO.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1f;
            light.color = new Color(1f, 0.95f, 0.85f); // Warm
            light.shadows = LightShadows.None; // MVP baked lighting, no realtime shadows
            light.lightmapBakeType = LightmapBakeType.Baked;
            light.shadowStrength = 0f;
            light.transform.rotation = Quaternion.Euler(50, -30, 0);
            
            // Ambient
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Skybox;
            RenderSettings.ambientLight = new Color(0.3f, 0.25f, 0.2f);
            RenderSettings.ambientIntensity = 1f;
            RenderSettings.defaultReflectionMode = UnityEngine.Rendering.DefaultReflectionMode.Skybox;
            RenderSettings.reflectionIntensity = 1f;
            RenderSettings.reflectionBounces = 1;
        }
        
        private static void AddSceneToBuildSettings(string scenePath)
        {
            var scenes = EditorBuildSettings.scenes;
            var sceneList = new System.Collections.Generic.List<EditorBuildSettingsScene>(scenes);
            
            // Check if already exists
            bool exists = false;
            foreach (var s in sceneList)
            {
                if (s.path == scenePath)
                {
                    exists = true;
                    break;
                }
            }
            
            if (!exists)
            {
                sceneList.Add(new EditorBuildSettingsScene(scenePath, true));
                EditorBuildSettings.scenes = sceneList.ToArray();
            }
        }
    }
}
#endif