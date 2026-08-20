package com.cymatic.client.sensor

import android.content.Context
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.opengl.Matrix
import kotlinx.coroutines.Dispatchers

class SensorFusion(private val context: Context) : SensorEventListener {

    private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
    
    // Sensors
    private val rotationVector = sensorManager.getDefaultSensor(Sensor.TYPE_ROTATION_VECTOR)
    private val accelerometer = sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)
    private val gyroscope = sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)
    private val magnetic = sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)
    private val gravity = sensorManager.getDefaultSensor(Sensor.TYPE_GRAVITY)
    private val linearAcceleration = sensorManager.getDefaultSensor(Sensor.TYPE_LINEAR_ACCELERATION)
    private val gameRotationVector = sensorManager.getDefaultSensor(Sensor.TYPE_GAME_ROTATION_VECTOR)
    
    // State
    private var orientation = FloatArray(4) // Quaternion [x, y, z, w]
    private var angularVelocity = FloatArray(3)
    private var linearAccel = FloatArray(3)
    private var magneticField = FloatArray(3)
    private var position = FloatArray(3)
    private var velocity = FloatArray(3)
    
    // Kalman filter state for orientation (quaternion)
    private var orientationKF = KalmanFilterQuaternion()
    
    // Kalman filter state for position (3D)
    private var positionKF = KalmanFilterPosition3D()
    
    // Gravity vector for reference
    private var gravityVector = FloatArray(3)
    private var geomagneticVector = FloatArray(3)
    
    // Filters
    private var lastTimestamp = 0L
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
        registerSensors()
    }
    
    fun onPause() {
        unregisterSensors()
    }
    
    private fun registerSensors() {
        // Use game rotation vector if available (no magnetic interference)
        if (gameRotationVector != null) {
            sensorManager.registerListener(this, gameRotationVector, SensorManager.SENSOR_DELAY_FASTEST)
        } else if (rotationVector != null) {
            sensorManager.registerListener(this, rotationVector, SensorManager.SENSOR_DELAY_FASTEST)
        }
        
        sensorManager.registerListener(this, accelerometer, SensorManager.SENSOR_DELAY_FASTEST)
        sensorManager.registerListener(this, gyroscope, SensorManager.SENSOR_DELAY_FASTEST)
        sensorManager.registerListener(this, magnetic, SensorManager.SENSOR_DELAY_FASTEST)
        
        // Initialize Kalman filters
        orientationKF = KalmanFilterQuaternion()
        positionKF = KalmanFilterPosition3D()
        
        firstOrientation = true
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
                
                // Apply Kalman filter to orientation
                val dt = if (lastTimestamp > 0) (event.timestamp - lastTimestamp) / 1_000_000_000.0 else 0.016
                lastTimestamp = event.timestamp
                
                if (firstOrientation) {
                    orientation = q.copyOf()
                    orientationKF.initialize(q)
                    firstOrientation = false
                } else {
                    orientation = orientationKF.update(q, dt)
                }
            }
            Sensor.TYPE_GYROSCOPE -> {
                angularVelocity = event.values.copyOf()
                // Angular velocity used for orientation prediction in Kalman filter
            }
            Sensor.TYPE_LINEAR_ACCELERATION -> {
                linearAccel = event.values.copyOf()
                updatePosition(event.timestamp)
            }
            Sensor.TYPE_ACCELEROMETER -> {
                // Store gravity vector for reference
                if (gravity == null) {
                    gravityVector = event.values.copyOf()
                }
            }
            Sensor.TYPE_MAGNETIC_FIELD -> {
                geomagneticVector = event.values.copyOf()
                // Update heading correction in Kalman filter
            }
        }
    }
    
    private fun updatePosition(timestamp: Long) {
        if (lastTimestamp == 0L) {
            lastTimestamp = timestamp
            return
        }
        
        val dt = (timestamp - lastTimestamp) / 1_000_000_000.0
        lastTimestamp = timestamp
        
        // Use Kalman filter for position estimation
        position = positionKF.update(linearAccel, dt)
        velocity = positionKF.getVelocity()
    }
    
    override fun onAccuracyChanged(sensor: Sensor?, accuracy: Int) {
        // Handle accuracy changes if needed
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
        val pitch = if (abs(sinp) >= 1.0f) copysign(PI / 2, sinp) else asin(sinp)
        
        val sinr_cosp = 2.0f * (q[3] * q[0] + q[1] * q[2])
        val cosr_cosp = 1.0f - 2.0f * (q[0] * q[0] + q[1] * q[1])
        val roll = atan2(sinr_cosp, cosr_cosp)
        
        return floatArrayOf(yaw, pitch, roll)
    }
    
    fun getOrientationMatrix(): FloatArray {
        val m = FloatArray(16)
        val q = orientation
        val qx = q[0], qy = q[1], qz = q[2], qw = q[3]
        
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
        
        // Prediction step: integrate angular velocity (if available)
        // For simplicity, we assume state doesn't change significantly in dt
        // x = x (no control input)
        
        // Covariance prediction: P = F * P * F^T + Q
        // F = identity for quaternion (no change without angular velocity input)
        // P = P + Q
        predictCovariance()
        
        // Update step
        // Innovation: y = z - h(x) = z - x (measurement is quaternion)
        val innovation = FloatArray(4)
        for (i in 0..3) innovation[i] = measurement[i] - state[i]
        
        // Normalize innovation (quaternion difference)
        val innovationNorm = sqrt(innovation[0]*innovation[0] + innovation[1]*innovation[1] + 
                                 innovation[2]*innovation[2] + innovation[3]*innovation[3])
        if (innovationNorm > 0.001) { // Significant difference
            // Kalman gain: K = P * H^T * (H * P * H^T + R)^-1
            // H = identity
            // S = P + R
            val S = FloatArray(16)
            for (i in 0..15) S[i] = covariance[i] + measurementNoise[i]
            
            // K = P * S^-1 (simplified: K = P / (P + R) for diagonal)
            val K = FloatArray(16)
            for (i in 0..3) {
                val idx = i * 5
                K[idx] = covariance[idx] / S[idx]
            }
            
            // Update state: x = x + K * innovation
            for (i in 0..3) {
                state[i] += K[i * 5] * innovation[i]
            }
            
            // Update covariance: P = (I - K) * P
            for (i in 0..3) {
                val idx = i * 5
                covariance[idx] = (1 - K[idx]) * covariance[idx]
            }
        }
        
        // Normalize quaternion
        normalizeQuaternion(state)
        
        return state
    }
    
    private fun predictCovariance() {
        // P = P + Q (F = I)
        for (i in 0..15) {
            covariance[i] += processNoise[i]
        }
    }
    
    private fun normalizeQuaternion(q: FloatArray) {
        val norm = sqrt(q[0]*q[0] + q[1]*q[1] + q[2]*q[2] + q[3]*q[3])
        if (norm > 0) {
            for (i in 0..3) q[i] /= norm
        }
    }
}

