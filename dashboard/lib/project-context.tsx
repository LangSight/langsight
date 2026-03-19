"use client";

/**
 * Project context — stores the active project for the current session.
 *
 * The active project is persisted in localStorage so it survives page
 * refreshes. All data-fetching hooks append ?project_id=<id> when a
 * project is selected.
 *
 * Usage:
 *   // In any component:
 *   const { activeProject, setActiveProject } = useProject();
 *
 *   // In API calls:
 *   const { projectParam } = useProject();
 *   useSWR(`/api/agents/sessions${projectParam}`, fetcher);
 */

import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import type { ProjectResponse } from "./types";

interface ProjectContextValue {
  activeProject: ProjectResponse | null;
  setActiveProject: (p: ProjectResponse | null) => void;
  projectParam: string;   // "&project_id=xxx" or ""
  isLoading: boolean;
}

const ProjectContext = createContext<ProjectContextValue>({
  activeProject: null,
  setActiveProject: () => {},
  projectParam: "",
  isLoading: true,
});

const STORAGE_KEY = "langsight_active_project";

export function ProjectProvider({ children }: { children: ReactNode }) {
  const [activeProject, setActiveProjectState] = useState<ProjectResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // Restore from localStorage on mount
  useEffect(() => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        setActiveProjectState(JSON.parse(stored) as ProjectResponse);
      }
    } catch {
      // Ignore parse errors — treat as no project stored
    }
    setIsLoading(false);
  }, []);

  const setActiveProject = useCallback((p: ProjectResponse | null) => {
    setActiveProjectState(p);
    try {
      if (p) {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(p));
      } else {
        localStorage.removeItem(STORAGE_KEY);
      }
    } catch {
      // Ignore storage errors (private browsing, quota exceeded)
    }
  }, []);

  const projectParam = activeProject ? `&project_id=${encodeURIComponent(activeProject.id)}` : "";

  return (
    <ProjectContext.Provider value={{ activeProject, setActiveProject, projectParam, isLoading }}>
      {children}
    </ProjectContext.Provider>
  );
}

export function useProject(): ProjectContextValue {
  return useContext(ProjectContext);
}
