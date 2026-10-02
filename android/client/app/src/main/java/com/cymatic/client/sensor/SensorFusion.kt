package com.cymatic.client.sensor

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import kotlin.math.abs
import kotlin.math.asin
import kotlin.math.atan2
import kotlin.math.copysign
import kotlin.math.sqrt

class SensorFusion(private val context: Context) : SensorEventListener {

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager

    // Sensors — only register fused vector + low-rate magnetometer to save thermal/CPU
    private val rotationVector = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
    private val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    private val magnetic = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)
    private val gameRotationVector = sensorManager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)

    // State
    private var orientation = FloatArray(4) // Quaternion [x, y, z, w]
    private var angularVelocity = FloatArray(3)
    private var linearAccel = FloatArray(3)
    private var position = FloatArray(3)
    private var velocity = FloatArray(3)

    // Kalman filter state for orientation (quaternion)
    private var orientationKF = KalmanFilterQuaternion()

    // Kalman filter state for position (3D) — low-end: disabled by default, high drift risk
    private var positionKF = KalmanFilterPosition3D()

    // Gravity / geomagnetic reference (low-rate)
    private var gravityVector = FloatArray(3)
    private var geomagneticVector = FloatArray(3)

    // Per-sensor timestamps — fixes shared lastTimestamp drift (134)
    private var lastOrientationTimestamp = 0L
    private var lastPositionTimestamp = 0L
    private var isRunning = false
    private var firstOrientation = true

    init {
        orientation[3] = 1f // w = 1 (identity quaternion)
        gravityVector[1] = -1.0f // Gravity points down (Y-up)
    }

    fun start() {
        isRunning = true
        registerSensors()
    }

    fun stop() {
        isRunning = false
        unregisterSensors()
    }

    fun onResume() {
        if (!isRunning) return
        registerSensors()
    }

    fun onPause() {
        unregisterSensors()
    }

    private fun registerSensors() {
        // Thermal-aware: gameRotationVector already fuses accel+gyro at 50Hz.
        // Register ONLY fused vector at GAME (50Hz) + magnetometer at NORMAL (5Hz) when available.
        // Avoids 4 sensors * 50Hz = 200Hz events (≈5% CPU thermal).
        if (gameRotationVector != null) {
            sensorManager.registerListener(this, gameRotationVector, SensorManager.SENSOR_DELAY_GAME)
            magnetic?.let {
                sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
            }
        } else if (rotationVector != null) {
            sensorManager.registerListener(this, rotationVector, SensorManager.SENSOR_DELAY_GAME)
            magnetic?.let {
                sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL)
            }
        } else {
            // Fallback only when no fused vector: accel+gyro at GAME, mag at NORMAL
            accelerometer?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
            gyroscope?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_GAME) }
            magnetic?.let { sensorManager.registerListener(this, it, SensorManager.SENSOR_DELAY_NORMAL) }
        }

        // Initialize Kalman filters
        orientationKF = KalmanFilterQuaternion()
        positionKF = KalmanFilterPosition3D()

        firstOrientation = true
        lastOrientationTimestamp = 0L
        lastPositionTimestamp = 0L
    }

    private fun unregisterSensors() {
        sensorManager.unregisterListener(this)
    }

    override fun onSensorChanged(event: SensorEvent) {
        when (event.sensor.type) {
            Sensor.TYPE_GAME_ROTATION_VECTOR, Sensor.TYPE_ROTATION_VECTOR -> {
                // Get quaternion from rotation vector
                val q = FloatArray(4)
                SensorManager.getQuaternionFromVector(q, event.values)

                // Per-sensor dt — not shared with position path
                val dt = if (lastOrientationTimestamp > 0) (event.timestamp - lastOrientationTimestamp) / 1_000_000_000.0 else 0.016
                lastOrientationTimestamp = event.timestamp

                // Clamp dt to avoid jumps after pause/resume causing large integration
                val clampedDt = dt.coerceIn(0.001, 0.05)
                if (firstOrientation) {
                    orientation = q.copyOf()
                    orientationKF.initialize(q)
                    firstOrientation = false
                } else {
                    orientation = orientationKF.update(q, clampedDt)
                }
            }
            Sensor.TYPE_GYROSCOPE -> {
                angularVelocity = event.values.copyOf()
            }
            Sensor.TYPE_LINEAR_ACCELERATION -> {
                linearAccel = event.values.copyOf()
                updatePosition(event.timestamp)
            }
            Sensor.TYPE_ACCELEROMETER -> {
                // Keep gravity reference at low rate if no fused vector
                if (gameRotationVector == null && rotationVector == null) {
                    gravityVector = event.values.copyOf()
                }
            }
            Sensor.TYPE_MAGNETIC_FIELD -> {
                geomagneticVector = event.values.copyOf()
            }
        }
    }

    private fun updatePosition(timestamp: Long) {
        if (lastPositionTimestamp == 0L) {
            lastPositionTimestamp = timestamp
            return
        }

        val rawDt = (timestamp - lastPositionTimestamp) / 1_000_000_000.0
        lastPositionTimestamp = timestamp
        // Drop large gaps (pause/resume) to prevent integration explosion
        if (rawDt <= 0 || rawDt > 0.1) return
        val dt = rawDt.coerceIn(0.001, 0.05)

        // Drift mitigation: ignore position integration on low-end phone VR.
        // For MVP we track only orientation; position is optional and heavily damped.
        // Apply dead-zone on linear accel magnitude and zero-velocity update.
        val accelMag = sqrt(linearAccel[0]*linearAccel[0] + linearAccel[1]*linearAccel[1] + linearAccel[2]*linearAccel[2])
        val isStatic = accelMag < 0.15f // 0.15 m/s² noise floor for phone IMU
        if (isStatic) {
            // Zero-velocity update: decay velocity aggressively when device static
            for (i in 0..2) velocity[i] *= 0.5f
            if (sqrt(velocity[0]*velocity[0] + velocity[1]*velocity[1] + velocity[2]*velocity[2]) < 0.01f) {
                velocity[0] = 0f; velocity[1] = 0f; velocity[2] = 0f
            }
            return
        }

        // Use Kalman filter for position estimation with clamping
        position = positionKF.update(linearAccel, dt)
        velocity = positionKF.getVelocity()
        // Hard clamp position to avoid runaway drift (phone has no position tracking)
        for (i in 0..2) {
            position[i] = position[i].coerceIn(-5f, 5f)
            velocity[i] = velocity[i].coerceIn(-2f, 2f)
        }
    }

    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        // No-op: avoid extra work
    }

    // Getters
    fun getOrientation(): FloatArray = orientation.copyOf()

    fun getOrientationEuler(): FloatArray {
        val q = orientation
        val euler = FloatArray(3)

        // Convert quaternion to Euler angles (yaw, pitch, roll)
        val siny_cosp = 2.0f * (q[3] * q[2] + q[0] * q[1])
        val cosy_cosp = 1.0f - 2.0f * (q[1] * q[1] + q[2] * q[2])
        val yaw = atan2(siny_cosp, cosy_cosp)

        val sinp = 2.0f * (q[3] * q[1] - q[2] * q[0])
        val pitch = if (abs(sinp) >= 1.0f) copysign(kotlin.math.PI.toFloat() / 2f, sinp) else asin(sinp)

        val sinr_cosp = 2.0f * (q[3] * q[0] + q[1] * q[2])
        val cosr_cosp = 1.0f - 2.0f * (q[0] * q[0] + q[1] * q[1])
        val roll = atan2(sinr_cosp, cosr_cosp)

        return floatArrayOf(yaw, pitch, roll)
    }

    fun getOrientationMatrix(): FloatArray {
        val m = FloatArray(16)
        val q = orientation
        val qx = q[0]; val qy = q[1]; val qz = q[2]; val qw = q[3]

        m[0] = 1 - 2 * (qy * qy + qz * qz)
        m[1] = 2 * (qx * qy + qw * qz)
        m[2] = 2 * (qx * qz - qw * qy)
        m[3] = 0f

        m[4] = 2 * (qx * qy - qw * qz)
        m[5] = 1 - 2 * (qx * qx + qz * qz)
        m[6] = 2 * (qy * qz + qw * qx)
        m[7] = 0f

        m[8] = 2 * (qx * qz + qw * qy)
        m[9] = 2 * (qy * qz - qw * qx)
        m[10] = 1 - 2 * (qx * qx + qy * qy)
        m[11] = 0f

        m[12] = 0f
        m[13] = 0f
        m[14] = 0f
        m[15] = 1f

        return m
    }

    fun getForwardVector(): FloatArray {
        val m = getOrientationMatrix()
        return floatArrayOf(-m[8], -m[9], -m[10]) // Forward is -Z in OpenGL
    }

    fun getUpVector(): FloatArray {
        val m = getOrientationMatrix()
        return floatArrayOf(m[4], m[5], m[6]) // Up is Y
    }

    fun getRightVector(): FloatArray {
        val m = getOrientationMatrix()
        return floatArrayOf(m[0], m[1], m[2]) // Right is X
    }

    fun getPosition(): FloatArray = position.copyOf()
    fun getVelocity(): FloatArray = velocity.copyOf()
    fun getAngularVelocity(): FloatArray = angularVelocity.copyOf()
    fun getLinearAcceleration(): FloatArray = linearAccel.copyOf()

    companion object {
        private const val PI = 3.14159265359
    }
}

