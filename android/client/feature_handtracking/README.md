# feature_handtracking — dynamic feature (on-demand)

Mediapipe hand-tracking is optional per AGENTS.md. Base APK excludes it via bundle abi splits + R8.
Full extraction to dynamic-feature saves ~10-12MB + native libs.

To enable on-demand install:
1. Add to settings.gradle.kts: include("":feature_handtracking"")
2. Add to app/build.gradle.kts inside android { dynamicFeatures += setOf("":feature_handtracking"") }
3. Move HandTrackingManager + UvcCameraManager + tasks-vision dependency to this module
4. Gate via PreferencesManager.isHandTrackingEnabled + Play Feature Delivery SplitInstallManager

MVP keeps dependency in base for assembleDebug compat; bundle + shrinkResources already strip when flag off.
