using System.Collections.Generic;
using UnityEngine;

namespace Cymatic.Pooling
{
    /// <summary>
    /// Generic object pool for Unity GameObjects to reduce GC allocations.
    /// </summary>
    public class ObjectPool : MonoBehaviour
    {
        [System.Serializable]
        public class PoolConfig
        {
            public string tag;
            public GameObject prefab;
            public int initialSize = 10;
            public int maxSize = 50;
            public bool expandable = true;
        }
        
        public List<PoolConfig> pools = new List<PoolConfig>();
        public Dictionary<string, Queue<GameObject>> poolDictionary = new Dictionary<string, Queue<GameObject>>();
        
        public static ObjectPool Instance { get; private set; }
        
        void Awake()
        {
            if (Instance == null)
            {
                Instance = this;
                DontDestroyOnLoad(gameObject);
                InitializePools();
            }
            else
            {
                Destroy(gameObject);
            }
        }
        
        void InitializePools()
        {
            foreach (var pool in pools)
            {
                var objectPool = new Queue<GameObject>();
                var parent = new GameObject($"{pool.tag}_Pool");
                parent.transform.SetParent(transform);
                
                for (int i = 0; i < pool.initialSize; i++)
                {
                    var obj = Instantiate(pool.prefab, parent.transform);
                    obj.SetActive(false);
                    objectPool.Enqueue(obj);
                }
                
                poolDictionary.Add(pool.tag, objectPool);
            }
        }
        
        /// <summary>
        /// Get an object from the pool.
        /// </summary>
        public GameObject SpawnFromPool(string tag, Vector3 position, Quaternion rotation)
        {
            if (!poolDictionary.ContainsKey(tag))
            {
                Debug.LogWarning($"Pool with tag {tag} does not exist.");
                return null;
            }
            
            var objectPool = poolDictionary[tag];
            
            GameObject objectToSpawn;
            if (objectPool.Count > 0)
            {
                objectToSpawn = objectPool.Dequeue();
            }
            else
            {
                // Pool exhausted, check if we can expand
                var config = pools.Find(p => p.tag == tag);
                if (config != null && config.expandable && objectPool.Count < config.maxSize)
                {
                    var parent = transform.Find($"{tag}_Pool");
                    var obj = Instantiate(config.prefab, parent);
                    objectToSpawn = obj;
                }
                else
                {
                    Debug.LogWarning($"Pool {tag} exhausted and not expandable.");
                    return null;
                }
            }
            
            objectToSpawn.SetActive(true);
            objectToSpawn.transform.position = position;
            objectToSpawn.transform.rotation = rotation;
            
            // Reset object state
            var pooledObj = objectToSpawn.GetComponent<IPooledObject>();
            pooledObj?.OnSpawn();
            
            return objectToSpawn;
        }
        
        /// <summary>
        /// Return an object to the pool.
        /// </summary>
        public void ReturnToPool(string tag, GameObject objectToReturn)
        {
            if (!poolDictionary.ContainsKey(tag))
            {
                Debug.LogWarning($"Pool with tag {tag} does not exist.");
                Destroy(objectToReturn);
                return;
            }
            
            objectToReturn.SetActive(false);
            
            var pooledObj = objectToReturn.GetComponent<IPooledObject>();
            pooledObj?.OnReturnToPool();
            
            poolDictionary[tag].Enqueue(objectToReturn);
        }
        
        /// <summary>
        /// Pre-warm a pool to a specific size.
        /// </summary>
        public void PrewarmPool(string tag, int count)
        {
            if (!poolDictionary.ContainsKey(tag)) return;
            
            var config = pools.Find(p => p.tag == tag);
            if (config == null) return;
            
            var pool = poolDictionary[tag];
            var parent = transform.Find($"{tag}_Pool");
            
            while (pool.Count < count && pool.Count < config.maxSize)
            {
                var obj = Instantiate(config.prefab, parent);
                obj.SetActive(false);
                pool.Enqueue(obj);
            }
        }
        
        /// <summary>
        /// Clear a specific pool.
        /// </summary>
        public void ClearPool(string tag)
        {
            if (poolDictionary.ContainsKey(tag))
            {
                foreach (var obj in poolDictionary[tag])
                {
                    Destroy(obj);
                }
                poolDictionary[tag].Clear();
            }
        }
        
        /// <summary>
        /// Get current pool size.
        /// </summary>
        public int GetPoolSize(string tag)
        {
            return poolDictionary.ContainsKey(tag) ? poolDictionary[tag].Count : 0;
        }
    }
    
    /// <summary>
    /// Helper component for automatically returning to pool after time.
    /// </summary>
    public class AutoReturnToPool : MonoBehaviour
    {
        public string poolTag;
        public float lifetime = 5f;
        
        void OnEnable()
        {
            Invoke(nameof(ReturnToPool), lifetime);
        }
        
        void OnDisable()
        {
            CancelInvoke();
        }
        
        void ReturnToPool()
        {
            if (ObjectPool.Instance != null)
            {
                ObjectPool.Instance.ReturnToPool(poolTag, gameObject);
            }
            else
            {
                Destroy(gameObject);
            }
        }
    }
}