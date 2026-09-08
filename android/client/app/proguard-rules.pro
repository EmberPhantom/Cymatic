# Cymatic ProGuard / R8 rules
-keep class com.cymatic.client.** { *; }
-keep class org.webrtc.** { *; }
# Mediapipe / hand-tracking is optional (feature-flagged). When handTrackingEnabled=false, R8 will
# strip com.google.mediapipe.** via -- isMinifyEnabled + isShrinkResources + bundle abi splits.
# Keep only if feature active (auto-keep via -if).
-if class com.cymatic.client.handtracking.HandTrackingManager
-keep class com.google.mediapipe.tasks.vision.** { *; }
-dontwarn com.google.mediapipe.**
# Keep WebRTC
-keep class org.webrtc.** { *; }
# Keep Hilt / Gson models
-keep class com.cymatic.client.network.model.** { *; }
-keepattributes Signature, InnerClasses, EnclosingMethod
-keep class androidx.security.crypto.** { *; }
# Remove logging in release
-assumenosideeffects class android.util.Log {
    public static *** d(...);
    public static *** v(...);
}
