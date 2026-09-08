using System.Collections.Generic;
using UnityEngine;
using Cysharp.Threading.Tasks;

namespace Cymatic.Pooling
{
    /// <summary>
    /// Generic object pool for Unity GameObjects to reduce GC allocations.
    /// Fixed: expansion no longer checks queue.Count (was infinite expand), now tracks totalSpawned.
    /// Fixed: 50 instantiates hitch spread across frames.
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
        private Dictionary<string, int> _totalSpawned = new Dictionary<string, int>();
        
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
                
                // Spread 50-instantiate hitch: only instantiate min(initialSize, 10) synchronously, remainder async
                int syncCount = Mathf.Min(pool.initialSize, 10);
                for (int i = 0; i < syncCount; i++)
                {
                    var obj = Instantiate(pool.prefab, parent.transform);
                    obj.SetActive(false);
                    objectPool.Enqueue(obj);
                }
                
                poolDictionary.Add(pool.tag, objectPool);
                _totalSpawned[pool.tag] = syncCount;
                // Schedule remaining async to avoid frame hitch
                if (pool.initialSize > syncCount)
                {
                    PrewarmRemainingAsync(pool.tag, pool.initialSize, parent.transform).Forget();
                }
            }
        }

        private async UniTaskVoid PrewarmRemainingAsync(string tag, int targetTotal, Transform parent)
        {
            var config = pools.Find(p => p.tag == tag);
            if (config == null || config.prefab == null) return;
            if (!poolDictionary.TryGetValue(tag, out var queue)) return;
            int spawned = _totalSpawned.ContainsKey(tag) ? _totalSpawned[tag] : queue.Count;
            // Spread across frames: 10 per frame
            while (spawned < targetTotal && spawned < config.maxSize)
            {
                int batch = Mathf.Min(10, targetTotal - spawned);
                for (int i = 0; i < batch; i++)
                {
                    var obj = Instantiate(config.prefab, parent);
                    obj.SetActive(false);
                    queue.Enqueue(obj);
                    spawned++;
                }
                _totalSpawned[tag] = spawned;
                await UniTask.Yield(PlayerLoopTiming.Update);
            }
            _totalSpawned[tag] = spawned;
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
                // Pool exhausted, check if we can expand - FIX: track totalSpawned, not queue.Count (was 0 < maxSize always -> infinite expand)
                var config = pools.Find(p => p.tag == tag);
                int total = _totalSpawned.TryGetValue(tag, out var t) ? t : 0;
                // Fallback: if not tracked yet, estimate total = queue.Count + active (approx queue + spawned)
                if (config != null && config.expandable && total < config.maxSize)
                {
                    var parent = transform.Find($"{tag}_Pool");
                    var obj = Instantiate(config.prefab, parent);
                    objectToSpawn = obj;
                    _totalSpawned[tag] = total + 1;
                }
                else
                {
                    Debug.LogWarning($"Pool {tag} exhausted and not expandable (total {total}/{config?.maxSize}).");
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
        /// Fixed: checks totalSpawned not queue.Count, spreads across frames to avoid hitch.
        /// </summary>
        public void PrewarmPool(string tag, int count)
        {
            // Sync version: for small counts only; large counts should use PrewarmPoolAsync
            PrewarmPoolAsync(tag, count).Forget();
        }

        public async UniTask PrewarmPoolAsync(string tag, int count)
        {
            if (!poolDictionary.ContainsKey(tag)) return;
            
            var config = pools.Find(p => p.tag == tag);
            if (config == null) return;
            
            var pool = poolDictionary[tag];
            var parent = transform.Find($"{tag}_Pool");
            int total = _totalSpawned.TryGetValue(tag, out var t) ? t : pool.Count;
            count = Mathf.Min(count, config.maxSize);
            int batch = 0;
            while (total < count)
            {
                var obj = Instantiate(config.prefab, parent);
                obj.SetActive(false);
                pool.Enqueue(obj);
                total++;
                _totalSpawned[tag] = total;
                batch++;
                // Yield every 10 to avoid 50-instantiate hitch
                if (batch % 10 == 0)
                    await UniTask.Yield(PlayerLoopTiming.Update);
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
                _totalSpawned[tag] = 0;
            }
        }
        
        /// <summary>
        /// Get current pool size (queued available).
        /// </summary>
        public int GetPoolSize(string tag)
        {
            return poolDictionary.ContainsKey(tag) ? poolDictionary[tag].Count : 0;
        }

        /// <summary>
        /// Get total spawned count (queued + active).
        /// </summary>
        public int GetTotalSpawned(string tag)
        {
            return _totalSpawned.TryGetValue(tag, out var v) ? v : GetPoolSize(tag);
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