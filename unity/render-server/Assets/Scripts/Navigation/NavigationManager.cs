using UnityEngine;
using UnityEngine.AI;
using System.Collections.Generic;

namespace Cymatic.Navigation
{
    /// <summary>
    /// Manages navigation mesh and pathfinding for the scene.
    /// P0 FIX: Use NavMeshBuilder.BuildNavMeshData (correct 2022.3 signature) + AddNavMeshData
    /// </summary>
    public class NavigationManager : MonoBehaviour
    {
        [Header("NavMesh Settings")]
        [SerializeField] private NavMeshData navMeshData;
        [SerializeField] private NavMeshBuildSettings buildSettings;
        [SerializeField] private bool autoRebakeOnLoad = false; // MVP: disabled to avoid 2nd NavMesh build hitch; SceneLoader builds explicitly with 50m bound
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
        private NavMeshDataInstance _navMeshInstance;
        private bool _isBuilt = false;
        
        public static NavigationManager Instance { get; private set; }
        public bool IsNavMeshReady => _isBuilt && _navMesh != null;
        
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
            // Ensure valid build settings
            if (buildSettings.agentTypeID == 0)
            {
                buildSettings.agentRadius = agentRadius;
                buildSettings.agentHeight = agentHeight;
                buildSettings.agentSlope = maxSlope;
                buildSettings.agentClimb = stepHeight;
                buildSettings.minRegionArea = 1f;
            }
            else
            {
                buildSettings.agentRadius = agentRadius;
                buildSettings.agentHeight = agentHeight;
                buildSettings.agentSlope = maxSlope;
                buildSettings.agentClimb = stepHeight;
                buildSettings.minRegionArea = 1f;
            }
            
            var sources = new List<NavMeshBuildSource>();
#if UNITY_2022_3_OR_NEWER
            var renderers = UnityEngine.Object.FindObjectsByType<MeshRenderer>(FindObjectsSortMode.None);
            var colliders = UnityEngine.Object.FindObjectsByType<Collider>(FindObjectsSortMode.None);
#else
            var renderers = FindObjectsOfType<MeshRenderer>();
            var colliders = FindObjectsOfType<Collider>();
#endif
            
            foreach (var r in renderers)
            {
                if (r.gameObject.isStatic)
                {
                    var mf = r.GetComponent<MeshFilter>();
                    var source = new NavMeshBuildSource
                    {
                        shape = NavMeshBuildSourceShape.Mesh,
                        sourceObject = mf != null ? mf.sharedMesh : null,
                        transform = r.transform.localToWorldMatrix,
                        area = 0
                    };
                    // Fallback if mesh null: use bounds
                    if (source.sourceObject == null)
                    {
                        source.shape = NavMeshBuildSourceShape.Box;
                        source.size = r.bounds.size;
                        source.transform = Matrix4x4.TRS(r.bounds.center, Quaternion.identity, Vector3.one);
                    }
                    sources.Add(source);
                }
            }
            
            foreach (var c in colliders)
            {
                if (c.gameObject.isStatic && c is MeshCollider meshCol && meshCol.sharedMesh != null)
                {
                    var source = new NavMeshBuildSource
                    {
                        shape = NavMeshBuildSourceShape.Mesh,
                        sourceObject = meshCol.sharedMesh,
                        transform = c.transform.localToWorldMatrix,
                        area = 0
                    };
                    sources.Add(source);
                }
                else if (c.gameObject.isStatic && c is BoxCollider box)
                {
                    var source = new NavMeshBuildSource
                    {
                        shape = NavMeshBuildSourceShape.Box,
                        size = box.size,
                        transform = Matrix4x4.TRS(box.transform.position, box.transform.rotation, box.transform.lossyScale),
                        area = 0
                    };
                    sources.Add(source);
                }
            }
            
            var bounds = new Bounds(Vector3.zero, Vector3.one * 50f); // MVP 50m bound (was 10km³ = 10000³, froze 2-5s)
            // P0 FIX: correct signature for Unity 2022.3: BuildNavMeshData(settings, sources, bounds, pos, rot)
            var newData = NavMeshBuilder.BuildNavMeshData(buildSettings, sources, bounds, Vector3.zero, Quaternion.identity);
            
            if (newData != null)
            {
                // Remove previous instance if exists
                if (_navMeshInstance.valid)
                    _navMeshInstance.Remove();
                if (_navMesh != null)
                {
                    // previous data will be GC'd after Remove
                }
                _navMesh = newData;
                _navMeshInstance = NavMesh.AddNavMeshData(_navMesh);
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
            if (NavMesh.SamplePosition(position, out NavMeshHit hit, maxDistance, NavMesh.AllAreas))
            {
                return hit.position;
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
            if (_navMeshInstance.valid)
            {
                _navMeshInstance.Remove();
                _navMeshInstance = default;
            }
            if (_navMesh != null)
            {
                // Destroy old navmesh data
                // Note: Do not DestroyImmediate; let GC handle
                _navMesh = null;
            }
            _isBuilt = false;
            BuildNavMesh();
        }
        
        void OnDrawGizmos()
        {
            if (!showNavMesh) return;
            // P0 FIX: NavMeshData does not have GetNavMeshTriangles; use CalculateTriangulation
            var triangulation = NavMesh.CalculateTriangulation();
            if (triangulation.vertices == null || triangulation.indices == null) return;
            Gizmos.color = navMeshColor;
            for (int i = 0; i < triangulation.indices.Length; i += 3)
            {
                if (i + 2 >= triangulation.indices.Length) break;
                var v0 = triangulation.vertices[triangulation.indices[i]];
                var v1 = triangulation.vertices[triangulation.indices[i+1]];
                var v2 = triangulation.vertices[triangulation.indices[i+2]];
                Gizmos.DrawLine(v0, v1);
                Gizmos.DrawLine(v1, v2);
                Gizmos.DrawLine(v2, v0);
            }
        }
        
        void OnDestroy()
        {
            if (Instance == this)
                Instance = null;
            if (_navMeshInstance.valid)
                _navMeshInstance.Remove();
        }
    }
}
