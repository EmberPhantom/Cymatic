plugins {
    id(""com.android.dynamic-feature"")
    id(""org.jetbrains.kotlin.android"")
    id(""com.google.dagger.hilt.android"") version ""2.48""
    id(""kotlin-kapt"")
}
android {
    namespace = ""com.cymatic.client.feature.handtracking""
    compileSdk = 34
    defaultConfig { minSdk = 34 }
    buildTypes {
        release { isMinifyEnabled = true; proguardFiles(getDefaultProguardFile(""proguard-android-optimize.txt""), ""proguard-rules.pro"") }
    }
}
dependencies {
    implementation(project("":app""))
    // Mediapipe is moved here for on-demand delivery — base APK saves ~10-12MB when handTrackingEnabled=false
    implementation(""com.google.mediapipe:tasks-vision:0.10.14"")
    implementation(""androidx.core:core-ktx:1.12.0"")
}
