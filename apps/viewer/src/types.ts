// Mirrors services/worker/app/agents/scene_package.py and
// packages/cymatic-shared/cymatic_shared/schemas/simulation_spec.py (NavigationSpec).
// Kept intentionally close to the Pydantic wire shape rather than "cleaned up",
// so future schema changes are easy to diff against the backend source.

export interface Project {
  id: number;
  name: string;
  domain: string;
  status: string;
}

export interface SceneEntity {
  id: string;
  name: string;
  type: string;
  position: [number, number, number];
  rotation?: [number, number, number];
  scale?: [number, number, number];
  prefab_path?: string | null;
  properties?: Record<string, unknown>;
  components?: Record<string, unknown>[];
  children?: SceneEntity[];
}

export interface NavigationPoint {
  id: string;
  name: string;
  position: [number, number, number];
  description?: string | null;
  connections: string[];
}

export interface NavigationPath {
  from: string;
  to: string;
  type: "walk" | "teleport";
  waypoints?: [number, number, number][] | null;
}

export interface NavigationSpec {
  points: NavigationPoint[];
  paths: NavigationPath[];
  default_start_point: string;
}

export interface CustomLight {
  type: string;
  position: [number, number, number];
  color?: [number, number, number];
  intensity?: number;
  range?: number;
  angle?: number;
}

export interface LightingData {
  preset: string;
  time_of_day: string;
  ambient_intensity: number;
  sun_direction: [number, number, number];
  custom_lights: CustomLight[];
}

export interface ScenePackage {
  metadata: {
    format: string;
    spec_version: number;
    generated_at: string;
    domain?: string;
  };
  domain: string;
  entities: SceneEntity[];
  navigation: NavigationSpec;
  lighting: LightingData;
  performance_budget?: {
    max_entities?: number;
    max_triangles?: number;
  };
}

export interface ViewResponse {
  project: { id: number; name: string; domain: string };
  scene_package: ScenePackage;
}
