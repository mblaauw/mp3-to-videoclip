import { useEffect, useState } from "react";
import { api } from "../../api";
import { Button } from "../../ui";
import { SaveState, type SaveStatus } from "../../ui/SaveState";
import { Row, Section, TextRow, usePanel } from "./fields";
import { patchAt, type CatalogProvider } from "./settingsModel";

/** Where each provider's key sits in the settings. */
const KEY_PATH: Record<string, string> = {
  openai: "keys.openai",
  direct: "keys.openai_compatible.key",
  "opencode-go": "keys.opencode_go",
  anthropic: "keys.anthropic",
  gemini: "keys.gemini",
  runware: "keys.runware",
  elevenlabs: "keys.elevenlabs",
};

/** The list of keys a new one can be added to, including ones not listed until set. */
const ALWAYS_ADDABLE = [{ id: "elevenlabs", label: "ElevenLabs", unlocks: ["voices"] }];

function KeyRow({
  id,
  label,
  stored,
  provider,
}: {
  id: string;
  label: string;
  stored: boolean;
  provider?: CatalogProvider;
}) {
  const { save, settled, reloadCatalog } = usePanel();
  const [value, setValue] = useState("");
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [word, setWord] = useState<{ ok: boolean; message: string } | null>(
    provider?.ready.reachable ?? null,
  );
  const [busy, setBusy] = useState<"test" | "refresh" | null>(null);
  const [listed, setListed] = useState<string | null>(null);
  useEffect(() => setWord(provider?.ready.reachable ?? null), [provider?.ready.reachable]);

  const commit = async () => {
    const key = value.trim();
    if (!key) return;
    setStatus("saving");
    try {
      await save(patchAt(KEY_PATH[id], key));
      setValue("");
      setStatus("saved");
      await reloadCatalog();
    } catch {
      setStatus("error");
    }
  };
  const test = async () => {
    setBusy("test");
    setWord(null);
    try {
      await settled();
      const result = await api.testProvider(id);
      setWord(result);
    } catch (caught) {
      setWord({ ok: false, message: String(caught) });
    } finally {
      setBusy(null);
    }
  };
  const refresh = async () => {
    setBusy("refresh");
    setListed(null);
    try {
      await settled();
      const report = await api.refreshCatalog(id);
      setListed(`${report.listed} listed, ${report.added.length} new`);
      await reloadCatalog();
    } catch (caught) {
      setListed(String(caught));
    } finally {
      setBusy(null);
    }
  };

  return (
    <Row
      id={`key-${id}`}
      label={`${label} key`}
      hint={provider ? `Unlocks: ${provider.ready.unlocks.join(", ")}` : undefined}
      extra={
        <span className="settings-row">
          <SaveState status={status} onRetry={() => void commit()} />
          <Button size="small" disabled={busy !== null} onClick={() => void test()}>
            {busy === "test" ? "Checking…" : "Test"}
          </Button>
          {provider?.lists_models && (
            <Button size="small" variant="quiet" disabled={busy !== null} onClick={() => void refresh()}>
              {busy === "refresh" ? "Refreshing…" : "Refresh list"}
            </Button>
          )}
          {word && <span className={word.ok ? "settings-good" : "settings-bad"}>{word.message}</span>}
          {listed && <span className="settings-muted">{listed}</span>}
        </span>
      }
    >
      <input
        id={`key-${id}`}
        type="password"
        value={value}
        autoComplete="off"
        placeholder={stored ? "Stored. Leave empty to keep it" : "Paste the key"}
        onChange={(event) => setValue(event.target.value)}
        onBlur={() => void commit()}
      />
    </Row>
  );
}

export function KeysTab() {
  const { catalog, settings } = usePanel();
  const has: Record<string, boolean> = {
    openai: settings.has_openai_key === true,
    direct: settings.has_openai_compatible_key === true,
    "opencode-go": settings.has_opencode_go_key === true,
    anthropic: settings.has_anthropic_key === true,
    gemini: settings.has_gemini_key === true,
    runware: settings.has_runware_key === true,
    elevenlabs: settings.has_elevenlabs_key === true,
  };
  const listed = new Set(catalog.providers.map((provider) => provider.id));
  return (
    <>
      <Section title="Keys" note="Stored on this computer only, and never shown again. A test makes a free call.">
        {catalog.providers.map((provider) => (
          <KeyRow key={provider.id} id={provider.id} label={provider.label} stored={has[provider.id]} provider={provider} />
        ))}
        {ALWAYS_ADDABLE.filter((item) => !listed.has(item.id)).map((item) => (
          <KeyRow key={item.id} id={item.id} label={item.label} stored={has[item.id]} />
        ))}
      </Section>
      <Section title="Your own endpoint" note={catalog.notes.direct_path}>
        <TextRow path="keys.openai_compatible.base_url" label="Address" placeholder="https://…/v1" />
        <TextRow path="keys.openai_compatible.model" label="A model it offers" hint="Used when a role names this endpoint with no model of its own." />
      </Section>
    </>
  );
}
