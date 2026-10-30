import { clock } from "../spine/wave";
import { LyricsPart } from "../track/LyricsPart";
import { SectionsPart } from "../track/SectionsPart";
import { useTrackData } from "../track/useTrackData";
import { ErrorState, LoadingState } from "../ui";

export function TrackStage({ slug }: { slug: string }) {
  const model = useTrackData(slug);
  const { data, error, modeSaving, setMode, load } = model;
  const instrumental = data?.music_mode === "instrumental";
  const tempo = data?.music?.estimated_tempo_bpm;

  return (
    <>
      <div className="track-facts">
        <h1>Track</h1>
        <span>{data ? clock(data.duration) : "—"}</span>
        <span>{tempo ? `about ${Math.round(tempo)} BPM` : "tempo not measured"}</span>
        <div className="ui-seg track-mode" role="group" aria-label="Music">
          <button
            type="button"
            aria-pressed={!instrumental}
            disabled={!data || modeSaving}
            onClick={() => void setMode("vocal")}
          >
            Vocals
          </button>
          <button
            type="button"
            aria-pressed={instrumental}
            disabled={!data || modeSaving}
            onClick={() => void setMode("instrumental")}
          >
            Instrumental
          </button>
        </div>
        {modeSaving && <span>Saving…</span>}
      </div>
      {error && (
        <ErrorState
          what={data ? "saving the track" : "reading the track"}
          error={error}
          compact={!!data}
          onRetry={data ? undefined : () => void load()}
        />
      )}
      {!data && !error && <LoadingState>Reading the song and its sections…</LoadingState>}
      {data && (
        <div className="track-room">
          <SectionsPart model={model} />
          <LyricsPart slug={slug} model={model} />
        </div>
      )}
    </>
  );
}
