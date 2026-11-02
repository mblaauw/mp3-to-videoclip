import { type ProjectSummary } from "../api";
import { ArchiveFilm } from "./ArchiveFilm";
import { goLibrary } from "./route";
import { TopBar } from "./TopBar";

export function ArchiveShell({
  project,
  onBack,
  onSettings,
}: {
  project: ProjectSummary;
  onBack: () => void;
  onSettings: () => void;
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
      <ArchiveFilm project={project} onBack={onBack} />
    </div>
  );
}
