import { AbsoluteFill, Audio } from "remotion";
import { Film, type BaseFilmInput } from "./baseFilm";

export type PreviewProps = {
  input: BaseFilmInput;
  audio: string | null;
};

/**
 * The live Player runs the renderer's own Film composition (BaseFilm plus the
 * planned titles) and timing module. Only the image source and the audio
 * element differ from the MP4 composition.
 */
export function LivePreview({ input, audio }: PreviewProps) {
  return (
    <AbsoluteFill style={{ backgroundColor: "#000" }}>
      {audio && <Audio src={audio} />}
      <Film input={input} />
    </AbsoluteFill>
  );
}
