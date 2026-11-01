import { useState } from "react";
import { api } from "../../api";
import { Button } from "../../ui";
import { ChoiceRow, NumberRow, Row, Section, usePanel, type Option } from "./fields";
import {
  modelsFor,
  priceWords,
  recommendedPictures,
  recommendedRoles,
  recommendedVoices,
  type CatalogModel,
} from "./settingsModel";

function Reset({ patch }: { patch: Record<string, unknown> }) {
  const { save } = usePanel();
  return (
    <Button size="small" variant="quiet" onClick={() => void save(patch)}>
      Reset to recommended
    </Button>
  );
}

function modelOptions(models: CatalogModel[], blank?: string): Option[] {
  return [
    ...(blank !== undefined ? [{ value: "", label: blank }] : []),
    ...models.map((model) => ({ value: model.id, label: model.label || model.id })),
  ];
}

const THINKING: Option[] = [
  { value: "off", label: "Off" },
  { value: "low", label: "Low" },
  { value: "medium", label: "Medium" },
  { value: "high", label: "High" },
];

const ROLES = [
  { id: "writer", label: "Writer", hint: "Story, storyboard and images.", needs: ["text"] },
  { id: "editor", label: "Editor", hint: "Track and film, the cut.", needs: ["text"] },
  { id: "critic", label: "Critic", hint: "Reviews a cut, so it must be able to see pictures.", needs: ["text", "vision"] },
];

export function RolesTab() {
  const { catalog, settings } = usePanel();
  const roles = settings.roles;
  const textProviders = catalog.providers
    .filter((provider) => provider.unlocks.includes("writer"))
    .map((provider) => ({ value: provider.id, label: provider.label }));
  return (
    <>
      <Section
        title="Who answers"
        note={`${catalog.notes.direct_path} ${catalog.notes.thinking}`}
        action={<Reset patch={recommendedRoles(catalog)} />}
      >
        {ROLES.map((role) => {
          const provider = roles[role.id as "writer"].provider;
          return (
            <div key={role.id} className="settings-role">
              <ChoiceRow
                path={`roles.${role.id}.provider`}
                label={`${role.label} provider`}
                hint={role.hint}
                options={textProviders}
              />
              <ChoiceRow
                path={`roles.${role.id}.model`}
                label={`${role.label} model`}
                options={modelOptions(modelsFor(catalog, role.needs, provider))}
              />
              <ChoiceRow
                path={`roles.${role.id}.thinking`}
                label={`${role.label} thinking`}
                options={THINKING}
                free={false}
              />
              <NumberRow
                path={`roles.${role.id}.max_tokens_per_turn`}
                label={`${role.label} tokens per turn`}
                hint="0 means no limit of your own."
                step="100"
              />
            </div>
          );
        })}
      </Section>
      <Section title="Narrator" note={catalog.notes.narrator}>
        <ChoiceRow
          path="roles.narrator.model"
          label="Narrator model"
          options={modelOptions(modelsFor(catalog, ["speech"]))}
          extra={<span className="settings-price">{priceWords(catalog.models.find((m) => m.id === roles.narrator.model))}</span>}
        />
      </Section>
    </>
  );
}

function Sample({ voice }: { voice: string }) {
  const [message, setMessage] = useState<string | null>(null);
  const [src, setSrc] = useState<string | null>(null);
  return (
    <span className="settings-row">
      <Button
        size="small"
        onClick={() => {
          setMessage(null);
          api
            .testVoice(voice)
            .then((result) => {
              if (result.preview_url) setSrc(result.preview_url);
              else setMessage(result.message);
            })
            .catch((caught) => setMessage(String(caught)));
        }}
      >
        Play sample
      </Button>
      {src && <audio src={src} autoPlay controls />}
      {message && <span className="settings-muted">{message}</span>}
    </span>
  );
}

export function VoicesTab() {
  const { catalog, settings, save } = usePanel();
  const voices = settings.voices;
  const offered = catalog.voices.filter((voice) => voice.provider === voices.provider);
  const providers = catalog.providers
    .filter((provider) => provider.unlocks.includes("voices"))
    .map((provider) => ({ value: provider.id, label: provider.label }));
  const toggle = (id: string) =>
    void save({
      voices: {
        favourites: voices.favourites.includes(id)
          ? voices.favourites.filter((item) => item !== id)
          : [...voices.favourites, id],
      },
    });
  return (
    <Section
      title="The narrator's voice"
      note={catalog.notes.narrator}
      action={<Reset patch={recommendedVoices(catalog)} />}
    >
      <ChoiceRow path="voices.provider" label="Voice provider" options={providers} />
      <ChoiceRow
        path="voices.default_voice"
        label="Default voice"
        options={offered.map((voice) => ({ value: voice.id, label: `${voice.label} (${voice.id})` }))}
        extra={<Sample voice={voices.default_voice} />}
      />
      <Row label="Favourites" hint="Offered first when a film chooses a voice.">
        <span className="settings-chips" role="group" aria-label="Favourite voices">
          {offered.map((voice) => (
            <button
              key={voice.id}
              type="button"
              aria-pressed={voices.favourites.includes(voice.id)}
              onClick={() => toggle(voice.id)}
            >
              {voice.label}
            </button>
          ))}
        </span>
      </Row>
    </Section>
  );
}

export function PicturesTab() {
  const { catalog, settings } = usePanel();
  const pictures = settings.pictures;
  const looks = settings.style_presets ?? [];
  const images = modelsFor(catalog, ["image"]);
  const stills = catalog.models.find((model) => model.recommended.includes("pictures"));
  return (
    <>
      <Section
        title="Models"
        note={catalog.notes.pictures}
        action={<Reset patch={recommendedPictures(looks.map((look) => look.id))} />}
      >
        {looks.map((look) => (
          <ChoiceRow
            key={look.id}
            path={`pictures.image_model_by_look.${look.id}`}
            label={`Stills for ${look.name}`}
            options={modelOptions(images, "The look's own model")}
            extra={
              <span className="settings-price">
                {priceWords(images.find((m) => m.id === pictures.image_model_by_look[look.id]) ?? stills)}
              </span>
            }
          />
        ))}
        <ChoiceRow
          path="pictures.video_model"
          label="Video model"
          options={modelOptions(modelsFor(catalog, ["video"]), "None yet")}
          extra={<span className="settings-price">{priceWords(catalog.models.find((m) => m.id === pictures.video_model))}</span>}
        />
        <ChoiceRow
          path="pictures.upscaler"
          label="Upscaler"
          options={modelOptions(modelsFor(catalog, ["upscale"]), "None yet")}
          extra={<span className="settings-price">{priceWords(catalog.models.find((m) => m.id === pictures.upscaler))}</span>}
        />
      </Section>
      <Section title="What is set aside before buying">
        <NumberRow
          path="pictures.reserve_usd_per_still"
          label="Reserve per still"
          hint="The price shown on every picture button."
          min="0.01"
          max="10"
          step="0.01"
        />
        <NumberRow
          path="pictures.reserve_usd_per_clip_second"
          label="Reserve per clip second"
          hint="Stored for when clips arrive."
          min="0.01"
          max="10"
          step="0.01"
        />
      </Section>
    </>
  );
}
