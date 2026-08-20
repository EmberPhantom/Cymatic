using UnityEngine;
using UnityEngine.AI;

namespace Cymatic.Prefabs
{
    /// <summary>
    /// Component for Points of Interest in heritage/tourism simulations.
    /// </summary>
    public class POIComponent : MonoBehaviour
    {
        [Header("POI Properties")]
        [SerializeField] private string poiName;
        [SerializeField] private POIType poiType = POIType.Generic;
        [SerializeField] private string description;
        [SerializeField] private bool hasNarration = true;
        [SerializeField] private AudioClip narrationClip;
        [SerializeField] private string narrationText;
        
        [Header("Interaction")]
        [SerializeField] private float interactionRadius = 2f;
        [SerializeField] private bool requiresProximity = true;
        [SerializeField] private float narrationTriggerDistance = 3f;
        
        [Header("Navigation")]
        [SerializeField] private Transform[] connectedPOIs;
        [SerializeField] private float navigationWeight = 1f;
        
        [Header("Visual")]
        [SerializeField] private GameObject highlightEffect;
        [SerializeField] private Material highlightMaterial;
        
        [Header("Historical/Cultural")]
        [SerializeField] private string historicalPeriod;
        [SerializeField] private string culturalSignificance;
        [SerializeField] private int constructionYear;
        
        private SphereCollider _triggerCollider;
        private Material _originalMaterial;
        private Renderer[] _renderers;
        private bool _isHighlighted = false;
        
        public string POIName => poiName;
        public POIType POIType => poiType;
        public string Description => description;
        public bool HasNarration => hasNarration && (narrationClip != null || !string.IsNullOrEmpty(narrationText));
        public float InteractionRadius => interactionRadius;
        public Transform[] ConnectedPOIs => connectedPOIs;
        
        public event System.Action<POIComponent> OnPlayerEnter;
        public event System.Action<POIComponent> OnPlayerExit;
        
        void Awake()
        {
            _triggerCollider = GetComponent<SphereCollider>();
            if (_triggerCollider == null)
            {
                _triggerCollider = gameObject.AddComponent<SphereCollider>();
            }
            _triggerCollider.isTrigger = true;
            _triggerCollider.radius = interactionRadius;
            
            _renderers = GetComponentsInChildren<Renderer>(true);
            if (_renderers.Length > 0)
                _originalMaterial = _renderers[0].sharedMaterial;
        }
        
        void OnTriggerEnter(Collider other)
        {
            if (!requiresProximity) return;
            if (other.CompareTag("Player") || other.CompareTag("MainCamera"))
            {
                _isHighlighted = true;
                ApplyHighlight(true);
                OnPlayerEnter?.Invoke(this);
            }
        }
        
        void OnTriggerExit(Collider other)
        {
            if (other.CompareTag("Player") || other.CompareTag("MainCamera"))
            {
                _isHighlighted = false;
                ApplyHighlight(false);
                OnPlayerExit?.Invoke(this);
            }
        }
        
        public void PlayNarration(AudioSource audioSource)
        {
            if (!HasNarration || audioSource == null) return;
            
            if (narrationClip != null)
            {
                audioSource.clip = narrationClip;
                audioSource.Play();
            }
            else if (!string.IsNullOrEmpty(narrationText))
            {
                // Trigger TTS via event system
                // This would integrate with the TTS system
            }
        }
        
        public void SetHighlighted(bool highlighted)
        {
            _isHighlighted = highlighted;
            ApplyHighlight(highlighted);
        }
        
        private void ApplyHighlight(bool highlighted)
        {
            if (highlightEffect != null)
                highlightEffect.SetActive(highlighted);
            
            if (highlightMaterial != null && _renderers != null)
            {
                foreach (var renderer in _renderers)
                {
                    if (highlighted)
                    {
                        var mats = renderer.materials;
                        var newMats = new Material[mats.Length + 1];
                        System.Array.Copy(mats, newMats, mats.Length);
                        newMats[mats.Length - 1] = highlightMaterial;
                        renderer.materials = newMats;
                    }
                    else
                    {
                        // Restore original materials - would need to store originals
                    }
                }
            }
        }
        
        public float GetDistanceToPlayer(Vector3 playerPosition)
        {
            return Vector3.Distance(transform.position, playerPosition);
        }
        
        public bool IsPlayerInRange(Vector3 playerPosition, float additionalRange = 0f)
        {
            return Vector3.Distance(transform.position, GetComponent<Collider>().ClosestPointOnBounds(Vector3.zero)) <= interactionRadius;
        }
        
        private void OnDrawGizmosSelected()
        {
            Gizmos.color = Color.yellow;
            Gizmos.DrawWireSphere(transform.position, interactionRadius);
            
            Gizmos.color = Color.cyan;
            if (connectedPOIs != null)
            {
                foreach (var poi in connectedPOIs)
                {
                    if (poi != null)
                        Gizmos.DrawLine(transform.position, poi.position);
                }
            }
        }
    }
    
    public enum POIType
    {
        Generic,
        Entrance,
        Exit,
        Landmark,
        Artifact,
        Exhibit,
        InformationPoint,
        RestArea,
        Viewpoint,
        Sacred,
        Historical
    }
}