// Kalman Filter for Quaternion Orientation
class KalmanFilterQuaternion {
    private var state = FloatArray(4) // Quaternion state [x, y, z, w]
    private var covariance = FloatArray(16) // 4x4 covariance matrix
    private var processNoise = FloatArray(16) // Q matrix
    private var measurementNoise = FloatArray(16) // R matrix
    private var initialized = false

    init {
        // Initialize process noise (small for quaternion)
        for (i in 0..15) processNoise[i] = if (i % 5 == 0) 0.001f else 0f

        // Initialize measurement noise (from sensor specs)
        for (i in 0..15) measurementNoise[i] = if (i % 5 == 0) 0.01f else 0f

        // Initial covariance
        for (i in 0..15) covariance[i] = if (i % 5 == 0) 1.0f else 0f
    }

    fun initialize(quaternion: FloatArray) {
        state = quaternion.copyOf()
        initialized = true
    }

    fun update(measurement: FloatArray, dt: Double): FloatArray {
        if (!initialized) {
            initialize(measurement)
            return state
        }

        // Covariance prediction: P = P + Q
        predictCovariance()

        // Innovation: y = z - x
        val innovation = FloatArray(4)
        for (i in 0..3) innovation[i] = measurement[i] - state[i]

        // Normalize innovation
        val innovationNorm = sqrt(innovation[0]*innovation[0] + innovation[1]*innovation[1] +
                                 innovation[2]*innovation[2] + innovation[3]*innovation[3])
        if (innovationNorm > 0.001) {
            val S = FloatArray(16)
            for (i in 0..15) S[i] = covariance[i] + measurementNoise[i]

            val K = FloatArray(16)
            for (i in 0..3) {
                val idx = i * 5
                K[idx] = covariance[idx] / S[idx].coerceAtLeast(1e-6f)
            }

            for (i in 0..3) {
                state[i] += K[i * 5] * innovation[i]
            }

            for (i in 0..3) {
                val idx = i * 5
                covariance[idx] = (1 - K[idx]) * covariance[idx]
            }
        }

        normalizeQuaternion(state)

        return state
    }

