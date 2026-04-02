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
import { useSession } from "next-auth/react";
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
  const { data: session } = useSession();

  const isAdmin = (session?.user as { role?: string } | undefined)?.role === "admin";

  // Restore from localStorage, then revalidate against the API.
  // Stale trust: a deleted or revoked project would strand non-admins with
  // persistent 403/404s until they cleared localStorage.  We now verify the
  // stored project is still accessible before applying it.
  useEffect(() => {
    if (!session) return; // wait until session is known

    let restored: ProjectResponse | null = null;
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) restored = JSON.parse(stored) as ProjectResponse;
    } catch {
      // Ignore parse errors — treat as no stored project
    }

    // Always fetch the current project list so we can revalidate the
    // stored selection and auto-select for non-admins when needed.
    fetch("/api/proxy/projects")
      .then((r) => r.json() as Promise<ProjectResponse[]>)
      .then((projects) => {
        if (!Array.isArray(projects)) return;

        if (restored) {
          // Revalidate: confirm stored project is still in the visible list
          const stillValid = projects.find((p) => p.id === restored!.id);
          if (stillValid) {
            // Refresh metadata (name/slug may have changed) and persist
            setActiveProjectState(stillValid);
            try { localStorage.setItem(STORAGE_KEY, JSON.stringify(stillValid)); } catch { /**/ }
            return;
          }
          // Stored project no longer accessible — clear stale entry
          try { localStorage.removeItem(STORAGE_KEY); } catch { /**/ }
        }

        // No valid stored project — auto-select first for non-admins
        if (!isAdmin && projects.length > 0) {
          const first = projects[0];
          setActiveProjectState(first);
          try { localStorage.setItem(STORAGE_KEY, JSON.stringify(first)); } catch { /**/ }
        }
      })
      .catch(() => {
        // API unreachable — fall back to stored value so the UI isn't blank
        if (restored) setActiveProjectState(restored);
      })
      .finally(() => setIsLoading(false));
  }, [session, isAdmin]); // eslint-disable-line react-hooks/exhaustive-deps

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
