import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, type Settings } from "../../api";
import { ErrorState, useFocusTrap } from "../../ui";
import { CloseIcon } from "../../ui/icons";
import { CostsTab, ComputerTab, NewFilmsTab } from "./FilmTabs";
import { KeysTab } from "./KeysTab";
import { PicturesTab, RolesTab, SoundsTab, VoicesTab } from "./ModelTabs";
import { PanelContext, type Panel } from "./fields";
import { missingForFilm, TABS, type Catalog, type Missing, type TabId } from "./settingsModel";

const CONTENT = {
  roles: RolesTab,
  voices: VoicesTab,
  pictures: PicturesTab,
  sounds: SoundsTab,
  keys: KeysTab,
  "new-films": NewFilmsTab,
  computer: ComputerTab,
  costs: CostsTab,
} satisfies Record<TabId, () => React.JSX.Element>;

/** Every model, voice, price, key and new-film default, saved field by field. */
export function SettingsPanel({ onClose, onSaved }: { onClose: () => void; onSaved: () => void }) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [catalog, setCatalog] = useState<Catalog | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<TabId>("roles");
  const [query, setQuery] = useState("");
  const [focusField, setFocusField] = useState<string | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  const saving = useRef<Promise<unknown>>(Promise.resolve());
  useFocusTrap(true, dialog);

  const reloadCatalog = useCallback(async () => {
    setCatalog((await api.settingsCatalog()) as Catalog);
  }, []);

  const load = useCallback(() => {
    setError(null);
    Promise.all([api.settings(), api.settingsCatalog()])
      .then(([value, listed]) => {
        setSettings(value);
        setCatalog(listed as Catalog);
      })
      .catch((caught) => setError(String(caught)));
  }, []);

  useEffect(load, [load]);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  useEffect(() => {
    if (!focusField) return;
    document.getElementById(focusField)?.focus();
    setFocusField(null);
  }, [focusField, tab]);

  const panel = useMemo<Panel | null>(
    () =>
      settings && catalog
        ? {
            settings,
            catalog,
            query,
            reloadCatalog,
            settled: () => saving.current,
            save: async (patch) => {
              const run = saving.current
                .catch(() => undefined)
                .then(() => api.saveSettings(patch))
                .then((value) => {
                  setSettings(value);
                  onSaved();
                });
              saving.current = run.catch(() => undefined);
              return run;
            },
          }
        : null,
    [settings, catalog, query, reloadCatalog, onSaved],
  );

  const missing = settings && catalog ? missingForFilm(settings, catalog.computer) : [];
  const goTo = (item: Missing) => {
    setQuery("");
    setTab(item.tab);
    setFocusField(item.field);
  };
  const Current = CONTENT[tab];

  return (
    <div
      className="settings-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="settings-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title" ref={dialog}>
        <header>
          <h2 id="settings-title">Settings</h2>
          {settings?.file && (
            <span className="settings-file" title={settings.file}>
              Saved as you go to {settings.file}
            </span>
          )}
          <input
            type="search"
            className="settings-search"
            aria-label="Search settings"
            placeholder="Search settings"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
          />
          <button type="button" className="icon-btn" aria-label="Close settings" onClick={onClose}>
            <CloseIcon />
          </button>
        </header>
        {!panel ? (
          error ? (
            <div className="settings-body">
              <ErrorState what="reading settings" error={error} onRetry={load} />
            </div>
          ) : (
            <div className="settings-loading">Reading settings…</div>
          )
        ) : (
          <div className="settings-columns">
            <nav className="settings-rail" aria-label="Settings sections">
              {TABS.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  aria-current={!query && tab === item.id ? "page" : undefined}
                  onClick={(event) => {
                    setQuery("");
                    setTab(item.id);
                    event.currentTarget.scrollIntoView({ block: "nearest", inline: "nearest" });
                  }}
                >
                  <span>{item.label}</span>
                  <small>{item.hint}</small>
                </button>
              ))}
            </nav>
            <div className="settings-body">
              <PanelContext.Provider value={panel}>
                {missing.length > 0 && !query && (
                  <section className="settings-missing" aria-label="What is missing to make a film">
                    <h3>What is missing to make a film</h3>
                    <ul>
                      {missing.map((item) => (
                        <li key={item.id}>
                          <button type="button" onClick={() => goTo(item)}>
                            {item.label}
                          </button>
                        </li>
                      ))}
                    </ul>
                  </section>
                )}
                {query ? (
                  <div className="settings-results">
                    {TABS.map((item) => {
                      const Found = CONTENT[item.id];
                      return <Found key={item.id} />;
                    })}
                  </div>
                ) : (
                  <Current key={tab} />
                )}
              </PanelContext.Provider>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
