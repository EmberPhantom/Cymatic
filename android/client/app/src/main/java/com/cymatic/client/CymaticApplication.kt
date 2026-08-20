package com.cymatic.client

import android.app.Application
import dagger.hilt.android.HiltAndroidApp
import timber.log.Timber

@HiltAndroidApp
class CymaticApplication : Application() {

    override fun onCreate() {
        super.onCreate()
        
        // Initialize Timber for logging
        if (BuildConfig.DEBUG) {
            Timber.plant(Timber.DebugTree())
        } else {
            Timber.plant(CrashReportingTree())
        }
    }
    
    private class CrashReportingTree : Timber.Tree() {
        override fun log(priority: Int, tag: String?, message: String, t: Throwable?) {
            // In production, send to crash reporting service
            if (priority == Log.ERROR) {
                // Send to backend or crash reporting
            }
        }
    }
}