import { AbsoluteFill, Audio, Img, Sequence, interpolate, useCurrentFrame } from "remotion";

export type PreviewShot = {
  id: string;
  start_frame: number;
  duration_frames: number;
  dissolve_frames: number;
  camera: string;
  image: string | null;
};

export type PreviewProps = {
  shots: PreviewShot[];
  audio: string | null;
};

function Shot({ shot, fadeIn }: { shot: PreviewShot; fadeIn: number }) {
  const frame = useCurrentFrame();
  const progress =
    shot.duration_frames > 1 ? Math.min(1, frame / (shot.duration_frames - 1)) : 0;
  const zoom =
    shot.camera === "zoom_in"
      ? 1 + 0.06 * progress
      : shot.camera === "zoom_out"
        ? 1.06 - 0.06 * progress
        : 1;
  const shift =
    shot.camera === "pan_left" ? -2 * progress : shot.camera === "pan_right" ? 2 * progress : 0;
  const opacity = fadeIn
    ? interpolate(frame, [0, fadeIn], [0, 1], { extrapolateRight: "clamp" })
    : 1;
  return (
    <AbsoluteFill style={{ backgroundColor: "#000", opacity, overflow: "hidden" }}>
      {shot.image ? (
        <Img
          src={shot.image}
          style={{
            width: "100%",
            height: "100%",
            objectFit: "cover",
            transform: `scale(${zoom}) translateX(${shift}%)`,
          }}
        />
      ) : (
        <AbsoluteFill
          style={{
            display: "grid",
            placeItems: "center",
            color: "#8fa0ae",
            fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
          }}
        >
          <div style={{ textAlign: "center" }}>
            <div style={{ fontSize: 13 }}>{shot.id}</div>
            <div style={{ fontSize: 11, marginTop: 6 }}>no still yet</div>
          </div>
        </AbsoluteFill>
      )}
    </AbsoluteFill>
  );
}

/**
 * The Player spike: the exact shot order and durations, the selected stills and
 * the source audio. Camera motion is a local approximation; the Remotion render
 * remains the authority for transitions and final timing.
 */
export function LivePreview({ shots, audio }: PreviewProps) {
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {audio && <Audio src={audio} />}
      {shots.map((shot, index) => (
        <Sequence
          key={shot.id}
          from={shot.start_frame}
          durationInFrames={shot.duration_frames + shot.dissolve_frames}
          name={shot.id}
        >
          <Shot shot={shot} fadeIn={index === 0 ? 0 : shots[index - 1].dissolve_frames} />
        </Sequence>
      ))}
    </AbsoluteFill>
  );
}
