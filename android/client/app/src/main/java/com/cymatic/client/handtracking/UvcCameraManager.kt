package com.cymatic.client.handtracking

import android.content.Context
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.media.Image
import android.media.ImageReader
import android.util.Log
import android.util.Size
import androidx.camera.core.CameraSelector
import androidx.camera.core.ImageAnalysis
import androidx.camera.core.ImageProxy
import androidx.camera.core.Preview
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.launch
import kotlinx.coroutines.channels.Channel
import java.nio.ByteBuffer
import java.util.concurrent.Executors

class UvcCameraManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView
) {

    private var cameraProvider: ListenableFuture<ProcessCameraProvider>? = null
    private var cameraExecutor = Executors.newSingleThreadExecutor()
    private var imageReader: ImageReader? = null
    private var isCameraActive = false
    private var currentDevice: UsbDevice? = null

    // Frame callback
    private val frameChannel = Channel<ImageProxy>(10)
    private var onFrameAvailable: ((ImageProxy) -> Unit)? = null

    init {
        cameraProvider = ProcessCameraProvider.getInstance(context)
    }

    fun startCamera(device: UsbDevice) {
        currentDevice = device

        val cameraProviderFuture = ProcessCameraProvider.getInstance(context)
        cameraProviderFuture.addListener({
            try {
                val provider = cameraProviderFuture.get()
                bindCamera(provider)
            } catch (e: Exception) {
                Log.e("UvcCamera", "Camera start failed", e)
            }
        }, ContextCompat.getMainExecutor(context))
    }

    private fun bindCamera(provider: ProcessCameraProvider) {
        // For UVC cameras, we need to use a custom camera selector
        // This is simplified - real implementation would enumerate UVC devices

        val preview = Preview.Builder()
            .setTargetRotation(previewView.display.rotation)
            .build()
            .also { it.setSurfaceProvider(previewView.surfaceProvider) }

        val imageAnalysis = ImageAnalysis.Builder()
            .setTargetResolution(Size(640, 480))
            .setBackpressureStrategy(ImageAnalysis.STRATEGY_KEEP_ONLY_LATEST)
            .build()
            .also {
                it.setAnalyzer(cameraExecutor) { imageProxy ->
                    processFrame(imageProxy)
                }
            }

        // For UVC, we'd need a custom camera selector
        // This is a placeholder - real implementation needs USB camera enumeration

        try {
            // provider.bindToLifecycle(lifecycleOwner, cameraSelector, preview, imageAnalysis)
            isCameraActive = true
        } catch (e: Exception) {
            Log.e("UvcCamera", "Camera bind failed", e)
        }
    }

    private fun processFrame(imageProxy: ImageProxy) {
        // Send frame to hand tracking
        frameChannel.trySend(imageProxy)
        onFrameAvailable?.invoke(imageProxy)

        // Don't close - let the analyzer handle it
    }

    fun setOnFrameAvailable(listener: (ImageProxy) -> Unit) {
        onFrameAvailable = listener
    }

    fun stopCamera() {
        isCameraActive = false
        cameraExecutor.shutdown()
    }

    fun setFrameListener(listener: (ImageProxy) -> Unit) {
        onFrameAvailable = listener
    }

    fun getFrameChannel(): Channel<ImageProxy> = frameChannel

    companion object {
        fun getUvcDevices(context: Context): List<UsbDevice> {
            val usbManager = context.getSystemService(Context.USB_SERVICE) as UsbManager
            val devices = mutableListOf<UsbDevice>()

            for (device in usbManager.deviceList.values) {
                if (isUvcCamera(device)) {
                    devices.add(device)
                }
            }
            return devices
        }

        private fun isUvcCamera(device: UsbDevice): Boolean {
            // Check for UVC video class (0x0E) or common camera interfaces
            if (device.deviceClass == 0x0E) return true // Video class

            for (i in 0 until device.interfaceCount) {
                val usbInterface = device.getInterface(i)
                if (usbInterface.interfaceClass == 0x0E) return true // Video class
                if (usbInterface.interfaceClass == 0x01 && usbInterface.interfaceSubclass == 0x04) return true // Audio/Video
            }

            // Check device name
            val name = device.deviceName.lowercase()
            return name.contains("uvc") || name.contains("camera") || name.contains("webcam")
        }
    }
}
