package com.cymatic.client.ui.main

import android.content.Intent
import android.os.Bundle
import android.view.View
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.lifecycle.viewmodel.ComposableViewModelProviderFactory
import com.cymatic.client.R
import com.cymatic.client.databinding.ActivityMainBinding
import com.cymatic.client.ui.vr.VRActivity
import com.cymatic.client.ui.diagnostics.DiagnosticsActivity
import dagger.hilt.android.AndroidEntryPoint
import kotlinx.coroutines.launch

@AndroidEntryPoint
class MainActivity : AppCompatActivity() {

    private var _binding: ActivityMainBinding? = null
    private val binding get() = _binding!!
    
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        _binding = ActivityMainBinding.inflate(layoutInflater)
        setContentView(binding.root)
        
        setupClickListeners()
        checkPermissions()
    }
    
    private fun setupClickListeners() {
        binding.btnStartVR.setOnClickListener {
            val intent = Intent(this, VRActivity::class.java)
            startActivity(intent)
        }
        
        binding.btnDiagnostics.setOnClickListener {
            val intent = Intent(this, DiagnosticsActivity::class.java)
            startActivity(intent)
        }
        
        binding.btnSettings.setOnClickListener {
            // TODO: Open settings
        }
    }
    
    private fun checkPermissions() {
        val requiredPermissions = arrayOf(
            android.Manifest.permission.CAMERA,
            android.Manifest.permission.RECORD_AUDIO
        )
        
        val missingPermissions = requiredPermissions.filter { checkSelfPermission(it) != android.content.pm.PackageManager.PERMISSION_GRANTED }
        
        if (missingPermissions.isNotEmpty()) {
            requestPermissions(missingPermissions.toTypedArray(), 100)
        }
    }
    
    override fun onDestroy() {
        super.onDestroy()
        _binding = null
    }
}