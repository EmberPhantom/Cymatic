#if UNITY_EDITOR
using UnityEditor;
using UnityEngine;
using System.IO;
using System.Linq;

namespace Cymatic
{
    /// <summary>
    /// CI build entry point for CYMATIC Render Server.
    /// Called via: -executeMethod Cymatic.BuildScript.PerformBuild
    /// </summary>
    public static class BuildScript
    {
        public static void PerformBuild()
        {
            // Ensure scene exists — create if missing (idempotent)
            const string scenePath = "Assets/Scenes/RenderServer.unity";
            if (!File.Exists(scenePath))
            {
                Debug.Log("[CYMATIC Build] Scene not found, creating via SetupRenderServerScene...");
                // Use fully qualified name to avoid namespace confusion
                Cymatic.Editor.SetupRenderServerScene.CreateRenderServerScene();
            }

            // Ensure Scenes list contains at least the RenderServer scene
            var scenes = EditorBuildSettings.scenes;
            if (scenes == null || scenes.Length == 0 || !scenes.Any(s => s.path == scenePath))
            {
                Debug.LogWarning("[CYMATIC Build] Build Settings scenes empty, adding RenderServer.unity");
                var list = new System.Collections.Generic.List<EditorBuildSettingsScene>(scenes ?? new EditorBuildSettingsScene[0]);
                list.Add(new EditorBuildSettingsScene(scenePath, true));
                EditorBuildSettings.scenes = list.ToArray();
            }

            // Determine output path — game-ci unity-builder expects Builds/StandaloneWindows64
            string buildPath = "Builds/StandaloneWindows64/CymaticRenderServer.exe";
            // Allow override via env var BUILD_PATH
            string envPath = System.Environment.GetEnvironmentVariable("BUILD_PATH");
            if (!string.IsNullOrEmpty(envPath))
            {
                buildPath = envPath;
            }

            string dir = Path.GetDirectoryName(buildPath);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }

            var buildScenes = EditorBuildSettings.scenes.Where(s => s.enabled).Select(s => s.path).ToArray();
            if (buildScenes.Length == 0)
            {
                buildScenes = new[] { scenePath };
            }

            Debug.Log($"[CYMATIC Build] Building {buildScenes.Length} scene(s) to {buildPath} ...");

            var options = new BuildPlayerOptions
            {
                scenes = buildScenes,
                locationPathName = buildPath,
                target = BuildTarget.StandaloneWindows64,
                options = BuildOptions.None
            };

            var report = BuildPipeline.BuildPlayer(options);
            var summary = report.summary;

            Debug.Log($"[CYMATIC Build] Result: {summary.result} | {summary.totalSize} bytes | warnings: {summary.totalWarnings} errors: {summary.totalErrors}");

            if (summary.result != UnityEditor.Build.Reporting.BuildResult.Succeeded)
            {
                Debug.LogError($"[CYMATIC Build] Failed with {summary.totalErrors} errors");
                EditorApplication.Exit(1);
            }
            else
            {
                Debug.Log("[CYMATIC Build] Succeeded");
                EditorApplication.Exit(0);
            }
        }
    }
}
#endif
