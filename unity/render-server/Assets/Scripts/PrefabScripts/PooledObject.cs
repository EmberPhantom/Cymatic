using UnityEngine;

namespace Cymatic.Pooling
{
    /// <summary>
    /// Interface for pooled objects to handle spawn/return events.
    /// </summary>
    public interface IPooledObject
    {
        void OnSpawn();
        void OnReturnToPool();
    }
}
