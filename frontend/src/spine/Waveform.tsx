import type { Music } from "../api";
import { sectionColor } from "./wave";

const WAVE_WIDTH = 1000;
const WAVE_HEIGHT = 52;

/** The measured level as bars over a faint tint per section. */
export function Waveform({
  bars,
  sections,
  duration,
  shift = 0,
  clip = null,
}: {
  bars: { value: number; section: number; start: number }[];
  sections: NonNullable<Music["sections"]>;
  duration: number;
  /** Seconds the film starts into the drawn source, for an excerpt. */
  shift?: number;
  clip?: { start: number; end: number } | null;
}) {
  return (
        <svg
          className="spine-wave"
          viewBox={`0 0 ${WAVE_WIDTH} ${WAVE_HEIGHT}`}
          preserveAspectRatio="none"
          aria-hidden="true"
        >
          {sections.map((section, index) => {
            const start = shift + Number(section.start);
            const end = shift + Number(section.end);
            if (clip && (end <= clip.start || start >= clip.end)) {
              return null;
            }
            return (
              <rect
                key={`${section.start}-${index}`}
                x={(start / duration) * WAVE_WIDTH}
                y="0"
                width={((end - start) / duration) * WAVE_WIDTH}
                height={WAVE_HEIGHT}
                fill={sectionColor(index)}
                opacity=".14"
              />
            );
          })}
          {bars.map((bar, index) => {
            const width = WAVE_WIDTH / Math.max(1, bars.length);
            const height = Math.max(1.5, bar.value * (WAVE_HEIGHT - 6));
            return (
              <rect
                key={`${bar.start}-${index}`}
                x={(index * width).toFixed(2)}
                y={((WAVE_HEIGHT - height) / 2).toFixed(2)}
                width={Math.max(0.6, width - 0.8).toFixed(2)}
                height={height.toFixed(2)}
                fill={sectionColor(bar.section)}
              />
            );
          })}
        </svg>
  );
}
