import { apiFetch } from "./auth";
import type { Project, ViewResponse } from "./types";

export async function listPublishedProjects(): Promise<Project[]> {
  const res = await apiFetch("/v1/projects?limit=100");
  if (!res.ok) throw new Error(`Failed to list projects (${res.status})`);
  const projects = (await res.json()) as Project[];
  return projects.filter((p) => p.status === "published");
}

export async function fetchSceneForViewing(projectId: number): Promise<ViewResponse> {
  const res = await apiFetch(`/v1/projects/${projectId}/scene-package/view`);
  if (!res.ok) {
    if (res.status === 404) throw new Error("No published scene package found for this project");
    if (res.status === 400) throw new Error("Project must be published before it can be viewed");
    throw new Error(`Failed to load scene (${res.status})`);
  }
  return (await res.json()) as ViewResponse;
}
