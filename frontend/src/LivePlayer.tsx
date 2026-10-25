import { Player } from "@remotion/player";
import type { AnyZodObject } from "remotion";
import { LivePreview, type PreviewProps } from "./LivePreview";

/** Kept in its own module so the Player and Remotion load only on the Film stage. */
export default function LivePlayer({
  shots,
  audio,
  durationInFrames,
  fps,
  width,
  height,
}: PreviewProps & {
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
}) {
  return (
    <Player<AnyZodObject, PreviewProps>
      component={LivePreview}
      inputProps={{ shots, audio }}
      durationInFrames={durationInFrames}
      fps={fps}
      compositionWidth={width}
      compositionHeight={height}
      controls
      doubleClickToFullscreen
      acknowledgeRemotionLicense
      style={{ width: "100%" }}
    />
  );
}