    private fun predictCovariance() {
        for (i in 0..15) {
            covariance[i] += processNoise[i]
        }
    }

    private fun normalizeQuaternion(q: FloatArray) {
        val norm = sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3])
        if (norm > 1e-6f) {
            for (i in 0..3) q[i] /= norm
        }
    }
}

// Kalman Filter for 3D Position — damped to prevent drift (362)
class KalmanFilterPosition3D {
    private var position = FloatArray(3) // x, y, z
    private var velocity = FloatArray(3) // vx, vy, vz
    private var covariance = FloatArray(36) // 6x6 covariance [pos, vel]
    private var processNoise = FloatArray(36)
    private var initialized = false

    init {
        for (i in 0..5) {
            for (j in 0..5) {
                processNoise[i * 6 + j] = if (i == j) {
                    if (i < 3) 0.01f else 0.1f
                } else 0f
            }
        }

        for (i in 0..5) {
            for (j in 0..5) {
                covariance[i * 6 + j] = if (i == j) {
                    if (i < 3) 1.0f else 10.0f
                } else 0f
            }
        }
    }

    fun update(acceleration: FloatArray, dt: Double): FloatArray {
        val dtf = dt.toFloat()

        if (!initialized) {
            initialized = true
            return position
        }
        // Leaky integration with drift guard (362)
        for (i in 0..2) {
            // High-pass: ignore tiny accel
            val a = if (abs(acceleration[i]) < 0.12f) 0f else acceleration[i]
            position[i] = position[i] + velocity[i] * dtf + 0.5f * a * dtf * dtf
            // Velocity decay 0.92 (was 0.98) to limit runaway; extra damping when static
            velocity[i] = (velocity[i] + a * dtf) * 0.92f
            // Zero-velocity clamp
            if (abs(velocity[i]) < 0.005f) velocity[i] = 0f
        }
        // Slow position leak to zero for phone VR (no positional tracking)
        for (i in 0..2) position[i] *= 0.995f
        if (sqrt(position[0]*position[0]+position[1]*position[1]+position[2]*position[2]) < 0.005f) {
            position[0]=0f; position[1]=0f; position[2]=0f
        }

        predictCovariance(dtf)

        return position
    }

    fun getVelocity(): FloatArray = velocity.copyOf()

    private fun predictCovariance(dtf: Float) {
        val newCov = FloatArray(36)

        for (i in 0..2) {
            for (j in 0..2) {
                var sum = covariance[i*6 + j]
                sum += dtf * (covariance[i*6 + 3 + j] + covariance[(3+i)*6 + j])
                sum += dtf * dtf * covariance[(3+i)*6 + 3 + j]
                sum += processNoise[i*6 + j]
                newCov[i*6 + j] = sum
            }
        }

        for (i in 0..2) {
            for (j in 0..2) {
                var sum = covariance[i*6 + 3 + j]
                sum += dtf * covariance[(3+i)*6 + 3 + j]
                sum += processNoise[i*6 + 3 + j]
                newCov[i*6 + 3 + j] = sum
            }
        }

        for (i in 0..2) {
            for (j in 0..2) {
                newCov[(3+i)*6 + j] = newCov[i*6 + 3 + j]
            }
        }

        for (i in 0..2) {
            for (j in 0..2) {
                newCov[(3+i)*6 + 3 + j] = covariance[(3+i)*6 + 3 + j] + processNoise[(3+i)*6 + 3 + j]
            }
        }

        covariance = newCov
    }

    companion object {
        private const val PI = 3.14159265359
    }
}
