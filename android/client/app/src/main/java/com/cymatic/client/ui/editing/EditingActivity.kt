package com.cymatic.client.ui.editing

import android.os.Bundle
import android.view.View
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.lifecycle.lifecycleScope
import androidx.recyclerview.widget.LinearLayoutManager
import com.cymatic.client.R
import com.cymatic.client.databinding.ActivityEditingBinding
import com.cymatic.client.network.ApiClient
import com.cymatic.client.network.model.EditOperation
import com.cymatic.client.network.model.EditRequest
import com.cymatic.client.network.model.EditResponse
import com.cymatic.client.util.PreferencesManager
import kotlinx.coroutines.launch
import org.json.JSONObject

class EditingActivity : AppCompatActivity() {

    private var _binding: ActivityEditingBinding? = null
    private val binding get() = _binding!!
    
    private lateinit var preferencesManager: PreferencesManager
    private var projectId: Int = -1
    private var specId: Int = -1
    private var currentEntities: MutableList<JSONObject> = mutableListOf()
    private var selectedEntityId: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        _binding = ActivityEditingBinding.inflate(layoutInflater)
        setContentView(binding.root)
        
        preferencesManager = PreferencesManager(this)
        
        projectId = intent.getIntExtra("project_id", -1)
        specId = intent.getIntExtra("spec_id", -1)
        
        if (projectId == -1 || specId == -1) {
            Toast.makeText(this, "Invalid project/spec", Toast.LENGTH_SHORT).show()
            finish()
            return
        }
        
        initViews()
        loadSpec()
    }
    
    private fun initViews() {
        binding.btnBack.setOnClickListener { finish() }
        binding.btnSave.setOnClickListener { saveEdits() }
        binding.btnAddEntity.setOnClickListener { showAddEntityDialog() }
        binding.btnUndo.setOnClickListener { undo() }
        binding.btnRedo.setOnClickListener { redo() }
        
        binding.rvEntities.layoutManager = LinearLayoutManager(this)
    }
    
    private fun loadSpec() {
        lifecycleScope.launch {
            try {
                val response = ApiClient.apiService.getSpec(projectId, specId).await()
                
                if (response.isSuccessful) {
                    val spec = response.body()!!
                    runOnUiThread {
                        binding.tvSpecTitle.text = spec.payloadJson["metadata"]?.getString("title") ?: "Spec v${spec.version}"
                        binding.tvSpecVersion.text = "Version ${spec.version}"
                        
                        val entities = spec.payloadJson["entities"] as? List<Any> ?: emptyList()
                        currentEntities = entities.map { it as JSONObject }.toMutableList()
                        updateEntityList()
                    }
                } else {
                    runOnUiThread {
                        Toast.makeText(this@EditingActivity, "Failed to load spec: ${response.message()}", Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this@EditingActivity, "Error: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }
    
    private fun updateEntityList() {
        // Update RecyclerView with entities
        // binding.rvEntities.adapter = EntityAdapter(currentEntities) { entity ->
        //     selectEntity(entity.getString("id"))
        // }
    }
    
    private fun selectEntity(entityId: String) {
        selectedEntityId = entityId
        // Show entity properties panel
        binding.entityPropertiesPanel.visibility = View.VISIBLE
        // Populate with entity properties
    }
    
    private fun showAddEntityDialog() {
        // Show dialog to add new entity type
    }
    
    private fun saveEdits() {
        if (selectedEntityId == null) {
            Toast.makeText(this, "No entity selected", Toast.LENGTH_SHORT).show()
            return
        }
        
        val operations = mutableListOf<EditOperation>()
        // Build operations from UI changes
        
        lifecycleScope.launch {
            try {
                val request = EditRequest(operations = operations)
                val response = ApiClient.apiService.editSpec(projectId, specId, request).await()
                
                if (response.isSuccessful) {
                    val result = response.body()!!
                    runOnUiThread {
                        Toast.makeText(this@EditingActivity, "Edits saved", Toast.LENGTH_SHORT).show()
                        loadSpec() // Reload
                    }
                } else {
                    runOnUiThread {
                        Toast.makeText(this@EditingActivity, "Save failed: ${response.message()}", Toast.LENGTH_LONG).show()
                    }
                }
            } catch (e: Exception) {
                runOnUiThread {
                    Toast.makeText(this@EditingActivity, "Error: ${e.message}", Toast.LENGTH_LONG).show()
                }
            }
        }
    }
    
    private fun undo() {
        // Implement undo
    }
    
    private fun redo() {
        // Implement redo
    }
    
    override fun onDestroy() {
        super.onDestroy()
        _binding = null
    }
}