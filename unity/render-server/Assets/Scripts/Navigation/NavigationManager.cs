using UnityEngine;
using UnityEngine.AI;
using System.Collections.Generic;

namespace Cymatic.Navigation
{
    /// <summary>
    /// Manages navigation mesh and pathfinding for the scene.
    /// </summary>
    public class NavigationManager : MonoBehaviour
    {
        [Header("NavMesh Settings")]
        [SerializeField] private NavMeshData navMeshData;
        [SerializeField] private NavMeshBuildSettings buildSettings;
        [SerializeField] private bool autoRebakeOnLoad = true;
        [SerializeField] private LayerMask navigationLayers = -1;
        
        [Header("Pathfinding")]
        [SerializeField] private float agentRadius = 0.5f;
        [SerializeField] private float agentHeight = 2f;
        [SerializeField] private float maxSlope = 45f;
        [SerializeField] private float stepHeight = 0.3f;
        [SerializeField] private float dropHeight = 1f;
        [SerializeField] private float jumpDistance = 2f;
        
        [Header("Runtime")]
        [SerializeField] private bool showNavMesh = true;
        [SerializeField] private Color navMeshColor = new Color(0, 1, 0, 0.3f);
        
        private NavMeshData _navMesh;
        private bool _isBuilt = false;
        
        public static NavigationManager Instance { get; private set; }
        public bool IsNavMeshReady => _isBuilt && _navMesh != null && _navMesh.isValid;
        
        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            
            if (autoRebakeOnLoad)
                Invoke(nameof(BuildNavMesh), 0.5f);
        }
        
        public void BuildNavMesh()
        {
            if (buildSettings == null)
                buildSettings = new NavMeshBuildSettings();
            
            buildSettings.agentRadius = agentRadius;
            buildSettings.agentHeight = agentHeight;
            buildSettings.maxSlope = maxSlope;
            buildSettings.stepHeight = stepHeight;
            buildSettings.minRegionArea = 1f;
            
            var sources = new List<NavMeshBuildSource>();
            var renderers = FindObjectsOfType<MeshRenderer>();
            var colliders = FindObjectsOfType<Collider>();
            
            foreach (var r in renderers)
            {
                if (r.gameObject.isStatic)
                {
                    var source = new NavMeshBuildSource
                    {
                        shape = NavMeshBuildSourceShape.MeshRenderer,
                        sourceObject = r,
                        area = 0
                    };
                    sources.Add(source);
                }
            }
            
            foreach (var c in colliders)
            {
                if (c.gameObject.isStatic && c is MeshCollider)
                {
                    var source = new NavMeshBuildSource
                    {
                        shape = NavMeshBuildSourceShape.MeshCollider,
                        sourceObject = c,
                        area = 0
                    };
                    sources.Add(source);
                }
            }
            
            var bounds = new Bounds(Vector3.zero, Vector3.one * 10000f);
            _navMesh = NavMeshBuilder.BuildNavMesh(sources, buildSettings, bounds);
            
            if (_navMesh != null)
            {
                NavMesh.AddNavMeshData(_navMesh);
                _isBuilt = true;
                Debug.Log($"[NavigationManager] NavMesh built with {sources.Count} sources");
            }
            else
            {
                Debug.LogWarning("[NavigationManager] Failed to build NavMesh");
            }
        }
        
        public NavMeshPath CalculatePath(Vector3 start, Vector3 target)
        {
            var path = new NavMeshPath();
            if (NavMesh.CalculatePath(start, target, NavMesh.AllAreas, path))
            {
                return path;
            }
            return null;
        }
        
        public float CalculatePathLength(Vector3 start, Vector3 target)
        {
            var path = CalculatePath(start, target);
            if (path == null || path.corners.Length < 2)
                return -1f;
            
            float length = 0f;
            for (int i = 1; i < path.corners.Length; i++)
            {
                length += Vector3.Distance(path.corners[i - 1], path.corners[i]);
            }
            return length;
        }
        
        public Vector3 FindNearestNavMeshPoint(Vector3 position, float maxDistance = 10f)
        {
            NavMeshHit hit;
            if (NavMesh.SamplePosition(transform.InverseTransformPoint(position), out NavMeshHit hit, 10f, NavMesh.AllAreas))
            {
                return transform.TransformPoint(hit.position);
            }
            return position;
        }
        
        public bool IsPositionOnNavMesh(Vector3 position, float tolerance = 0.5f)
        {
            return NavMesh.SamplePosition(position, out NavMeshHit _, tolerance, NavMesh.AllAreas);
        }
        
        public Vector3 GetRandomPointOnNavMesh(Vector3 center, float radius)
        {
            for (int i = 0; i < 10; i++)
            {
                Vector3 randomDir = Random.insideUnitSphere * radius;
                randomDir.y = 0;
                Vector3 testPos = center + randomDir;
                
                if (NavMesh.SamplePosition(testPos, out NavMeshHit hit, 5f, NavMesh.AllAreas))
                {
                    return hit.position;
                }
            }
            return center;
        }
        
        public void RebuildNavMesh()
        {
            if (_navMesh != null)
            {
                NavMesh.RemoveNavMeshData(_navMesh);
                _navMesh = null;
            }
            BuildNavMesh();
        }
        
        void OnDrawGizmos()
        {
            if (!showNavMesh || _navMesh == null) return;
            
            Gizmos.color = navMeshColor;
            var triangles = _navMesh.GetNavMeshTriangles();
            for (int i = 0; i < triangles.Length; i += 3)
            {
                if (i + 2 < triangles.Length)
                {
                    var v1 = triangles[i];
                    var v2 = triangles[i + 1];
                    var v3 = triangles[i + 2];
                    Gizmos.DrawLine(v1, v2);
                    Gizmos.DrawLine(v2, v3);
                    Gizmos.DrawLine(v3, v1);
                }
            }
        }
        
        void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
        }
    }
}