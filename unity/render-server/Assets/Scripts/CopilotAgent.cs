using System.Collections.Generic;
using UnityEngine;
using Cysharp.Threading.Tasks;
using Newtonsoft.Json;

namespace Cymatic
{
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
            
            _knowledgeBase = policy.knowledge_base != null ? JsonConvert.DeserializeObject<Dictionary<string, object>>(policy.knowledge_base) : new Dictionary<string, object>();
            
            // Build scene context for LLM
            BuildSceneContext();
            
            // Subscribe to copilot messages
            _inputManager.OnCopilotMessage += HandleCopilotMessage;
            
            _isEnabled = policy.enabled;
            
            Debug.Log($"[CopilotAgent] Initialized for session {sessionId}");
        }
        
        private void BuildSceneContext()
        {
            var package = _sceneLoader.CurrentPackage;
            if (package == null) return;
            
            _sceneContext = $"Current scene: {package.metadata.title} ({package.domain}). " +
                          $"Navigation points: {string.Join(", ", package.navigation.points.ConvertAll(p => p.name))}. " +
                          $"Entities: {package.entities.Count} objects. " +
                          $"Copilot personality: {_policy.personality}. " +
                          $"Supported languages: {string.Join(", ", _policy.languages)}.";
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
                await _eventBridge.SendEvent(_currentSessionId, "copilot_response", new
                {
                    response = response.text,
                    actions = response.actions
                });
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
                webRequest.SetRequestHeader("Authorization", $"Bearer {_eventBridge.AuthToken}");
                
                await webRequest.SendWebRequest();
                
                if (webRequest.result == UnityEngine.Networking.UnityWebRequest.Result.Success)
                {
                    var response = JsonConvert.DeserializeObject<LLMResponse>(webRequest.downloadHandler.text);
                    var content = response.choices[0].message.content;
                    return JsonConvert.DeserializeObject<CopilotResponse>(content);
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
- Personality: {_policy.personality}
- Languages: {string.Join(", ", _policy.languages)}
- Default language: {_policy.default_language}

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
            foreach (var action in actions)
            {
                if (!_allowedActions.Contains(action.type))
                {
                    Debug.LogWarning($"[CopilotAgent] Action not allowed: {action.type}");
                    continue;
                }
                
                switch (action.type)
                {
                    case "highlight_object":
                        await HighlightObject(action.params);
                        break;
                    case "show_label":
                        await ShowLabel(action.params);
                        break;
                    case "move_to_point":
                        await MoveToPoint(action.params);
                        break;
                    case "open_menu":
                        OpenMenu(action.params);
                        break;
                    case "change_material":
                        await ChangeMaterial(action.params);
                        break;
                    case "pause_tour":
                        PauseTour();
                        break;
                    case "resume_tour":
                        ResumeTour();
                        break;
                    case "play_audio_hint":
                        await PlayAudioHint(action.params);
                        break;
                    case "answer_question":
                        // Already handled by text response
                        break;
                }
            }
        }
        
        private async UniTask HighlightObject(Dictionary<string, object> @params)
        {
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
                    Destroy(outline);
                }
            }
        }
        
        private async UniTask ShowLabel(Dictionary<string, object> @params)
        {
            if (@params.TryGetValue("object_id", out var objId) && @params.TryGetValue("text", out var text))
            {
                var obj = GameObject.Find(objId.ToString());
                if (obj != null)
                {
                    var label = obj.GetComponentInChildren<TMPro.TextMeshProUGUI>();
                    if (label == null)
                    {
                        var labelGO = new GameObject("Label");
                        labelGO.transform.SetParent(obj.transform);
                        label = labelGO.AddComponent<TMPro.TextMeshProUGUI>();
                    }
                    
                    label.text = text.ToString();
                    label.fontSize = 24;
                    label.color = Color.white;
                    label.alignment = TMPro.TextAlignmentOptions.Center;
                    
                    // Position above object
                    labelGO.transform.localPosition = new Vector3(0, obj.GetComponent<Renderer>().bounds.size.y + 1, 0);
                    labelGO.transform.LookAt(Camera.main.transform);
                    labelGO.transform.Rotate(0, 180, 0);
                }
            }
        }
        
        private async UniTask MoveToPoint(Dictionary<string, object> @params)
        {
            if (@params.TryGetValue("point_id", out var pointId))
            {
                _stereoRig.TeleportToNavigationPoint(pointId.ToString());
            }
        }
        
        private void OpenMenu(Dictionary<string, object> @params)
        {
            // Trigger menu UI
            _eventBridge.SendEvent(_currentSessionId, "copilot_open_menu", new { });
        }
        
        private async UniTask ChangeMaterial(Dictionary<string, object> @params)
        {
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
        }
        
        private void PauseTour()
        {
            // Pause navigation
            _eventBridge.SendEvent(_currentSessionId, "copilot_pause_tour", new { });
        }
        
        private void ResumeTour()
        {
            // Resume navigation
            _eventBridge.SendEvent(_currentSessionId, "copilot_resume_tour", new { });
        }
        
        private async UniTask PlayAudioHint(Dictionary<string, object> @params)
        {
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
        public Dictionary<string, object> params = new Dictionary<string, object>();
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