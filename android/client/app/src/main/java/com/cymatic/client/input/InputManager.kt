package com.cymatic.client.input

import com.cymatic.client.network.model.InputPacket

class InputManager {

    data class HeadPosePacket(
        val timestamp: Long,
        val position: FloatArray,
        val rotation: FloatArray
    )

    private fun nowSeconds(): Double = System.currentTimeMillis() / 1000.0

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
            timestamp = nowSeconds()
        )
    }

    fun createHeadPosePacket(position: FloatArray, rotation: FloatArray): InputPacket {
        return InputPacket(
            inputType = InputPacket.TYPE_HEAD_POSE,
            payload = mapOf(
                "position" to position.toList(),
                "rotation" to rotation.toList()
            ),
            timestamp = nowSeconds()
        )
    }

    fun createGazePacket(origin: FloatArray, direction: FloatArray): InputPacket {
        return InputPacket(
            inputType = InputPacket.TYPE_GAZE,
            payload = mapOf(
                "origin" to origin.toList(),
                "direction" to direction.toList()
            ),
            timestamp = nowSeconds()
        )
    }
}
