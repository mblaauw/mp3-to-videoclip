import { useEffect, useState } from "react";
import { api, type SettingsCache, type SettingsCosts } from "../../api";
import { Button, ErrorState } from "../../ui";
import { SHOW_EDIT_FILE } from "../editFile";
import { ChoiceRow, ListRow, NumberRow, Row, Section, TextRow, ToggleRow, usePanel } from "./fields";
import { formatBytes, money, priceWords } from "./settingsModel";

const STORED_ONLY = "Stored for later; new films do not use this yet.";

export function NewFilmsTab() {
  const { settings } = usePanel();
  const kinds = (settings.kinds ?? []).map((kind) => ({ value: kind.id, label: kind.label }));
  const looks = [
    { value: "", label: "The kind's own look" },
    ...(settings.style_presets ?? []).map((look) => ({ value: look.id, label: look.name })),
  ];
  return (
    <>
      <Section title="New films start with">
        <ChoiceRow path="new_films.kind" label="Kind" options={kinds} free={false} />
        <NumberRow path="new_films.length_s" label="Length in seconds" hint="0 means the whole track, where the kind allows it." />
        <ChoiceRow path="new_films.look" label="Look" options={looks} free={false} />
        <NumberRow
          path="new_films.depth"
          label="Depth"
          hint="0 to 1. Only where the depth tools are set up; 0 starts flat. A film's look can change it."
          max="1"
          step="0.1"
        />
        <NumberRow path="new_films.budget_usd" label="Budget" hint="A starting cap in US dollars; you can raise it later." step="0.01" />
        <ChoiceRow
          path="new_films.aspect"
          label="Shape"
          hint="A new film can still choose the other shape."
          options={[
            { value: "16:9", label: "Landscape 16:9" },
            { value: "9:16", label: "Portrait 9:16" },
          ]}
          free={false}
        />
        <NumberRow path="new_films.fps" label="Frames per second" hint={STORED_ONLY} min="1" />
        <ToggleRow path="new_films.signature_package" label="Open and close a music video with titles" hint="With a name below it uses the 25/40 signature; without one, a short title. Each film can choose." />
        <ListRow path="new_films.credit_roles" label="Credit roles" hint={STORED_ONLY} placeholder="director, music, visuals" />
      </Section>
      <Section title="Brand kit" note="Used in the opening and closing graphics. A film keeps the names it was made with.">
        <TextRow path="new_films.brand.name" label="Artist or brand" />
        <TextRow path="new_films.brand.partner" label="Partner" />
        <TextRow path="new_films.brand.logo" label="Logo file" hint="An SVG on this computer, shown on short end cards." placeholder="/path/to/logo.svg" />
        <ListRow path="new_films.brand.palette" label="Palette" hint={STORED_ONLY} placeholder="#D9B36C, #1B1C1F" />
        <TextRow path="new_films.brand.font" label="Font" hint={STORED_ONLY} />
      </Section>
    </>
  );
}

const TOOLS: [string, string][] = [
  ["renderer", "Renderer"],
  ["chrome", "Chrome"],
  ["node", "Node"],
  ["ffmpeg", "FFmpeg"],
  ["ffprobe", "ffprobe"],
];

function CacheRow({ cache, onCleared }: { cache: SettingsCache; onCleared: () => void }) {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [word, setWord] = useState<string | null>(null);
  const clear = async () => {
    setBusy(true);
    setWord(null);
    try {
      const report = await api.clearCache(cache.name);
      setWord(
        `Cleared ${formatBytes(report.bytes)}.` +
          (report.busy.length ? ` Skipped while in use: ${report.busy.join(", ")}.` : ""),
      );
      onCleared();
    } catch (caught) {
      setWord(String(caught));
    } finally {
      setBusy(false);
      setConfirming(false);
    }
  };
  return (
    <Row
      label={cache.label}
      hint={cache.rebuilds}
      extra={
        <span className="settings-row">
          {word && <span className="settings-muted">{word}</span>}
          {cache.clearable &&
            (confirming ? (
              <>
                <Button size="small" disabled={busy} onClick={() => void clear()}>
                  {busy ? "Clearing…" : `Clear ${formatBytes(cache.bytes)}`}
                </Button>
                <Button size="small" variant="quiet" disabled={busy} onClick={() => setConfirming(false)}>
                  Keep
                </Button>
              </>
            ) : (
              <Button size="small" disabled={cache.bytes === 0} onClick={() => setConfirming(true)}>
                Clear
              </Button>
            ))}
        </span>
      }
    >
      <output className="settings-size">{formatBytes(cache.bytes)}</output>
    </Row>
  );
}

