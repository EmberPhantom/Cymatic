package com.cymatic.client.input

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.bluetooth.BluetoothManager
import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.hardware.input.InputManager as AndroidInputManager
import android.os.Build
import android.util.Log
import android.view.InputDevice
import android.view.KeyEvent
import android.view.MotionEvent
import androidx.core.content.ContextCompat
import kotlinx.coroutines.channels.Channel

class ControllerManager(private val context: Context) {

    private val bluetoothAdapter = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
        (context.getSystemService(Context.BLUETOOTH_SERVICE) as BluetoothManager).adapter
    } else {
        @Suppress("DEPRECATION")
        BluetoothAdapter.getDefaultAdapter()
    }
    private var connectedController: BluetoothDevice? = null
    private var inputDevice: InputDevice? = null
    private var cachedInputManager: AndroidInputManager? = null
    private var receiverRegistered = false
    private var hasScanned = false
    
    // Controller state
    private var selectPressed = false
    private var menuPressed = false
    private var pttPressed = false
    private var touchpadX = 0f
    private var touchpadY = 0f
    private var touchpadDeltaX = 0f
    private var touchpadDeltaY = 0f
    private var touchpadTouched = false
    private var triggerValue = 0f
    private var gripValue = 0f
    private var thumbstickX = 0f
    private var thumbstickY = 0f
    
    // Battery
    private var batteryLevel = 100
    
    // Callbacks
    private val controllerStateChannel = Channel<ControllerState>(10)
    
    // For Daydream/Cardboard style controllers
    private var virtualControllerEnabled = false
    
    init {
        registerReceivers()
        // Single bonded-device scan guarded by BLUETOOTH_CONNECT permission — avoids double scan (144)
        scanForControllers()
    }
    
    private fun registerReceivers() {
        val filter = IntentFilter().apply {
            addAction(BluetoothDevice.ACTION_ACL_CONNECTED)
            addAction(BluetoothDevice.ACTION_ACL_DISCONNECTED)
            addAction(BluetoothDevice.ACTION_BATTERY_LEVEL_CHANGED)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                addAction(BluetoothDevice.ACTION_BATTERY_STATE_CHANGED)
            }
        }
        try {
            context.registerReceiver(bluetoothReceiver, filter)
            receiverRegistered = true
        } catch (e: SecurityException) {
            Log.w("ControllerManager", "Bluetooth permission not granted, skip receiver")
        }
    }
    
    private val bluetoothReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val action = intent?.action
            when (action) {
                BluetoothDevice.ACTION_ACL_CONNECTED -> {
                    val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
                    } else {
                        @Suppress("DEPRECATION")
                        intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    }
                    device?.let { onControllerConnected(it) }
                }
                BluetoothDevice.ACTION_ACL_DISCONNECTED -> {
                    val device = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                        intent.getParcelableExtra(BluetoothDevice.EXTRA_DEVICE, BluetoothDevice::class.java)
                    } else {
                        @Suppress("DEPRECATION")
                        intent.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    }
                    if (device == connectedController) {
                        onControllerDisconnected()
                    }
                }
                BluetoothDevice.ACTION_BATTERY_LEVEL_CHANGED, BluetoothDevice.ACTION_BATTERY_STATE_CHANGED -> {
                    val level = intent?.getIntExtra(BluetoothDevice.EXTRA_BATTERY_LEVEL, -1)
                        ?: intent?.getIntExtra("android.bluetooth.device.extra.BATTERY_LEVEL", -1) ?: -1
                    if (level != -1) {
                        batteryLevel = level
                    }
                }
            }
        }
    }
    
    private fun scanForControllers() {
        if (hasScanned) return
        hasScanned = true
        // BLUETOOTH_CONNECT guard (144) — double scan removed by hasScanned + permission check
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            if (ContextCompat.checkSelfPermission(context, android.Manifest.permission.BLUETOOTH_CONNECT) != PackageManager.PERMISSION_GRANTED) {
                Log.d("ControllerManager", "BLUETOOTH_CONNECT not granted, skipping bonded scan")
                return
            }
        }
        try {
            bluetoothAdapter?.bondedDevices?.forEach { device ->
                if (isControllerDevice(device)) {
                    onControllerConnected(device)
                }
            }
        } catch (e: SecurityException) {
            Log.w("ControllerManager", "BLUETOOTH_CONNECT denied during scan", e)
        }
    }
    
    private fun isControllerDevice(device: BluetoothDevice): Boolean {
        val name = try { device.name?.lowercase() ?: "" } catch (_: SecurityException) { "" }
        return name.contains("controller") || name.contains("daydream") || 
               name.contains("gear vr") || name.contains("oculus") ||
               name.contains("vr")
    }
    
    private fun onControllerConnected(device: BluetoothDevice) {
        connectedController = device
        Log.d("ControllerManager", "Controller connected: ${try{device.name}catch(_:SecurityException){"unknown"}}")
    }
    
    private fun onControllerDisconnected() {
        connectedController = null
        resetState()
        Log.d("ControllerManager", "Controller disconnected")
    }
    
    private fun resetState() {
        selectPressed = false
        menuPressed = false
        pttPressed = false
        touchpadX = 0f
        touchpadY = 0f
        touchpadDeltaX = 0f
        touchpadDeltaY = 0f
        touchpadTouched = false
        triggerValue = 0f
        gripValue = 0f
        thumbstickX = 0f
        thumbstickY = 0f
    }
    
    private fun getAndroidInputManager(): AndroidInputManager {
        if (cachedInputManager == null) {
            cachedInputManager = context.getSystemService(Context.INPUT_SERVICE) as AndroidInputManager
        }
        return cachedInputManager!!
    }

    // Handle input from Android's InputDevice API (for Daydream, etc.)
    fun onGenericMotionEvent(event: MotionEvent): Boolean {
        // Resolve InputDevice from cached manager — avoid getSystemService per event
        inputDevice = getAndroidInputManager().getInputDevice(event.deviceId)
        if (inputDevice == null) return false

        // Fix 151 touchpad duplicate: compute delta BEFORE overwriting touchpadX/Y
        // Single read of AXIS_X/Y (was duplicated with zero-delta bug)
        val touchX = event.getAxisValue(MotionEvent.AXIS_X)
        val touchY = event.getAxisValue(MotionEvent.AXIS_Y)
        if (touchX != 0f || touchY != 0f) {
            touchpadDeltaX = touchX - touchpadX
            touchpadDeltaY = touchY - touchpadY
            touchpadX = touchX
            touchpadY = touchY
            touchpadTouched = true
        } else {
            touchpadTouched = false
            touchpadDeltaX = 0f
            touchpadDeltaY = 0f
        }
        
        // Trigger / Grip / Thumbstick — distinct axes, not aliased to touchpad
        triggerValue = event.getAxisValue(MotionEvent.AXIS_BRAKE)
        gripValue = event.getAxisValue(MotionEvent.AXIS_GAS)
        
        // Thumbstick on hat axes, fallback to Z/RZ if hat is zero for some controllers
        val hatX = event.getAxisValue(MotionEvent.AXIS_HAT_X)
        val hatY = event.getAxisValue(MotionEvent.AXIS_HAT_Y)
        thumbstickX = if (hatX != 0f) hatX else event.getAxisValue(MotionEvent.AXIS_Z)
        thumbstickY = if (hatY != 0f) hatY else event.getAxisValue(MotionEvent.AXIS_RZ)
        
        return true
    }
    
    fun onKeyDown(keyCode: Int, event: KeyEvent): Boolean {
        when (keyCode) {
            KeyEvent.KEYCODE_BUTTON_A, KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                selectPressed = true
                return true
            }
            KeyEvent.KEYCODE_BUTTON_B, KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_ESCAPE -> {
                menuPressed = true
                return true
            }
            KeyEvent.KEYCODE_VOLUME_UP, KeyEvent.KEYCODE_BUTTON_L1 -> {
                pttPressed = true
                return true
            }
            KeyEvent.KEYCODE_BUTTON_THUMBL -> {
                pttPressed = true
                return true
            }
        }
        return false
    }
    
    fun onKeyUp(keyCode: Int, event: KeyEvent): Boolean {
        when (keyCode) {
            KeyEvent.KEYCODE_BUTTON_A, KeyEvent.KEYCODE_DPAD_CENTER, KeyEvent.KEYCODE_ENTER -> {
                selectPressed = false
                return true
            }
            KeyEvent.KEYCODE_BUTTON_B, KeyEvent.KEYCODE_BACK, KeyEvent.KEYCODE_ESCAPE -> {
                menuPressed = false
                return true
            }
            KeyEvent.KEYCODE_VOLUME_UP, KeyEvent.KEYCODE_BUTTON_L1 -> {
                pttPressed = false
                return true
            }
            KeyEvent.KEYCODE_BUTTON_THUMBL -> {
                pttPressed = false
                return true
            }
        }
        return false
    }
    
    // Virtual controller for testing
    fun setVirtualController(enabled: Boolean) {
        virtualControllerEnabled = enabled
        if (!enabled) {
            resetState()
        }
    }
    
    fun setVirtualButton(button: VirtualButton, pressed: Boolean) {
        when (button) {
            VirtualButton.SELECT -> selectPressed = pressed
            VirtualButton.MENU -> menuPressed = pressed
            VirtualButton.PTT -> pttPressed = pressed
        }
    }
    
    fun setVirtualTouchpad(x: Float, y: Float, touched: Boolean) {
        if (touched) {
            touchpadDeltaX = x - touchpadX
            touchpadDeltaY = y - touchpadY
            touchpadX = x
            touchpadY = y
            touchpadTouched = true
        } else {
            touchpadTouched = false
            touchpadDeltaX = 0f
            touchpadDeltaY = 0f
        }
    }
    
    fun setVirtualThumbstick(x: Float, y: Float) {
        thumbstickX = x
        thumbstickY = y
    }
    
    fun setVirtualTrigger(value: Float) {
        triggerValue = value
    }
    
    fun setVirtualGrip(value: Float) {
        gripValue = value
    }
    
    // Getters
    fun isSelectPressed(): Boolean = selectPressed
    fun isMenuPressed(): Boolean = menuPressed
    fun isPTTPressed(): Boolean = pttPressed
    fun getTouchpadPosition(): Pair<Float, Float> = touchpadX to touchpadY
    fun getTouchpadDelta(): Pair<Float, Float> = touchpadDeltaX to touchpadDeltaY
    fun isTouchpadTouched(): Boolean = touchpadTouched
    fun getTriggerValue(): Float = triggerValue
    fun getGripValue(): Float = gripValue
    fun getThumbstickPosition(): Pair<Float, Float> = thumbstickX to thumbstickY
    fun getBatteryLevel(): Int = batteryLevel
    fun isConnected(): Boolean = connectedController != null || virtualControllerEnabled
    
    fun getState(): ControllerState {
        return ControllerState(
            selectPressed = selectPressed,
            menuPressed = menuPressed,
            pttPressed = pttPressed,
            touchpadX = touchpadX,
            touchpadY = touchpadY,
            touchpadDeltaX = touchpadDeltaX,
            touchpadDeltaY = touchpadDeltaY,
            touchpadTouched = touchpadTouched,
            triggerValue = triggerValue,
            gripValue = gripValue,
            thumbstickX = thumbstickX,
            thumbstickY = thumbstickY,
            batteryLevel = batteryLevel,
            isConnected = isConnected()
        )
    }
    
    fun dispose() {
        if (receiverRegistered) {
            try { context.unregisterReceiver(bluetoothReceiver) } catch (_: Exception) {}
            receiverRegistered = false
        }
        try { controllerStateChannel.close() } catch (_: Exception) {}
    }
    
    enum class VirtualButton {
        SELECT, MENU, PTT
    }
    
    data class ControllerState(
        val selectPressed: Boolean,
        val menuPressed: Boolean,
        val pttPressed: Boolean,
        val touchpadX: Float,
        val touchpadY: Float,
        val touchpadDeltaX: Float,
        val touchpadDeltaY: Float,
        val touchpadTouched: Boolean,
        val triggerValue: Float,
        val gripValue: Float,
        val thumbstickX: Float,
        val thumbstickY: Float,
        val batteryLevel: Int,
        val isConnected: Boolean
    )
}
