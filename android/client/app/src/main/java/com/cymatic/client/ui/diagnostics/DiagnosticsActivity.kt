package com.cymatic.client.ui.diagnostics

import android.content.Context
import android.content.IntentFilter
import android.hardware.Sensor
import android.hardware.SensorManager
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import android.os.BatteryManager
import android.os.Build
import android.os.Bundle
import android.os.StatFs
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import com.cymatic.client.databinding.ActivityDiagnosticsBinding
import com.cymatic.client.network.ApiClient
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

/**
 * Read-only device/connectivity diagnostics screen, reachable from
 * MainActivity's "Diagnostics" button. Everything here reads local
 * system state or does a lightweight authenticated backend call - no
 * writes, no side effects.
 */
@AndroidEntryPoint
class DiagnosticsActivity : AppCompatActivity() {

    private var _binding: ActivityDiagnosticsBinding? = null
    private val binding get() = _binding!!

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        _binding = ActivityDiagnosticsBinding.inflate(layoutInflater)
        setContentView(binding.root)

        binding.toolbar.setNavigationOnClickListener { finish() }
        binding.btnRefresh.setOnClickListener { refresh() }
        binding.btnTestStream.setOnClickListener { testStreamConnection() }

        refresh()
    }

    private fun refresh() {
        binding.tvDeviceInfo.text = deviceInfo()
        binding.tvSensors.text = sensorInfo()
        binding.tvNetwork.text = networkInfo()
        binding.tvPerformance.text = performanceInfo()
        binding.tvStorage.text = storageInfo()
        binding.tvBattery.text = batteryInfo()
    }

    private fun deviceInfo(): String = listOf(
        "Manufacturer: ${Build.MANUFACTURER}",
        "Model: ${Build.MODEL}",
        "Android: ${Build.VERSION.RELEASE} (SDK ${Build.VERSION.SDK_INT})",
        "App: ${packageName} ${packageManager.getPackageInfo(packageName, 0).versionName}",
    ).joinToString("\n")

    private fun sensorInfo(): String {
        val sm = getSystemService(Context.SENSOR_SERVICE) as SensorManager
        fun has(type: Int) = sm.getDefaultSensor(type) != null
        return listOf(
            "Accelerometer: ${if (has(Sensor.TYPE_ACCELEROMETER)) "present" else "missing"}",
            "Gyroscope: ${if (has(Sensor.TYPE_GYROSCOPE)) "present" else "missing"}",
            "Magnetometer: ${if (has(Sensor.TYPE_MAGNETIC_FIELD)) "present" else "missing"}",
            "Rotation vector: ${if (has(Sensor.TYPE_ROTATION_VECTOR)) "present" else "missing"}",
        ).joinToString("\n")
    }

    private fun networkInfo(): String {
        val cm = getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = cm.activeNetwork
        val caps = network?.let { cm.getNetworkCapabilities(it) }
        val transport = when {
            caps == null -> "none"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_WIFI) -> "Wi-Fi"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_CELLULAR) -> "Cellular"
            caps.hasTransport(NetworkCapabilities.TRANSPORT_ETHERNET) -> "Ethernet"
            else -> "other"
        }
        val validated = caps?.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED) == true
        return "Transport: $transport\nInternet validated: $validated"
    }

    private fun performanceInfo(): String {
        val runtime = Runtime.getRuntime()
        val usedMb = (runtime.totalMemory() - runtime.freeMemory()) / (1024 * 1024)
        val maxMb = runtime.maxMemory() / (1024 * 1024)
        return "Heap used: ${usedMb}MB / ${maxMb}MB\nCPU cores: ${runtime.availableProcessors()}"
    }

    private fun storageInfo(): String {
        val stat = StatFs(filesDir.path)
        val availableGb = stat.availableBytes / (1024.0 * 1024.0 * 1024.0)
        val totalGb = stat.totalBytes / (1024.0 * 1024.0 * 1024.0)
        return "Available: %.1fGB / %.1fGB".format(availableGb, totalGb)
    }

    private fun batteryInfo(): String {
        val intent = registerReceiver(null, IntentFilter(android.content.Intent.ACTION_BATTERY_CHANGED))
        val level = intent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = intent?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val pct = if (level >= 0 && scale > 0) (level * 100 / scale) else -1
        val charging = intent?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ==
            BatteryManager.BATTERY_STATUS_CHARGING
        return if (pct >= 0) "Level: $pct%${if (charging) " (charging)" else ""}" else "Unavailable"
    }

    private fun testStreamConnection() {
        binding.btnTestStream.isEnabled = false
        lifecycleScope.launch {
            val message = try {
                val response = ApiClient.apiService.getProjects()
                if (response.isSuccessful) {
                    "Backend reachable and authenticated (HTTP ${response.code()})"
                } else {
                    "Backend reachable but request failed (HTTP ${response.code()})"
                }
            } catch (e: Exception) {
                "Backend unreachable: ${e.message}"
            }
            Toast.makeText(this@DiagnosticsActivity, message, Toast.LENGTH_LONG).show()
            binding.btnTestStream.isEnabled = true
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        _binding = null
    }
}
