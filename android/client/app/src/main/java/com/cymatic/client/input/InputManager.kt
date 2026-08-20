package com.cymatic.client.input

import com.cymatic.client.network.model.InputPacket
import com.cymatic.client.network.model.HeadPoseData
import com.cymatic.client.network.model.GazeData
import com.cymatic.client.network.model.ControllerData
import com.cymatic.client.network.model.VoiceData

class InputManager {
    
    data class HeadPosePacket(
        val timestamp: Long,
        val position: FloatArray,
        val rotation: FloatArray
    )
    
    fun createInputPacket(
        headPose: HeadPosePacket,
        gazeDirection: FloatArray,
        controllerData: ControllerData? = null,
        voiceData: VoiceData? = null
    ): InputPacket {
        return InputPacket(
            timestamp = headPose.timestamp,
            headPose = HeadPoseData(
                position = headPose.position,
                rotation = headPose.rotation
            ),
            gaze = GazeData(
                origin = headPose.position,
                direction = gazeDirection,
                targetId = null,
                targetPosition = FloatArray(3),
                dwellProgress = 0f
            ),
            controller = controllerData ?: ControllerData(
                selectPressed = false,
                menuPressed = false,
                pttPressed = false,
                touchpadDelta = Pair(0f, 0f),
                touchpadPosition = Pair(0f, 0f),
                touchpadTouched = false
            ),
            voice = voiceData ?: VoiceData(isRecording = false, data = null),
            handTracking = null
        )
    }
}
