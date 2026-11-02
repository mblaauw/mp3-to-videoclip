import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ProjectSummary } from "./api";
import { OPEN_SETTINGS } from "./api/errorAction";
import { ArchiveShell } from "./shell/ArchiveShell";
import { FilmShell } from "./shell/FilmShell";
import { LibraryShell } from "./shell/LibraryShell";
import { goArchive, goFilm, goLibrary, useHashRoute } from "./shell/route";
import { notifyProjectChanged, PROJECT_CHANGED } from "./shell/projectEvents";
import { SettingsPanel } from "./shell/settings/SettingsPanel";
import { ToastTray } from "./ToastTray";

export function App() {
  const route = useHashRoute();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const openSettings = () => setSettingsOpen(true);
  useEffect(() => {
    const open = () => setSettingsOpen(true);
    window.addEventListener(OPEN_SETTINGS, open);
    return () => window.removeEventListener(OPEN_SETTINGS, open);
  }, []);

  const loadEpoch = useRef(0);
  const refresh = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    try {
      const next = await api.projects();
      if (epoch !== loadEpoch.current) return;
      setProjects(next);
      setError(null);
    } catch (caught) {
      if (epoch !== loadEpoch.current) return;
      setError(String(caught));
    } finally {
      if (epoch === loadEpoch.current) setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const changed = () => void refresh();
    window.addEventListener(PROJECT_CHANGED, changed);
    return () => window.removeEventListener(PROJECT_CHANGED, changed);
  }, [refresh]);

  const created = async (slug: string, first: "track" | "story" = "track") => {
    await refresh();
    goFilm(slug, first);
  };

  const dialog = settingsOpen ? (
    <SettingsPanel
      onClose={() => setSettingsOpen(false)}
      onSaved={() => {
        void refresh();
        notifyProjectChanged();
      }}
    />
  ) : null;

  if (route.kind === "library") {
    return (
      <>
        <LibraryShell
          projects={projects}
          loading={loading}
          error={error}
          onOpen={(slug, stage) => goFilm(slug, stage)}
          onArchive={goArchive}
          onCreated={(slug, first) => void created(slug, first)}
          onSettings={openSettings}
          onRetry={() => void refresh()}
        />
        {dialog}
        <ToastTray />
      </>
    );
  }

  const selected = projects.find((project) => project.slug === route.slug) || null;
  if (!selected) {
    return (
      <>
        <div className="shell library-shell">
          <main className="library-main">
            <div className="library">
              <p className="empty">
                {loading ? "Loading the library…" : "That film is not in the library."}{" "}
                <a href="#/">Back to your films</a>.
              </p>
            </div>
          </main>
        </div>
        <ToastTray />
      </>
    );
  }

  if (route.kind === "archive") {
    return (
      <>
        <ArchiveShell project={selected} onBack={goLibrary} onSettings={openSettings} />
        {dialog}
        <ToastTray />
      </>
    );
  }

  return (
    <>
      <FilmShell
        key={selected.slug}
        project={selected}
        stage={route.stage}
        onNavigate={(stage) => goFilm(selected.slug, stage)}
        onProjectsChanged={() => void refresh()}
        onSettings={openSettings}
      />
      {dialog}
      <ToastTray />
    </>
  );
}
