// Shared Simulation Specification Types
// This file is the source of truth for the simulation spec structure

export type Domain = 'real_estate' | 'heritage';

export interface SimulationSpec {
  domain: Domain;
  metadata: SpecMetadata;
  entities: Entity[];
  navigation: NavigationSpec;
  lighting: LightingSpec;
  copilot_policy: CopilotPolicy;
  performance_budget: PerformanceBudget;
}

export interface SpecMetadata {
  title: string;
  description: string;
  version: string;
  author?: string;
  created_at: string;
  tags?: string[];
}

export interface Entity {
  id: string;
  type: EntityType;
  name: string;
  position: [number, number, number]; // x, y, z
  rotation?: [number, number, number]; // euler angles
  scale?: [number, number, number];
  properties: Record<string, any>;
  children?: Entity[];
}

export type EntityType =
  | 'room'
  | 'wall'
  | 'floor'
  | 'ceiling'
  | 'door'
  | 'window'
  | 'furniture'
  | 'decoration'
  | 'light'
  | 'navigation_point'
  | 'poi'  // point of interest
  | 'audio_zone'
  | 'trigger_zone';

export interface NavigationSpec {
  points: NavigationPoint[];
  paths: NavigationPath[];
  default_start_point: string;
}

export interface NavigationPoint {
  id: string;
  name: string;
  position: [number, number, number];
  description?: string;
  connections: string[]; // connected point IDs
}

export interface NavigationPath {
  from: string;
  to: string;
  type: 'walk' | 'teleport';
  waypoints?: [number, number, number][];
}

export interface LightingSpec {
  preset: LightingPreset;
  time_of_day: 'morning' | 'noon' | 'evening' | 'night';
  ambient_intensity: number;
  sun_direction?: [number, number, number];
  custom_lights?: CustomLight[];
}

export type LightingPreset = 'warm' | 'cool' | 'neutral' | 'golden_hour' | 'blue_hour' | 'custom';

export interface CustomLight {
  type: 'directional' | 'point' | 'spot' | 'area';
  position: [number, number, number];
  color: [number, number, number];
  intensity: number;
  range?: number;
  angle?: number;
}

export interface CopilotPolicy {
  enabled: boolean;
  languages: string[];
  default_language: string;
  personality: CopilotPersonality;
  allowed_actions: CopilotAction[];
  knowledge_base?: string;
}

export type CopilotPersonality = 'helpful_guide' | 'expert_narrator' | 'friendly_assistant' | 'professional_host';

export type CopilotAction =
  | 'highlight_object'
  | 'show_label'
  | 'move_to_point'
  | 'open_menu'
  | 'change_material'
  | 'pause_tour'
  | 'resume_tour'
  | 'play_audio_hint'
  | 'answer_question';

export interface PerformanceBudget {
  target_fps: number;
  max_triangles: number;
  max_draw_calls: number;
  texture_budget_mb: number;
  max_entities: number;
  lod_distances: [number, number, number]; // high, medium, low
}

// Generation Pipeline Types
export interface GenerationJob {
  id: string;
  project_id: number;
  spec_id: number;
  type: 'spec' | 'scene' | 'validation';
  status: 'pending' | 'running' | 'completed' | 'failed';
  progress: number;
  result?: any;
  error?: string;
  created_at: string;
  updated_at: string;
}

export interface AssetManifest {
  assets: AssetReference[];
  total_size_mb: number;
  estimated_load_time_ms: number;
}

export interface AssetReference {
  id: string;
  type: 'model' | 'texture' | 'audio' | 'material';
  uri: string; // MinIO path
  fallback_uri?: string;
  lod_levels?: number;
  required: boolean;
}
