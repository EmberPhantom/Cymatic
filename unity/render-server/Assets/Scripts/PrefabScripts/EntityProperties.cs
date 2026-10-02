using UnityEngine;
using System.Collections.Generic;

namespace Cymatic.Prefabs
{
    /// <summary>
    /// Component to store entity properties for runtime access.
    /// </summary>
    public class EntityProperties : MonoBehaviour
    {
        public Dictionary<string, object> properties = new Dictionary<string, object>();

        public void SetProperty(string key, object value)
        {
            properties[key] = value;
        }

        public T GetProperty<T>(string key, T defaultValue = default(T))
        {
            if (properties.TryGetValue(key, out var value))
            {
                if (value is T typed)
                    return typed;
                return defaultValue;
            }
            return defaultValue;
        }

        public bool HasProperty(string key)
        {
            return properties.ContainsKey(key);
        }

        public void RemoveProperty(string key)
        {
            properties.Remove(key);
        }

        public void Clear()
        {
            properties.Clear();
        }
    }
}
