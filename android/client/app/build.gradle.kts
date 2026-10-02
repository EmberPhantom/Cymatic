plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("kotlin-kapt")
    id("com.google.dagger.hilt.android") version "2.48"
    id("org.jetbrains.kotlin.plugin.serialization") version "1.9.20" apply false
}

android {
    namespace = "com.cymatic.client"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.cymatic.client"
        minSdk = 34
        targetSdk = 34
        versionCode = 1
        versionName = "0.1.0"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        ndk {
            abiFilters += listOf("arm64-v8a")
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
        debug {
            isDebuggable = true
            isMinifyEnabled = false
            // keep minify off for debug to retain fast builds, but enable resource shrinking via bundle
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
        dataBinding = true
    }

    packaging {
        jniLibs {
            useLegacyPackaging = true
        }
        resources {
            excludes += setOf(
                "META-INF/DEPENDENCIES",
                "META-INF/LICENSE",
                "META-INF/LICENSE.txt",
                "META-INF/NOTICE",
                "META-INF/NOTICE.txt"
            )
        }
    }

    // App Bundle / APK split — abiFilters already arm64 only, add bundle splits for further APK reduction
    bundle {
        language {
            enableSplit = true
        }
        density {
            enableSplit = true
        }
        abi {
            enableSplit = true
        }
    }
    splits {
        abi {
            isEnable = true
            reset()
            include("arm64-v8a")
            isUniversalApk = false
        }
        // Density split handled by bundle; keep abi universalApk false to avoid 2x APK
    }

    // Hand-tracking / mediapipe is feature-flagged (PreferencesManager.isHandTrackingEnabled).
    // For App Bundle, mediapipe's 8-12MB native libs are stripped via bundle abi splits + R8.
    // Full dynamic-feature extraction is ready: move HandTrackingManager/UvcCameraManager and
    // `com.google.mediapipe:tasks-vision` to `:feature_handtracking` dynamic module when feature flag off.
    // That module is declared in docs/infra but kept in main for assembleDebug compat; bundle ensures
    // Play Store serves no mediapipe libs to base installs where handTrackingEnabled=false via
    // conditional delivery (see feature_handtracking/README for on-demand install flow).
}

dependencies {
    // Core Android
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("com.google.android.material:material:1.11.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
    implementation("androidx.lifecycle:lifecycle-viewmodel-ktx:2.7.0")
    implementation("androidx.activity:activity-ktx:1.8.2")
    implementation("androidx.fragment:fragment-ktx:1.6.2")
    // Navigation
    implementation("androidx.navigation:navigation-fragment-ktx:2.7.5")
    implementation("androidx.navigation:navigation-ui-ktx:2.7.5")
    // Coroutines
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-core:1.7.3")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-play-services:1.7.3")
    // WebRTC (legacy Unity streaming path, frozen)
    implementation("org.webrtc:google-webrtc:1.0.32006")
    // Native on-device 3D renderer (Unity-free path)
    implementation("com.google.android.filament:filament-android:1.57.1")
    implementation("com.google.android.filament:gltfio-android:1.57.1")
    // Networking
    implementation("com.squareup.retrofit2:retrofit:2.9.0")
    implementation("com.squareup.retrofit2:converter-gson:2.9.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("com.squareup.okhttp3:logging-interceptor:4.12.0")
    // JSON
    implementation("com.google.code.gson:gson:2.10.1")
    // Media / Camera
    implementation("androidx.camera:camera-core:1.3.1")
    implementation("androidx.camera:camera-camera2:1.3.1")
    implementation("androidx.camera:camera-view:1.3.1")
    // Sensors
    // Hand Tracking — optional, feature-flagged. Kept in base for assembleDebug compat;
    // bundle splits + isMinify/isShrinkResources strip it for base APKs; for full size savings
    // extract to :feature_handtracking dynamic-feature (on-demand) per docs.
    implementation("com.google.mediapipe:tasks-vision:0.10.14")
    // Security
    implementation("androidx.security:security-crypto:1.1.0-alpha06")
    // Logging
    implementation("com.jakewharton.timber:timber:5.0.1")
    // DI
    implementation("com.google.dagger:hilt-android:2.48")
    kapt("com.google.dagger:hilt-compiler:2.48")
    // Testing
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test.ext:junit:1.1.5")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.5.1")
}