export function ComputerTab() {
  const { catalog, reloadCatalog } = usePanel();
  const [caches, setCaches] = useState<SettingsCache[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [installing, setInstalling] = useState(false);
  const [showFile, setShowFile] = useState(() => window.localStorage.getItem(SHOW_EDIT_FILE) === "1");
  const loadCaches = () =>
    api
      .settingsCaches()
      .then((value) => setCaches(value.caches))
      .catch((caught) => setError(String(caught)));
  useEffect(() => void loadCaches(), []);
  const install = async () => {
    setInstalling(true);
    setError(null);
    try {
      await api.installRenderer();
      await reloadCatalog();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setInstalling(false);
    }
  };
  const lyric = catalog.lyric_tools;
  return (
    <>
      <Section title="Tools">
        {TOOLS.map(([id, label]) => (
          <Row key={id} id={`tool-${id}`} label={label}>
            <output id={`tool-${id}`} tabIndex={-1} className={catalog.computer[id] ? "settings-good" : "settings-bad"}>
              {catalog.computer[id] ? "Ready" : "Missing"}
            </output>
          </Row>
        ))}
        {!catalog.computer.renderer && (
          <Row id="install-renderer" label="Install the renderer" hint="About a minute. Nothing is charged.">
            <Button id="install-renderer" size="small" disabled={installing} onClick={() => void install()}>
              {installing ? "Installing…" : "Install renderer"}
            </Button>
          </Row>
        )}
        <Row
          label="Lyric timing tools"
          hint={lyric.reason ?? `Set up from a film's Track page. About ${lyric.download_gb} GB.`}
        >
          <output className={lyric.ready ? "settings-good" : "settings-muted"}>
            {lyric.ready ? "Ready" : "Not set up"}
          </output>
        </Row>
        <Row
          label="Depth tools"
          hint={catalog.depth_tools.reason ?? `Set up from a film's look. About ${catalog.depth_tools.download_gb} GB.`}
        >
          <output className={catalog.depth_tools.ready ? "settings-good" : "settings-muted"}>
            {catalog.depth_tools.ready ? "Ready" : "Not set up"}
          </output>
        </Row>
      </Section>
      <Section title="Rendering">
        <NumberRow
          path="computer.render_workers"
          label="Browsers per render"
          hint="0 chooses from this computer's cores and free memory, at most 4. Each takes about 1.5 GB."
          max="8"
        />
      </Section>
      <Section
        title="Caches"
        note="Copies the app can rebuild. Stills, audio, renders, approvals and the journal are never touched. A damaged cache is refused rather than trusted, and frozen films are skipped."
      >
        {error && <ErrorState what="reading this computer" error={error} compact />}
        {caches?.map((cache) => <CacheRow key={cache.name} cache={cache} onCleared={() => void loadCaches()} />)}
      </Section>
      <Section title="Advanced">
        <Row label="Show the edit file on Film" hint="Read-only. Changes go through the Editor or the cut controls.">
          <input
            type="checkbox"
            checked={showFile}
            onChange={(event) => {
              setShowFile(event.target.checked);
              window.localStorage.setItem(SHOW_EDIT_FILE, event.target.checked ? "1" : "0");
            }}
          />
        </Row>
      </Section>
    </>
  );
}

function PriceRow({ id, label, price, stored }: { id: string; label: string; price: string; stored: string }) {
  const { save } = usePanel();
  const [value, setValue] = useState(stored);
  useEffect(() => setValue(stored), [stored]);
  return (
    <Row label={label} hint={price}>
      <input
        value={value}
        inputMode="decimal"
        placeholder="Your price, in USD"
        onChange={(event) => setValue(event.target.value)}
        onBlur={() => {
          if (value.trim() !== stored) void save({ prices: { [id]: value.trim() } });
        }}
      />
    </Row>
  );
}

export function CostsTab() {
  const { catalog, settings } = usePanel();
  const [costs, setCosts] = useState<SettingsCosts | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api
      .settingsCosts()
      .then(setCosts)
      .catch((caught) => setError(String(caught)));
  }, []);
  return (
    <>
      <Section title="What has been spent" note="Read from each film's journal, which keeps what the provider reported.">
        {error && <ErrorState what="reading costs" error={error} compact />}
        {costs && (
          <div className="settings-costs">
            <p>
              <b>{money(costs.spent_usd)}</b> spent, {money(costs.reserved_usd)} still reserved
              {costs.unpriced > 0 && `, ${costs.unpriced} tasks with no price`}.
            </p>
            <table>
              <caption>By kind</caption>
              <tbody>
                {costs.by_kind.map((row) => (
                  <tr key={row.kind}>
                    <th scope="row">{row.kind}</th>
                    <td>{money(row.spent_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <table>
              <caption>By film</caption>
              <tbody>
                {costs.films.map((film) => (
                  <tr key={film.slug}>
                    <th scope="row">{film.slug}</th>
                    <td>{film.unreadable ? "Journal unreadable" : money(film.spent_usd)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
      <Section
        title="Prices"
        note="A price here is a reservation input, not a bill; the journal keeps the provider's reported cost. Quotes do not read these yet."
      >
        {catalog.models.map((model) => (
          <PriceRow
            key={`${model.provider}/${model.id}`}
            id={model.id}
            label={model.label || model.id}
            price={priceWords(model)}
            stored={settings.prices[model.id] ?? ""}
          />
        ))}
      </Section>
    </>
  );
}
