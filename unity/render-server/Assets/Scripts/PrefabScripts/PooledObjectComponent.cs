using UnityEngine;

namespace Cymatic.Prefabs
{
    /// <summary>
    /// Component that identifies a room and provides room-specific functionality.
    /// </summary>
    public class RoomComponent : MonoBehaviour
    {
        [Header("Room Properties")]
        [SerializeField] private string roomName;
        [SerializeField] private RoomType roomType = RoomType.Generic;
        [SerializeField] private bool isFurnished = true;
        [SerializeField] private string style = "modern";
        [SerializeField] private bool hasWindows = true;
        [SerializeField] private bool hasDoors = true;

        [Header("Dimensions")]
        [SerializeField] private Vector3 roomSize = new Vector3(10f, 3f, 10f);
        [SerializeField] private float ceilingHeight = 3f;

        [Header("Connections")]
        [SerializeField] private Transform[] doorPositions;
        [SerializeField] private Transform[] windowPositions;

        public string RoomName => roomName;
        public RoomType RoomType => roomType;
        public bool IsFurnished => isFurnished;
        public string Style => style;
        public Vector3 RoomSize => roomSize;
        public float CeilingHeight => ceilingHeight;
        public Transform[] DoorPositions => doorPositions;
        public Transform[] WindowPositions => windowPositions;

        public Bounds GetRoomBounds()
        {
            var collider = GetComponent<BoxCollider>();
            if (collider != null)
                return collider.bounds;

            return new Bounds(transform.position, new Vector3(roomSize.x, ceilingHeight, roomSize.z));
        }

        public bool IsPointInside(Vector3 worldPoint)
        {
            var bounds = GetRoomBounds();
            return bounds.Contains(worldPoint);
        }

        public Transform GetNearestDoor(Vector3 fromPosition)
        {
            if (doorPositions == null || doorPositions.Length == 0)
                return transform;

            Transform nearest = null;
            float minDist = float.MaxValue;

            foreach (var door in doorPositions)
            {
                if (door == null) continue;
                float dist = Vector3.Distance(fromPosition, door.position);
                if (dist < minDist)
                {
                    minDist = dist;
                    nearest = door;
                }
            }
            return nearest;
        }

        private void OnDrawGizmosSelected()
        {
            Gizmos.color = Color.cyan;
            Gizmos.DrawWireCube(transform.position + Vector3.up * (ceilingHeight / 2f), new Vector3(roomSize.x, ceilingHeight, roomSize.z));

            Gizmos.color = Color.green;
            if (doorPositions != null)
            {
                foreach (var door in doorPositions)
                {
                    if (door != null)
                        Gizmos.DrawWireSphere(door.position, 0.5f);
                }
            }
        }
    }

    public enum RoomType
    {
        Generic,
        LivingRoom,
        Kitchen,
        Bedroom,
        Bathroom,
        DiningRoom,
        Office,
        Hallway,
        Balcony,
        Outdoor
    }
}
