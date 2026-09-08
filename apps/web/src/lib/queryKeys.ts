export const queryKeys = {
  projects: {
    all: ["projects"] as const,
    lists: () => [...queryKeys.projects.all, "list"] as const,
    detail: (id: number) => [...queryKeys.projects.all, "detail", id] as const,
  },
  project: (id: number) => [...queryKeys.projects.all, id] as const,
  specs: {
    all: (projectId: number) => ["specs", projectId] as const,
    list: (projectId: number) => [...queryKeys.specs.all(projectId), "list"] as const,
    detail: (projectId: number, specId: number) => [...queryKeys.specs.all(projectId), specId] as const,
  },
  assets: {
    all: (projectId: number) => ["assets", projectId] as const,
    list: (projectId: number) => [...queryKeys.assets.all(projectId), "list"] as const,
    detail: (assetId: number) => ["asset", assetId] as const,
  },
  jobs: {
    all: ["jobs"] as const,
    detail: (jobId: string) => [...queryKeys.jobs.all, jobId] as const,
  },
  generationRuns: (projectId: number) => ["generationRuns", projectId] as const,
  scenePackages: (projectId: number) => ["scenePackages", projectId] as const,
  streamSessions: (projectId: number) => ["streamSessions", projectId] as const,
  credits: {
    balance: ["credits", "balance"] as const,
    usage: ["credits", "usage"] as const,
    costs: ["credits", "costs"] as const,
  },
  analytics: {
    project: (projectId: number) => ["analytics", "project", projectId] as const,
    session: (sessionId: number) => ["analytics", "session", sessionId] as const,
  },
}
