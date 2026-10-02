package com.cymatic.client.input

import com.cymatic.client.network.model.InputPacket

class InputManager {

    data class HeadPosePacket(
        val timestamp: Long,
        val position: FloatArray,
        val rotation: FloatArray
    )

    // Epoch ms, matching Unity's InputManager.InputPacket.timestamp (long, ms) -
    // packets are relayed to the render server unchanged over the signaling channel.
    private fun nowMillis(): Long = System.currentTimeMillis()

    fun createInputPacket(
        headPose: HeadPosePacket,
        gazeDirection: FloatArray,
        controllerData: com.cymatic.client.network.model.ControllerData? = null,
        voiceData: com.cymatic.client.network.model.VoiceData? = null
    ): InputPacket {
        // Backend contract: {input_type, payload, timestamp}.
        // Pack head pose + gaze into a single head_pose payload for backwards compat.
        val payload = mapOf(
            "position" to headPose.position.toList(),
            "rotation" to headPose.rotation.toList(),
            "gaze_direction" to gazeDirection.toList()
        )
        return InputPacket(
            inputType = InputPacket.TYPE_HEAD_POSE,
            payload = payload,
            timestamp = nowMillis()
        )
    }

    fun createHeadPosePacket(position: FloatArray, rotation: FloatArray): InputPacket {
        return InputPacket(
            inputType = InputPacket.TYPE_HEAD_POSE,
            payload = mapOf(
                "position" to position.toList(),
                "rotation" to rotation.toList()
            ),
            timestamp = nowMillis()
        )
    }

    fun createGazePacket(origin: FloatArray, direction: FloatArray): InputPacket {
        return InputPacket(
            inputType = InputPacket.TYPE_GAZE,
            payload = mapOf(
                "origin" to origin.toList(),
                "direction" to direction.toList()
            ),
            timestamp = nowMillis()
        )
    }

    fun createControllerPacket(state: ControllerManager.ControllerState): InputPacket {
        return InputPacket(
            inputType = InputPacket.TYPE_CONTROLLER,
            payload = mapOf(
                "select_pressed" to state.selectPressed,
                "menu_pressed" to state.menuPressed,
                "ptt_pressed" to state.pttPressed,
                "touchpad_x" to state.touchpadX,
                "touchpad_y" to state.touchpadY,
                "touchpad_touched" to state.touchpadTouched,
                "trigger" to state.triggerValue,
                "grip" to state.gripValue,
                "thumbstick_x" to state.thumbstickX,
                "thumbstick_y" to state.thumbstickY,
                "battery_level" to state.batteryLevel
            ),
            timestamp = nowMillis()
        )
    }
}
