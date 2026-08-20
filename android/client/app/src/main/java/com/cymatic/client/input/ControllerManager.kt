package com.cymatic.client.input

import android.bluetooth.BluetoothAdapter
import android.bluetooth.BluetoothDevice
import android.content.BroadcastReceiver
import android.content.Context
import android.content.ContextCompat
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.PackageManager
import android.hardware.input.InputManager
import android.os.Build
import android.util.Log
import android.view.InputDevice
import android.view.KeyEvent
import android.view.MotionEvent
import kotlinx.coroutines.channels.Channel

class ControllerManager(private val context: Context) {

    private val bluetoothAdapter = BluetoothAdapter.getDefaultAdapter()
    private var connectedController: BluetoothDevice? = null
    private var inputDevice: InputDevice? = null
    
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
        
        context.registerReceiver(bluetoothReceiver, filter, 
            ContextCompat.getSystemService(context, android.content.pm.PermissionManager::class.java)?.getPermission("android.permission.BLUETOOTH_CONNECT") == PackageManager.PERMISSION_GRANTED)
    }
    
    private val bluetoothReceiver = object : BroadcastReceiver() {
        override fun onReceive(context: Context?, intent: Intent?) {
            val action = intent?.action
            when (action) {
                BluetoothDevice.ACTION_ACL_CONNECTED -> {
                    val device = intent?.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    device?.let { onControllerConnected(it) }
                }
                BluetoothDevice.ACTION_ACL_DISCONNECTED -> {
                    val device = intent?.getParcelableExtra<BluetoothDevice>(BluetoothDevice.EXTRA_DEVICE)
                    if (device == connectedController) {
                        onControllerDisconnected()
                    }
                }
                BluetoothDevice.ACTION_BATTERY_LEVEL_CHANGED -> {
                    val level = intent?.getIntExtra(BluetoothDevice.EXTRA_BATTERY_LEVEL, -1)
                    if (level != -1) {
                        batteryLevel = level
                    }
                }
            }
        }
    }
    
    private fun scanForControllers() {
        // Scan for paired controllers
        bluetoothAdapter?.bondedDevices?.forEach { device ->
            if (isControllerDevice(device)) {
                onControllerConnected(device)
            }
        }
    }
    
    private fun isControllerDevice(device: BluetoothDevice): Boolean {
        // Check if device is a VR controller
        val name = device.name?.lowercase() ?: ""
        return name.contains("controller") || name.contains("daydream") || 
               name.contains("gear vr") || name.contains("oculus") ||
               name.contains("vr") || device.bluetoothClass?.majorDeviceClass == BluetoothClass.Device.Major.PERIPHERAL
    }
    
    private fun onControllerConnected(device: BluetoothDevice) {
        connectedController = device
        // In real implementation, would set up HID connection
        Log.d("ControllerManager", "Controller connected: ${device.name}")
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
    
    // Handle input from Android's InputDevice API (for Daydream, etc.)
    fun onGenericMotionEvent(event: MotionEvent): Boolean {
        val deviceId = event.deviceId
        inputDevice = context.getSystemService(Context.INPUT_SERVICE) as InputManager
            .getInputDevice(deviceId)
        
        if (inputDevice == null) return false
        
        // Process axes
        val axes = event.getAxisValue(MotionEvent.AXIS_X) to event.getAxisValue(MotionEvent.AXIS_Y)
        touchpadX = axes.first
        touchpadY = axes.second
        
        // Touchpad
        val touchX = event.getAxisValue(MotionEvent.AXIS_TOUCH_X)
        val touchY = event.getAxisValue(MotionEvent.AXIS_TOUCH_Y)
        if (touchX != 0f || touchY != 0f) {
            touchpadTouched = true
            touchpadDeltaX = touchX - touchpadX
            touchpadDeltaY = touchY - touchpadY
            touchpadX = touchX
            touchpadY = touchY
        } else {
            touchpadTouched = false
            touchpadDeltaX = 0f
            touchpadDeltaY = 0f
        }
        
        // Trigger
        triggerValue = event.getAxisValue(MotionEvent.AXIS_BRAKE)
        gripValue = event.getAxisValue(MotionEvent.AXIS_GAS)
        
        // Thumbstick
        thumbstickX = event.getAxisValue(MotionEvent.AXIS_HAT_X)
        thumbstickY = event.getAxisValue(MotionEvent.AXIS_HAT_Y)
        
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
        context.unregisterReceiver(bluetoothReceiver)
        controllerStateChannel.close()
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