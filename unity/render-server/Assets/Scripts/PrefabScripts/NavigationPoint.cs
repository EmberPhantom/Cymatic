using UnityEngine;
using UnityEngine.AI;
using System.Collections.Generic;

namespace Cymatic.Prefabs
{
    /// <summary>
    /// Navigation point for wayfinding and tour navigation.
    /// </summary>
    public class NavigationPoint : MonoBehaviour
    {
        [Header("Navigation Point Properties")]
        [SerializeField] private string pointId;
        [SerializeField] private string pointName;
        [SerializeField] private string description;
        [SerializeField] private NavPointType pointType = NavPointType.Waypoint;
        
        [Header("Connections")]
        [SerializeField] private NavigationPoint[] connectedPoints;
        [SerializeField] private float[] connectionWeights;
        
        [Header("Navigation")]
        [SerializeField] private float stopDistance = 1.5f;
        [SerializeField] private bool isTeleportPoint = false;
        [SerializeField] private bool isStartPoint = false;
        [SerializeField] private bool isEndPoint = false;
        
        [Header("Tour")]
        [SerializeField] private bool isTourStop = false;
        [SerializeField] private float pauseDuration = 5f;
        [SerializeField] private string tourAudioClip;
        
        [Header("Visual")]
        [SerializeField] private GameObject waypointMarker;
        [SerializeField] private float markerScale = 1f;
        [SerializeField] private Color markerColor = Color.cyan;
        
        private SphereCollider _triggerCollider;
        private NavMeshAgent _playerAgent;
        private LineRenderer _pathLine;
        private bool _isActive = false;
        
        public string PointId => string.IsNullOrEmpty(pointId) ? gameObject.name : pointId;
        public string PointName => pointName;
        public string Description => description;
        public NavPointType PointType => pointType;
        public Transform[] ConnectedPoints => GetConnectedTransforms();
        public float StopDistance => stopDistance;
        public bool IsTeleportPoint => isTeleportPoint;
        public bool IsStartPoint => isStartPoint;
        public bool IsEndPoint => isEndPoint;
        public bool IsTourStop => isTourStop;
        public float PauseDuration => pauseDuration;
        
        public event System.Action<NavigationPoint> OnPlayerArrived;
        public event System.Action<NavigationPoint> OnPlayerDeparted;
        
        void Awake()
        {
            if (string.IsNullOrEmpty(pointId))
                pointId = gameObject.name;
            
            // Setup trigger collider
            var collider = GetComponent<SphereCollider>();
            if (collider == null)
                collider = gameObject.AddComponent<SphereCollider>();
            collider.isTrigger = true;
            collider.radius = 2f;
            
            // Find player NavMeshAgent
            var player = GameObject.FindGameObjectWithTag("Player");
            if (player != null)
                _playerAgent = player.GetComponent<NavMeshAgent>();
        }
        
        void Start()
        {
            if (waypointMarker != null)
            {
                waypointMarker.transform.localScale = Vector3.one * markerScale;
                var renderer = waypointMarker.GetComponent<Renderer>();
                if (renderer != null)
                    renderer.material.color = markerColor;
            }
        }
        
        void OnTriggerEnter(Collider other)
        {
            if (!other.CompareTag("Player") && !other.CompareTag("MainCamera"))
                return;
            
            _isActive = true;
            OnPlayerArrived?.Invoke(this);
        }
        
        void OnTriggerExit(Collider other)
        {
            if (!other.CompareTag("Player") && !other.CompareTag("MainCamera"))
                return;
            
            _isActive = false;
            OnPlayerDeparted?.Invoke(this);
        }
        
        public Transform[] GetConnectedTransforms()
        {
            if (connectedPoints == null) return new Transform[0];
            
            var transforms = new List<Transform>();
            foreach (var point in connectedPoints)
            {
                if (point != null)
                    transforms.Add(point.transform);
            }
            return transforms.ToArray();
        }
        
        public float GetConnectionWeight(NavigationPoint target)
        {
            if (connectionWeights == null || connectionWeights.Length == 0)
                return 1f;
            
            for (int i = 0; i < connectedPoints.Length; i++)
            {
                if (connectedPoints[i] == target)
                    return i < connectionWeights.Length ? connectionWeights[i] : 1f;
            }
            return 1f;
        }
        
        public void NavigateToThisPoint()
        {
            if (_playerAgent != null && _playerAgent.isOnNavMesh)
            {
                _playerAgent.SetDestination(transform.position);
                _playerAgent.stoppingDistance = 1.5f;
            }
        }
        
        public bool IsPlayerHere(Collider playerCollider)
        {
            var collider = GetComponent<Collider>();
            return collider.bounds.Contains(playerCollider.bounds.center);
        }
        
        private void OnDrawGizmosSelected()
        {
            Gizmos.color = Color.cyan;
            Gizmos.DrawWireSphere(transform.position, 2f);
            
            if (connectedPoints != null)
            {
                Gizmos.color = Color.green;
                foreach (var point in connectedPoints)
                {
                    if (point != null)
                        Gizmos.DrawLine(transform.position, point.transform.position);
                }
            }
        }
        
        public void SetActiveState(bool active)
        {
            _isActive = active;
            if (waypointMarker != null)
                waypointMarker.SetActive(active);
        }
    }
    
    public enum NavPointType
    {
        Waypoint,
        StartPoint,
        EndPoint,
        DecisionPoint,
        POI,
        Teleport,
        RestArea
    }
}