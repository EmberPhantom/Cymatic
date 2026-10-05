package com.cymatic.client.input

/**
 * Pure Bluetooth controller identity + allowlist policy.
 *
 * Two fixes over the old inline checks:
 * 1. Devices are compared by Bluetooth address, not object instance — intents
 *    deliver a fresh BluetoothDevice parcelable each time, so `==` on the
 *    instance is unreliable for disconnect matching.
 * 2. Name matching uses an allowlist of controller product prefixes instead of
 *    a bare "vr" substring (which also matched speakers/TVs advertising "AVR"
 *    etc.). Claimed devices are logged by the caller with name + address.
 *
 * No Android dependencies — JVM unit-tested.
 */
object ControllerIdentity {

    /** Known VR-controller product name prefixes (lowercase). */
    val ALLOWED_PREFIXES = listOf(
        "controller",
        "daydream",
        "gear vr",
        "oculus",
        "quest",
        "vive",
        "pico",
        "cardboard",
        "vr controller",
        "vr-controller",
        "spire",
        "lenovo mirage"
    )

    /** Whether [deviceName] looks like a VR controller. Blank never matches. */
    fun isAllowedControllerName(deviceName: String?): Boolean {
        val name = deviceName?.trim()?.lowercase() ?: return false
        if (name.isEmpty()) return false
        return ALLOWED_PREFIXES.any { prefix ->
            name == prefix || name.startsWith(prefix + " ") ||
                name.startsWith(prefix + "-") || name.startsWith(prefix + "_") ||
                name.contains(" $prefix") || name.endsWith(prefix)
        }
    }

    /**
     * Identity comparison by Bluetooth MAC address (case-insensitive).
     * Null/blank addresses never match.
     */
    fun sameDevice(addressA: String?, addressB: String?): Boolean {
        if (addressA.isNullOrBlank() || addressB.isNullOrBlank()) return false
        return addressA.trim().equals(addressB.trim(), ignoreCase = true)
    }

    /** Log-safe label for a claimed device (name may be blank). */
    fun claimLabel(deviceName: String?, address: String?): String {
        val name = deviceName?.trim()?.takeIf { it.isNotEmpty() } ?: "<unnamed>"
        val addr = address?.trim()?.takeIf { it.isNotEmpty() } ?: "<no-address>"
        return "name=$name address=$addr"
    }
}
