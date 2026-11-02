import { type ProjectSummary } from "../api";
import { Library } from "./Library";
import { goLibrary } from "./route";
import { TopBar } from "./TopBar";

export function LibraryShell({
  projects,
  loading,
  error,
  onOpen,
  onArchive,
  onCreated,
  onSettings,
  onRetry,
}: {
  projects: ProjectSummary[];
  loading: boolean;
  error: string | null;
  onOpen: (slug: string, stage: string) => void;
  onArchive: (slug: string) => void;
  onCreated: (slug: string, first?: "track" | "story") => void;
  onSettings: () => void;
  onRetry: () => void;
}) {
  return (
    <div className="shell library-shell">
      <TopBar
        project={null}
        stage={null}
        budget={null}
        onNavigate={() => goLibrary()}
        onSettings={onSettings}
        onBudgetChanged={() => {}}
        directorOpen={false}
        onDirector={() => {}}
      />
      <Library
        projects={projects}
        loading={loading}
        error={error}
        onOpen={onOpen}
        onArchive={onArchive}
        onCreated={onCreated}
        onRetry={onRetry}
        onSettings={onSettings}
      />
    </div>
  );
}
