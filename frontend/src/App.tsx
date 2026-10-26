import { useCallback, useEffect, useState } from "react";
import { api, type ProjectSummary } from "./api";
import { ArchiveShell, FilmShell, LibraryShell } from "./shell/FilmShell";
import { goArchive, goFilm, goLibrary, useHashRoute } from "./shell/route";
import { notifyProjectChanged, PROJECT_CHANGED } from "./shell/projectEvents";
import { SettingsDialog } from "./shell/SettingsDialog";
import { ToastTray } from "./ToastTray";

export function App() {
  const route = useHashRoute();
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const openSettings = () => setSettingsOpen(true);

  const refresh = useCallback(async () => {
    try {
      setProjects(await api.projects());
      setError(null);
    } catch (caught) {
      setError(String(caught));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void refresh();
    const changed = () => void refresh();
    window.addEventListener(PROJECT_CHANGED, changed);
    return () => window.removeEventListener(PROJECT_CHANGED, changed);
  }, [refresh]);

  const created = async (slug: string) => {
    await refresh();
    goFilm(slug, "track");
  };

  const dialog = settingsOpen ? (
    <SettingsDialog
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
          onCreated={(slug) => void created(slug)}
          onSettings={openSettings}
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
