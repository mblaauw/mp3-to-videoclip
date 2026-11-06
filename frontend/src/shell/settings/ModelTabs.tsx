import { useState } from "react";
import { api } from "../../api";
import { Button } from "../../ui";
import { ChoiceRow, NumberRow, Row, Section, usePanel, type Option } from "./fields";
import {
  modelsFor,
  priceWords,
  recommendedPictures,
  recommendedRoles,
  recommendedSounds,
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
  {
    id: "writer",
    label: "Writer",
    hint: "Story, script, storyboard, images, the sound cues and the release copy.",
    needs: ["text"],
  },
  {
    id: "editor",
    label: "Editor",
    hint: "Track and film: the cut, and notes on every other stage.",
    needs: ["text"],
  },
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
        note={catalog.notes.thinking}
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
  const chosen = offered.find((voice) => voice.id === voices.default_voice);
  const elevenlabs = voices.provider === "elevenlabs";
  const elevenModels = modelsFor(catalog, ["speech"], "elevenlabs");
  const voiceModel = catalog.models.find((model) =>
    elevenlabs ? model.id === voices.elevenlabs_model : model.id === chosen?.model,
  );
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
      {elevenlabs ? (
        <ChoiceRow
          path="voices.elevenlabs_model"
          label="Spoken with"
          hint="Every ElevenLabs voice speaks with this model. Its characters count against the plan."
          options={modelOptions(elevenModels)}
          extra={<span className="settings-price">{priceWords(voiceModel)}</span>}
        />
      ) : (
        <Row label="Spoken by" hint={`The voice's own model. ${priceWords(voiceModel)}.`}>
          <output>{voiceModel ? voiceModel.label || voiceModel.id : chosen?.model || "The provider's model"}</output>
        </Row>
      )}
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
  const upscalers = modelsFor(catalog, ["upscale"]);
  const recommendedUpscaler =
    upscalers.find((model) => model.recommended.includes("upscaler")) ?? upscalers[0];
  const chosenUpscaler = upscalers.find((model) => model.id === pictures.upscaler);
  const oneStillModel = images.length <= 1;
  return (
    <>
      <Section
        title="Stills"
        note={
          oneStillModel
            ? "Every look makes its stills with the one still model the catalogue lists. A film keeps the model it was made with."
            : catalog.notes.pictures
        }
        action={oneStillModel ? undefined : <Reset patch={recommendedPictures(looks.map((look) => look.id))} />}
      >
        {oneStillModel ? (
          <Row label="Still model" hint={priceWords(images[0])}>
            <output>{images[0] ? images[0].label || images[0].id : "None listed"}</output>
          </Row>
        ) : (
          looks.map((look) => {
            const own = images.find((model) => model.id === look.model);
            const chosen = images.find((model) => model.id === pictures.image_model_by_look[look.id]);
            return (
              <ChoiceRow
                key={look.id}
                path={`pictures.image_model_by_look.${look.id}`}
                label={`Stills for ${look.name}`}
                options={modelOptions(images, own ? `${own.label || own.id} (the look's own)` : "The look's own model")}
                extra={<span className="settings-price">{priceWords(chosen ?? own)}</span>}
              />
            );
          })
        )}
      </Section>
      <Section title="Clips and upscaling" note="Used as soon as they are chosen.">
        <ChoiceRow
          path="pictures.video_model"
          label="Video model"
          hint="A clip starts from a shot's still. Clips need one."
          options={modelOptions(modelsFor(catalog, ["video"]), "Not chosen")}
          extra={<span className="settings-price">{priceWords(catalog.models.find((m) => m.id === pictures.video_model))}</span>}
        />
        <ChoiceRow
          path="pictures.upscaler"
          label="Upscaler"
          hint="Makes a chosen still larger before the film is rendered."
          options={modelOptions(
            upscalers,
            recommendedUpscaler ? `${recommendedUpscaler.label || recommendedUpscaler.id} (recommended)` : "None listed",
          )}
          extra={<span className="settings-price">{priceWords(chosenUpscaler ?? recommendedUpscaler)}</span>}
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
          hint="What a clip's quote sets aside for each second; the journal keeps what was charged."
          min="0.01"
          max="10"
          step="0.01"
        />
      </Section>
    </>
  );
}

export function SoundsTab() {
  const { catalog, settings } = usePanel();
  const sounds = settings.sounds;
  const beds = modelsFor(catalog, ["music"]);
  const effects = modelsFor(catalog, ["effects"]);
  return (
    <>
      <Section title="Models" note={catalog.notes.sounds} action={<Reset patch={recommendedSounds(catalog)} />}>
        <ChoiceRow
          path="sounds.music_model"
          label="Music model"
          hint="A bed or a piece of music under the film. Length follows the cue."
          options={modelOptions(beds)}
          extra={<span className="settings-price">{priceWords(beds.find((m) => m.id === sounds.music_model))}</span>}
        />
        <ChoiceRow
          path="sounds.effects_model"
          label="Effects model"
          hint="A sound at a frame or a line: a door, rain, a room."
          options={modelOptions(effects)}
          extra={<span className="settings-price">{priceWords(effects.find((m) => m.id === sounds.effects_model))}</span>}
        />
      </Section>
      <Section title="What is set aside before buying">
        <NumberRow
          path="sounds.reserve_usd_per_cue"
          label="Reserve per cue"
          hint="Only for a model with no catalogue price. A priced model reserves twice its quote, never under a cent."
          min="0.01"
          max="10"
          step="0.01"
        />
      </Section>
    </>
  );
}
