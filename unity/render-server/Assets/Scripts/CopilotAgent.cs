using System.Collections.Generic;
using UnityEngine;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json;

namespace Cymatic
{
    // P0 FIX: Minimal Outline stub if package not present (prevents compile error CopilotAgent.cs:223)
    // If real Outline exists elsewhere, this will be ignored due to duplicate check via #if guard
#if !HAS_OUTLINE
    public class Outline : MonoBehaviour
    {
        public enum Mode { OutlineAll, OutlineVisible, OutlineHidden, OutlineAndSilhouette }
        public Mode OutlineMode;
        public Color OutlineColor = Color.yellow;
        public float OutlineWidth = 5f;
    }
#endif

    /// <summary>
    /// Copilot Agent - Runs in Unity Render Server
    /// Handles user queries, provides guidance, highlights objects, controls navigation
    /// </summary>
    public class CopilotAgent : MonoBehaviour
    {
        [Header("Configuration")]
        [SerializeField] private string backendUrl = "http://localhost:8000";
        [SerializeField] private string renderServerId = "render-server-01";
        
        // State
        private bool _isEnabled = true;
        private string _currentSessionId;
        private CopilotPolicyData _policy;
        
        // Components
        private EventBridge _eventBridge;
        private SceneLoader _sceneLoader;
        private StereoCameraRig _stereoRig;
        private InputManager _inputManager;
        
        // Knowledge base
        private Dictionary<string, object> _knowledgeBase;
        private string _sceneContext;
        
        // Allowed actions
        private readonly HashSet<string> _allowedActions = new HashSet<string>
        {
            "highlight_object",
            "show_label",
            "move_to_point",
            "open_menu",
            "change_material",
            "pause_tour",
            "resume_tour",
            "play_audio_hint",
            "answer_question"
        };
        
        public void Initialize(string sessionId, CopilotPolicyData policy, EventBridge eventBridge, SceneLoader sceneLoader, StereoCameraRig stereoRig, InputManager inputManager)
        {
            _currentSessionId = sessionId;
            _policy = policy;
            _eventBridge = eventBridge;
            _sceneLoader = sceneLoader;
            _stereoRig = stereoRig;
            _inputManager = inputManager;

            // Respect server policy allowlist instead of hardcoded set.
            _allowedActions.Clear();
            var configured = policy?.allowed_actions;
            if (configured != null && configured.Count > 0)
            {
                foreach (var a in configured) _allowedActions.Add(a);
            }
            else
            {
                // Fail-closed: no actions when policy omits allowlist.
                Debug.LogWarning("[CopilotAgent] Empty allowed_actions; all actions denied");
            }
            
            _knowledgeBase = policy.knowledge_base != null ? JsonConvert.DeserializeObject<Dictionary<string, object>>(policy.knowledge_base) : new Dictionary<string, object>();
            
            // Build scene context for LLM
            BuildSceneContext();
            
            // Subscribe to copilot messages
            if (_inputManager != null)
                _inputManager.OnCopilotMessage += HandleCopilotMessage;
            
            _isEnabled = policy != null && policy.enabled;
            
            Debug.Log($"[CopilotAgent] Initialized for session {sessionId}");
        }
        
        private void BuildSceneContext()
        {
            if (_sceneLoader == null) return;
            var package = _sceneLoader.CurrentPackage;
            if (package == null) return;
            
            var navNames = package.navigation?.points != null ? string.Join(", ", package.navigation.points.ConvertAll(p => p.name)) : "none";
            _sceneContext = $"Current scene: {package.metadata?.title ?? "unknown"} ({package.domain}). " +
                          $"Navigation points: {navNames}. " +
                          $"Entities: {package.entities?.Count ?? 0} objects. " +
                          $"Copilot personality: {_policy?.personality}. " +
                          $"Supported languages: {string.Join(", ", _policy?.languages ?? new List<string>())}.";
        }
        
        private async void HandleCopilotMessage(string message)
        {
            if (!_isEnabled) return;
            
            Debug.Log($"[CopilotAgent] Received message: {message}");
            
            try
            {
                // Send to LLM Router for processing
                var response = await ProcessMessage(message);
                
                // Execute any actions from response
                await ExecuteActions(response.actions);
                
                // Send response back
                if (_eventBridge != null)
                {
                    await _eventBridge.SendEvent(_currentSessionId, "copilot_response", new
                    {
                        response = response.text,
                        actions = response.actions
                    });
                }
            }
            catch (System.Exception e)
            {
                Debug.LogError($"[CopilotAgent] Error processing message: {e.Message}");
            }
        }
        