// Kalman Filter for 3D Position
class KalmanFilterPosition3D {
    private var position = FloatArray(3) // x, y, z
    private var velocity = FloatArray(3) // vx, vy, vz
    private var covariance = FloatArray(36) // 6x6 covariance [pos, vel]
    private var processNoise = FloatArray(36)
    private var measurementNoise = FloatArray(9) // 3x3 for position measurement
    private var initialized = false
    
    init {
        // Process noise: position gets small noise, velocity gets larger
        for (i in 0..5) {
            for (j in 0..5) {
                processNoise[i * 6 + j] = if (i == j) {
                    if (i < 3) 0.01f else 0.1f // position vs velocity noise
                } else 0f
            }
        }
        
        // Measurement noise for position
        for (i in 0..8) {
            measurementNoise[i] = if (i % 4 == 0) 0.1f else 0f // 10cm position noise
        }
        
        // Initial covariance
        for (i in 0..5) {
            for (j in 0..5) {
                covariance[i * 6 + j] = if (i == j) {
                    if (i < 3) 1.0f else 10.0f // Higher uncertainty in velocity
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
        
        // Prediction step
        // State transition: x = F * x + B * u
        // Position: p = p + v * dt + 0.5 * a * dt^2
        // Velocity: v = v + a * dt
        for (i in 0..2) {
            position[i] = position[i] + velocity[i] * dtf + 0.5f * acceleration[i] * dtf * dtf
            velocity[i] = velocity[i] + acceleration[i] * dtf
        }
        
        // Covariance prediction: P = F * P * F^T + Q
        predictCovariance(dtf)
        
        // Note: We don't have direct position measurement, so no update step
        // In a real implementation, you'd fuse with GPS/visual odometry here
        
        return position
    }
    
    fun getVelocity(): FloatArray = velocity.copyOf()
    
    private fun predictCovariance(dtf: Float) {
        // F matrix for constant velocity model:
        // [ I  dt*I ]
        // [ 0   I   ]
        // P = F * P * F^T + Q
        
        val newCov = FloatArray(36)
        
        // Position-position block: P_pp + dt*(P_pv + P_vp) + dt^2*P_vv + Q_pp
        for (i in 0..2) {
            for (j in 0..2) {
                var sum = covariance[i*6 + j]
                // dt * (P_pv + P_vp)
                sum += dtf * (covariance[i*6 + 3 + j] + covariance[(3+i)*6 + j])
                // dt^2 * P_vv
                sum += dtf * dtf * covariance[(3+i)*6 + 3 + j]
                // Process noise
                sum += processNoise[i*6 + j]
                newCov[i*6 + j] = sum
            }
        }
        
        // Position-velocity block: P_pv + dt*P_vv + Q_pv
        for (i in 0..2) {
            for (j in 0..2) {
                var sum = covariance[i*6 + 3 + j]
                sum += dtf * covariance[(3+i)*6 + 3 + j]
                sum += processNoise[i*6 + 3 + j]
                newCov[i*6 + 3 + j] = sum
            }
        }
        
        // Velocity-position block (symmetric)
        for (i in 0..2) {
            for (j in 0..2) {
                newCov[(3+i)*6 + j] = newCov[i*6 + 3 + j]
            }
        }
        
        // Velocity-velocity block: P_vv + Q_vv
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