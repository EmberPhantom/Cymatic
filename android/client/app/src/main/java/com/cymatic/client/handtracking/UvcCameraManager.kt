package com.cymatic.client.handtracking

import android.content.Context
import android.hardware.usb.UsbDevice
import android.hardware.usb.UsbManager
import android.media.ImageReader
import android.util.Log
import androidx.camera.core.ImageProxy
import androidx.camera.lifecycle.ProcessCameraProvider
import androidx.camera.view.PreviewView
import androidx.core.content.ContextCompat
import androidx.lifecycle.LifecycleOwner
import com.google.common.util.concurrent.ListenableFuture
import kotlinx.coroutines.channels.Channel
import java.util.concurrent.Executors

class UvcCameraManager(
    private val context: Context,
    private val lifecycleOwner: LifecycleOwner,
    private val previewView: PreviewView
) {

    private var cameraProvider: ListenableFuture<ProcessCameraProvider>? = null
    private var boundProvider: ProcessCameraProvider? = null
    private var cameraExecutor = Executors.newSingleThreadExecutor()
    private var imageReader: ImageReader? = null
    private var isCameraActive = false
    private var currentDevice: UsbDevice? = null

    // Frame callback
    private val frameChannel = Channel<ImageProxy>(10)
    private var droppedFrames = 0
    private var onFrameAvailable: ((ImageProxy) -> Unit)? = null

    init {
        cameraProvider = ProcessCameraProvider.getInstance(context)
    }

    fun startCamera(device: UsbDevice) {
        if (isCameraActive) {
            Log.d("UvcCamera", "already active, ignoring start")
            return
        }
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
        // UVC devices are not exposed through CameraX's selector: real
        // enumeration needs UsbManager permission + a UVC driver (e.g. UVCCamera)
        // feeding frames into imageReader. Until that driver lands, there is no
        // CameraX use case to bind — the old code left a commented-out
        // bindToLifecycle here while reporting active. Keep this honest: record
        // the provider for stopCamera's unbindAll and only mark active when a
        // real source is attached (set by the future UVC driver via onSourceReady).
        boundProvider = provider
        Log.w("UvcCamera", "UVC driver not implemented: camera not started (optional feature)")
    }

    /**
     * Called by the future UVC driver once it can produce frames. Separated
     * from bindCamera so nothing reports "active" without a live source.
     */
    fun onSourceReady() {
        isCameraActive = true
    }

    private fun processFrame(imageProxy: ImageProxy) {
        // The analyzer contract requires EVERY ImageProxy to be closed, or the
        // pipeline stalls after filling (the old code never closed -> leak).
        // Single-owner rule: the synchronous listener only BORROWS the frame
        // (copy what you need inside the callback); otherwise ownership moves
        // to the channel receiver, which MUST close (see getFrameChannel).
        var owned = true
        try {
            val listener = onFrameAvailable
            if (listener != null) {
                try {
                    listener(imageProxy)
                } catch (e: Exception) {
                    Log.w("UvcCamera", "frame listener failed", e)
                }
            } else {
                if (frameChannel.trySend(imageProxy).isSuccess) {
                    owned = false // receiver now owns the close
                } else {
                    frameChannel.tryReceive().getOrNull()?.close()
                    droppedFrames++
                    if (frameChannel.trySend(imageProxy).isSuccess) {
                        owned = false
                    } else {
                        Log.w("UvcCamera", "frame dropped, channel saturated (total=$droppedFrames)")
                    }
                }
            }
        } finally {
            if (owned) {
                try { imageProxy.close() } catch (e: Exception) { }
            }
        }
    }

    fun setOnFrameAvailable(listener: (ImageProxy) -> Unit) {
        onFrameAvailable = listener
    }

    fun stopCamera() {
        if (!isCameraActive && boundProvider == null) return
        isCameraActive = false
        currentDevice = null
        try { boundProvider?.unbindAll() } catch (e: Exception) { }
        boundProvider = null
        // Drain undelivered frames (each owned proxy must still be closed).
        var drained = 0
        while (true) {
            val proxy = frameChannel.tryReceive().getOrNull() ?: break
            try { proxy.close() } catch (e: Exception) { }
            drained++
        }
        if (drained > 0) Log.d("UvcCamera", "drained $drained queued frames on stop")
        try { imageReader?.close() } catch (e: Exception) { }
        imageReader = null
        try { cameraExecutor.shutdownNow() } catch (e: Exception) { }
        cameraExecutor = Executors.newSingleThreadExecutor()
    }

    fun setFrameListener(listener: (ImageProxy) -> Unit) {
        onFrameAvailable = listener
    }

    /** Channel receivers own each frame and MUST call [ImageProxy.close]. */
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
