using UnityEngine;
using System.Collections.Generic;

namespace Cymatic.Materials
{
    /// <summary>
    /// Manages material creation and caching for the Cymatic render server.
    /// </summary>
    public class MaterialManager : MonoBehaviour
    {
        public static MaterialManager Instance { get; private set; }

        [Header("Material Cache")]
        [SerializeField] private Material[] _materialPresets;

        private Dictionary<string, Material> _materialCache = new Dictionary<string, Material>();
        private Dictionary<string, Material> _presetMaterials = new Dictionary<string, Material>();

        // Standard material templates
        private Material _defaultMaterial;
        private Material _wallMaterial;
        private Material _floorMaterial;
        private Material _ceilingMaterial;
        private Material _doorMaterial;
        private Material _windowMaterial;
        private Material _poiMaterial;
        private Material _navigationMarkerMaterial;
        private Material _highlightMaterial;
        private Material _poiHighlightMaterial;
        private Material _transparentMaterial;
        private Material _unlitColorMaterial;
        private Material _unlitTextureMaterial;

        void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);

            InitializeMaterials();
        }

        void Start()
        {
            // Load material presets if assigned
            foreach (var mat in _materialPresets)
            {
                if (mat != null)
                {
                    var key = mat.name;
                    if (!_presetMaterials.ContainsKey(key))
                        _presetMaterials[key] = mat;
                }
            }

            // Create default materials if not loaded
            EnsureDefaultMaterials();
        }

        void InitializeMaterials()
        {
            _presetMaterials.Clear();

            // Register preset materials
            if (_materialPresets != null)
            {
                foreach (var mat in _materialPresets)
                {
                    if (mat != null)
                    {
                        var key = mat.name;
                        if (!_presetMaterials.ContainsKey(key))
                            _presetMaterials[key] = mat;
                    }
                }
            }
        }

        void EnsureDefaultMaterials()
        {
            // Create default materials if missing
            if (_defaultMaterial == null)
                _defaultMaterial = CreateStandardMaterial("Default", Color.white);

            if (_wallMaterial == null)
                _wallMaterial = CreateStandardMaterial("Wall", new Color(0.85f, 0.85f, 0.85f));

            if (_floorMaterial == null)
                _floorMaterial = CreateStandardMaterial("Floor", new Color(0.7f, 0.65f, 0.55f));

            if (_ceilingMaterial == null)
                _ceilingMaterial = CreateStandardMaterial("Ceiling", Color.white);

            if (_doorMaterial == null)
                _doorMaterial = CreateStandardMaterial("Door", new Color(0.4f, 0.3f, 0.2f));

            if (_windowMaterial == null)
            {
                _windowMaterial = CreateTransparentMaterial("Window", new Color(0.7f, 0.85f, 1f, 0.3f));
            }

            if (_poiMaterial == null)
                _poiMaterial = CreateStandardMaterial("POI", Color.yellow);

            if (_navigationMarkerMaterial == null)
            {
                _navigationMarkerMaterial = CreateUnlitMaterial("NavMarker", Color.cyan);
            }

            if (_highlightMaterial == null)
            {
                _highlightMaterial = CreateStandardMaterial("Highlight", Color.yellow);
            }

            if (_poiHighlightMaterial == null)
            {
                _poiHighlightMaterial = CreateStandardMaterial("POIHighlight", new Color(1f, 0.8f, 0f));
            }

            if (_transparentMaterial == null)
                _transparentMaterial = CreateTransparentMaterial("Transparent", new Color(1, 1, 1, 0.5f));

            if (_unlitColorMaterial == null)
                _unlitColorMaterial = new Material(Shader.Find("Cymatic/Unlit/Color"));

            if (_unlitTextureMaterial == null)
                _unlitTextureMaterial = new Material(Shader.Find("Cymatic/Unlit/Texture"));
        }

        Material CreateStandardMaterial(string name, Color color)
        {
            var mat = new Material(Shader.Find("Cymatic/Standard"))
            {
                name = name
            };
            mat.color = color;
            mat.SetFloat("_Metallic", 0f);
            mat.SetFloat("_Glossiness", 0.3f);
            return mat;
        }

        Material CreateTransparentMaterial(string name, Color color)
        {
            var mat = new Material(Shader.Find("Cymatic/Standard"))
            {
                name = name
            };
            mat.color = color;
            mat.SetFloat("_Metallic", 0f);
            mat.SetFloat("_Glossiness", 0.5f);
            mat.SetFloat("_Mode", 2); // Fade mode
            mat.SetInt("_SrcBlend", (int)UnityEngine.Rendering.BlendMode.SrcAlpha);
            mat.SetInt("_DstBlend", (int)UnityEngine.Rendering.BlendMode.OneMinusSrcAlpha);
            mat.SetInt("_ZWrite", 0);
            mat.DisableKeyword("_ALPHATEST_ON");
            mat.EnableKeyword("_ALPHABLEND_ON");
            mat.DisableKeyword("_ALPHAPREMULTIPLY_ON");
            mat.renderQueue = 3000;
            return mat;
        }

        Material CreateUnlitMaterial(string name, Color color)
        {
            var mat = new Material(Shader.Find("Cymatic/Unlit/Color"))
            {
                name = name
            };
            mat.color = color;
            return mat;
        }

        // Public accessors
        public Material GetDefaultMaterial() => EnsureMaterial(ref _defaultMaterial, () => CreateStandardMaterial("Default", Color.white));
        public Material GetWallMaterial() => EnsureMaterial(ref _wallMaterial, () => CreateStandardMaterial("Wall", new Color(0.85f, 0.85f, 0.85f)));
        public Material GetFloorMaterial() => EnsureMaterial(ref _floorMaterial, () => CreateStandardMaterial("Floor", new Color(0.7f, 0.65f, 0.55f)));
        public Material GetCeilingMaterial() => EnsureMaterial(ref _ceilingMaterial, () => CreateStandardMaterial("Ceiling", Color.white));
        public Material GetDoorMaterial() => EnsureMaterial(ref _doorMaterial, () => CreateStandardMaterial("Door", new Color(0.4f, 0.3f, 0.2f)));
        public Material GetWindowMaterial() => EnsureMaterial(ref _windowMaterial, () => CreateTransparentMaterial("Window", new Color(0.7f, 0.85f, 1f, 0.3f)));
        public Material GetPOIMaterial() => EnsureMaterial(ref _poiMaterial, () => CreateStandardMaterial("POI", Color.yellow));
        public Material GetNavigationMarkerMaterial() => EnsureMaterial(ref _navigationMarkerMaterial, () => CreateUnlitMaterial("NavMarker", Color.cyan));
        public Material GetHighlightMaterial() => EnsureMaterial(ref _highlightMaterial, () => CreateStandardMaterial("Highlight", Color.yellow));
        public Material GetPOIHighlightMaterial() => EnsureMaterial(ref _poiHighlightMaterial, () => CreateStandardMaterial("POIHighlight", new Color(1f, 0.8f, 0f)));
        public Material GetTransparentMaterial() => EnsureMaterial(ref _transparentMaterial, () => CreateTransparentMaterial("Transparent", new Color(1, 1, 1, 0.5f)));
        public Material GetUnlitColorMaterial() => EnsureMaterial(ref _unlitColorMaterial, () => new Material(Shader.Find("Cymatic/Unlit/Color")));
        public Material GetUnlitTextureMaterial() => EnsureMaterial(ref _unlitTextureMaterial, () => new Material(Shader.Find("Cymatic/Unlit/Texture")));

        Material EnsureMaterial(ref Material field, System.Func<Material> creator)
        {
            if (field == null)
                field = creator();
            return field;
        }

        // Get material by name or create default
        public Material GetMaterial(string name)
        {
            if (_presetMaterials.TryGetValue(name, out var mat))
                return mat;

            if (_materialCache.TryGetValue(name, out var cached))
                return cached;

            // Create fallback
            var fallback = new Material(Shader.Find("Cymatic/Standard"))
            {
                name = name
            };
            _materialCache[name] = fallback;
            return fallback;
        }

        public Material CreateMaterial(string name, Shader shader = null, Color? color = null, Texture texture = null)
        {
            var shaderObj = shader != null ? shader : Shader.Find("Cymatic/Standard");
            var mat = new Material(shaderObj)
            {
                name = name
            };

            if (color.HasValue)
                mat.color = color.Value;

            _materialCache[name] = mat;
            return mat;
        }

        public Material GetPooledMaterial(string baseMaterialName, Color tint)
        {
            var cacheKey = $"{baseMaterialName}_{ColorUtility.ToHtmlStringRGBA(tint)}";

            if (_materialCache.TryGetValue(cacheKey, out var cached))
                return cached;

            var baseMat = GetMaterial(baseMaterialName);
            var newMat = new Material(baseMat)
            {
                name = $"{baseMaterialName}_{ColorUtility.ToHtmlStringRGBA(tint)}"
            };
            newMat.color = tint;

            _materialCache[cacheKey] = newMat;
            return newMat;
        }

        public void ClearCache()
        {
            foreach (var kvp in _materialCache)
            {
                if (kvp.Value != null)
                    Destroy(kvp.Value);
            }
            _materialCache.Clear();
        }
    }
}