        private async UniTask<CopilotResponse> ProcessMessage(string message)
        {
            var request = new
            {
                messages = new[]
                {
                    new { role = "system", content = BuildSystemPrompt() },
                    new { role = "user", content = message }
                },
                task_type = "copilot_chat",
                sensitivity = "internal",
                temperature = 0.7,
                max_tokens = 500,
                response_format = new { type = "json_object" }
            };
            
            using (var webRequest = new UnityEngine.Networking.UnityWebRequest($"{backendUrl}/v1/chat/completions", "POST"))
            {
                var json = JsonConvert.SerializeObject(request);
                var bytes = System.Text.Encoding.UTF8.GetBytes(json);
                webRequest.uploadHandler = new UnityEngine.Networking.UploadHandlerRaw(bytes);
                webRequest.downloadHandler = new UnityEngine.Networking.DownloadHandlerBuffer();
                webRequest.SetRequestHeader("Content-Type", "application/json");
                // P0 FIX: 131 AuthToken private -> EventBridge now exposes public AuthToken / GetAuthToken()
                var token = _eventBridge != null ? _eventBridge.AuthToken : null;
                if (!string.IsNullOrEmpty(token))
                    webRequest.SetRequestHeader("Authorization", $"Bearer {token}");
                
                await webRequest.SendWebRequest();
                
                if (webRequest.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
                {
                    var response = JsonConvert.DeserializeObject<LLMResponse>(webRequest.downloadHandler.text);
                    if (response?.choices != null && response.choices.Count > 0)
                    {
                        var content = response.choices[0].message.content;
                        return JsonConvert.DeserializeObject<CopilotResponse>(content);
                    }
                    return new CopilotResponse { text = webRequest.downloadHandler.text, actions = new List<CopilotAction>() };
                }
                else
                {
                    throw new System.Exception($"LLM request failed: {webRequest.error}");
                }
            }
        }
        
        private string BuildSystemPrompt()
        {
            return $@"You are a helpful AI copilot inside a VR simulation.
            
Scene Context: {_sceneContext}

Your capabilities:
{string.Join("\n", _allowedActions)}

Current policy:
- Personality: {_policy?.personality}
- Languages: {string.Join(", ", _policy?.languages ?? new List<string>())}
- Default language: {_policy?.default_language}

When responding, always return JSON with:
{{
  ""text"": ""Your verbal response to the user"",
  ""actions"": [
    {{""type"": ""action_type"", ""params"": {{...}}}}
  ]
}}

Only use allowed actions. Be concise and helpful. If you cannot perform an action, explain why.";
        }
        
        private async UniTask ExecuteActions(List<CopilotAction> actions)
        {
            if (actions == null) return;
            foreach (var action in actions)
            {
                if (action == null || string.IsNullOrEmpty(action.type)) continue;
                if (!_allowedActions.Contains(action.type))
                {
                    Debug.LogWarning($"[CopilotAgent] Action not allowed: {action.type}");
                    continue;
                }
                
                switch (action.type)
                {
                    case "highlight_object":
                        await HighlightObject(action.@params);
                        break;
                    case "show_label":
                        await ShowLabel(action.@params);
                        break;
                    case "move_to_point":
                        await MoveToPoint(action.@params);
                        break;
                    case "open_menu":
                        OpenMenu(action.@params);
                        break;
                    case "change_material":
                        await ChangeMaterial(action.@params);
                        break;
                    case "pause_tour":
                        PauseTour();
                        break;
                    case "resume_tour":
                        ResumeTour();
                        break;
                    case "play_audio_hint":
                        await PlayAudioHint(action.@params);
                        break;
                    case "answer_question":
                        // Already handled by text response
                        break;
                }
            }
        }
        
        private async UniTask HighlightObject(Dictionary<string, object> @params)
        {
            if (@params == null) return;
            if (@params.TryGetValue("object_id", out var objId))
            {
                var obj = GameObject.Find(objId.ToString());
                if (obj != null)
                {
                    var outline = obj.GetComponent<Outline>();
                    if (outline == null) outline = obj.AddComponent<Outline>();
                    outline.OutlineMode = Outline.Mode.OutlineAll;
                    outline.OutlineColor = Color.yellow;
                    outline.OutlineWidth = 5f;
                    
                    // Auto-remove after delay
                    await UniTask.Delay(5000);
                    if (outline != null) Destroy(outline);
                }
            }
        }
        
        private async UniTask ShowLabel(Dictionary<string, object> @params)
        {
            if (@params == null) return;
            if (@params.TryGetValue("object_id", out var objId) && @params.TryGetValue("text", out var text))
            {
                var obj = GameObject.Find(objId.ToString());
                if (obj != null)
                {
                    var label = obj.GetComponentInChildren<TMPro.TextMeshProUGUI>();
                    GameObject labelGO = null;
                    if (label == null)
                    {
                        labelGO = new GameObject("Label");
                        labelGO.transform.SetParent(obj.transform);
                        label = labelGO.AddComponent<TMPro.TextMeshProUGUI>();
                    }
                    else
                    {
                        labelGO = label.gameObject;
                    }
                    
                    label.text = text.ToString();
                    label.fontSize = 24;
                    label.color = Color.white;
                    label.alignment = TMPro.TextAlignmentOptions.Center;
                    
                    // Position above object
                    var rend = obj.GetComponent<Renderer>();
                    float yOffset = rend != null ? rend.bounds.size.y + 1 : 1f;
                    labelGO.transform.localPosition = new Vector3(0, yOffset, 0);
                    if (Camera.main != null)
                    {
                        labelGO.transform.LookAt(Camera.main.transform);
                        labelGO.transform.Rotate(0, 180, 0);
                    }
                }
            }
            await UniTask.CompletedTask;
        }
        
        private async UniTask MoveToPoint(Dictionary<string, object> @params)
        {
            if (@params == null) return;
            if (@params.TryGetValue("point_id", out var pointId))
            {
                if (_stereoRig == null)
                {
                    Debug.LogWarning("[CopilotAgent] StereoRig is null, cannot teleport");
                    return;
                }
                // P0 FIX: 268 Teleport int vs string -> StereoCameraRig now has string overload
                _stereoRig.TeleportToNavigationPoint(pointId.ToString());
            }
            await UniTask.CompletedTask;
        }
        
        private void OpenMenu(Dictionary<string, object> @params)
        {
            // Trigger menu UI - P0 FIX: SendEvent returns UniTask, need Forget
            if (_eventBridge != null)
                _eventBridge.SendEvent(_currentSessionId, "copilot_open_menu", new { }).Forget();
        }
        
        private async UniTask ChangeMaterial(Dictionary<string, object> @params)
        {
            if (@params == null) return;
            if (@params.TryGetValue("object_id", out var objId) && @params.TryGetValue("material", out var matName))
            {
                var obj = GameObject.Find(objId.ToString());
                if (obj != null)
                {
                    var renderer = obj.GetComponent<Renderer>();
                    if (renderer != null)
                    {
                        var newMat = Resources.Load<Material>($"Materials/{matName}");
                        if (newMat != null)
                        {
                            renderer.material = newMat;
                        }
                    }
                }
            }
            await UniTask.CompletedTask;
        }
        
        private void PauseTour()
        {
            // Pause navigation - P0 FIX: use Forget
            if (_eventBridge != null)
                _eventBridge.SendEvent(_currentSessionId, "copilot_pause_tour", new { }).Forget();
        }
        
        private void ResumeTour()
        {
            // Resume navigation - P0 FIX: use Forget
            if (_eventBridge != null)
                _eventBridge.SendEvent(_currentSessionId, "copilot_resume_tour", new { }).Forget();
        }
        
        private async UniTask PlayAudioHint(Dictionary<string, object> @params)
        {
            if (@params == null) return;
            if (@params.TryGetValue("audio_id", out var audioId))
            {
                // Play audio clip
                var clip = Resources.Load<AudioClip>($"Audio/Hints/{audioId}");
                if (clip != null)
                {
                    var audioSource = GetComponent<AudioSource>();
                    if (audioSource == null) audioSource = gameObject.AddComponent<AudioSource>();
                    audioSource.PlayOneShot(clip);
                }
            }
            await UniTask.CompletedTask;
        }
        
        private void OnDestroy()
        {
            if (_inputManager != null)
                _inputManager.OnCopilotMessage -= HandleCopilotMessage;
        }
    }
    
    [System.Serializable]
    public class CopilotResponse
    {
        public string text;
        public List<CopilotAction> actions = new List<CopilotAction>();
    }
    
    [System.Serializable]
    public class CopilotAction
    {
        public string type;
        public Dictionary<string, object> @params = new Dictionary<string, object>();
    }
    
    [System.Serializable]
    public class LLMResponse
    {
        public List<Choice> choices = new List<Choice>();
    }
    
    [System.Serializable]
    public class Choice
    {
        public Message message = new Message();
    }
    
    [System.Serializable]
    public class Message
    {
        public string role;
        public string content;
    }
}
