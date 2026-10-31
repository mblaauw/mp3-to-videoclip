import { useEffect, useRef } from "react";
import { Player, type PlayerRef } from "@remotion/player";
import type { AnyZodObject } from "remotion";
import { LivePreview, type PreviewProps } from "./LivePreview";
import { preloadStills, stillSources } from "./film/preloadStills";

/** Kept in its own module so the Player and Remotion load only on the Film stage. */
export default function LivePlayer({
  input,
  audio,
  durationInFrames,
  fps,
  width,
  height,
  time,
  clock,
  playing,
}: PreviewProps & {
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  time?: number;
  /** The Studio audio clock; followed without re-rendering this component. */
  clock?: { get: () => number; subscribe: (listener: () => void) => () => void };
  playing?: boolean;
}) {
  const playerRef = useRef<PlayerRef>(null);
  const synced = time !== undefined || clock !== undefined;
  // Start from the playhead; later changes of position shouldn't restart the loading.
  const startFrame = useRef(Math.round((time ?? clock?.get() ?? 0) * fps));
  const sourcesKey = stillSources(input?.shots ?? [], startFrame.current).join("\n");

  useEffect(() => {
    if (!sourcesKey) return undefined;
    return preloadStills(sourcesKey.split("\n"));
  }, [sourcesKey]);

  useEffect(() => {
    if (time === undefined) return;
    const frame = Math.round((time || 0) * fps);
    const current = playerRef.current?.getCurrentFrame() ?? 0;
    if (Math.abs(current - frame) > 2) playerRef.current?.seekTo(frame);
  }, [fps, time]);

  useEffect(() => {
    if (!clock) return;
    const follow = () => {
      const frame = Math.round(clock.get() * fps);
      const current = playerRef.current?.getCurrentFrame() ?? 0;
      if (Math.abs(current - frame) > 2) playerRef.current?.seekTo(frame);
    };
    follow();
    return clock.subscribe(follow);
  }, [clock, fps]);

  useEffect(() => {
    if (!synced || playing === undefined) return;
    if (playing) playerRef.current?.play();
    else playerRef.current?.pause();
  }, [playing, synced]);

  return (
    <Player<AnyZodObject, PreviewProps>
      ref={playerRef}
      component={LivePreview}
      inputProps={{ input, audio }}
      durationInFrames={durationInFrames}
      fps={fps}
      compositionWidth={width}
      compositionHeight={height}
      controls={!synced}
      doubleClickToFullscreen
      acknowledgeRemotionLicense
      errorFallback={({ error }: { error: Error }) => (
        <div className="live-error" role="alert">
          The preview stopped on this frame: {error.message}
        </div>
      )}
      style={{ width: "100%" }}
    />
  );
}
