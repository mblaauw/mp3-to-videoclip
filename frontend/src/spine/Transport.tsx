import { useEffect, useMemo, useRef } from "react";
import type { Music, Storyboard } from "../api";
import { LoopIcon, NextIcon, PauseIcon, PlayIcon, PrevIcon, VolumeIcon } from "../ui/icons";
import { usePlayer } from "./player";
import { clock, sectionName } from "./wave";

/** Play, position, shot/section readout, loop, speed and volume, with their keys. */
export function Transport({
  board,
  music,
  shownDuration,
  excerptMode = false,
}: {
  board: Storyboard | null;
  music: Music | null;
  shownDuration: number;
  excerptMode?: boolean;
}) {
  const player = usePlayer();
  const sections = music?.sections ?? [];
  const displayTime = player.time;
  const fps = board?.fps || 24;
  const shotAt = (seconds: number) =>
    board?.shots.find(
      (shot) =>
        seconds >= shot.start_frame / fps &&
        seconds < (shot.start_frame + shot.duration_frames) / fps,
    ) || null;
  const sectionIndexAt = (seconds: number) =>
    sections.findIndex(
      (section) => seconds >= Number(section.start) && seconds < Number(section.end),
    );
  const nowShot = shotAt(player.time);
  const nowSectionIndex = sectionIndexAt(player.time);
  const nowSection = nowSectionIndex >= 0 ? sections[nowSectionIndex] : null;

  const stops = useMemo(() => {
    if (board?.shots.length) return board.shots.map((shot) => shot.start_frame / (board.fps || 24));
    return (music?.sections ?? []).map((section) => Number(section.start));
  }, [board, music]);

  const jump = (direction: -1 | 1) => {
    const now = player.current();
    if (!stops.length) {
      player.seekBy(direction * 5);
      return;
    }
    if (direction > 0) {
      const next = stops.find((value) => value > now + 0.05);
      if (next !== undefined) player.seek(next);
      return;
    }
    // Back: to the start of this shot, or the previous one when already there.
    const earlier = stops.filter((value) => value < now - 0.75);
    player.seek(earlier.length ? earlier[earlier.length - 1] : 0);
  };

  const cycleLoop = () => {
    const now = player.current();
    const mode = player.loop?.label.startsWith("Shot")
      ? "shot"
      : player.loop?.label.startsWith("Section")
        ? "section"
        : player.loop
          ? "other"
          : "off";
    const shot = shotAt(now);
    const sectionIndex = sectionIndexAt(now);
    if (mode === "off" && shot) {
      player.setLoop({
        start: shot.start_frame / fps,
        end: (shot.start_frame + shot.duration_frames) / fps,
        label: `Shot ${shot.id}`,
      });
      return;
    }
    if ((mode === "off" || mode === "shot") && sectionIndex >= 0) {
      const section = sections[sectionIndex];
      player.setLoop({
        start: Number(section.start),
        end: Number(section.end),
        label: `Section ${sectionName(section, sectionIndex)}`,
      });
      return;
    }
    player.setLoop(null);
  };

  const cycleRate = () => {
    const rates = [1, 0.75, 0.5];
    const index = rates.indexOf(player.rate);
    player.setRate(rates[(index + 1) % rates.length]);
  };

  const keys = useRef({ jump, cycleLoop });
  keys.current = { jump, cycleLoop };
  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (target?.closest("input, textarea, select, [contenteditable='true'], [role='dialog']")) {
        return;
      }
      if (event.key === "," || event.key === ".") {
        event.preventDefault();
        keys.current.jump(event.key === "," ? -1 : 1);
      } else if (event.key === "l" || event.key === "L") {
        event.preventDefault();
        keys.current.cycleLoop();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // A loop that no longer matches the board (a moved cut) is dropped.
  const { loop, setLoop } = player;
  useEffect(() => {
    if (loop && loop.end > shownDuration + 0.5) setLoop(null);
  }, [loop, setLoop, shownDuration]);

  return (
      <div className="spine-transport">
        <div className="spine-buttons">
          <button
            type="button"
            className="spine-btn"
            onClick={() => jump(-1)}
            aria-label={board ? "Previous shot" : "Previous section"}
            title={`${board ? "Previous shot" : "Previous section"} ( , )`}
          >
            <PrevIcon size={16} />
          </button>
          <button
            type="button"
            className="spine-play"
            onClick={player.toggle}
            aria-label={player.playing ? "Pause" : "Play"}
            title={`${player.playing ? "Pause" : "Play"} (Space)`}
          >
            {player.playing ? <PauseIcon /> : <PlayIcon />}
          </button>
          <button
            type="button"
            className="spine-btn"
            onClick={() => jump(1)}
            aria-label={board ? "Next shot" : "Next section"}
            title={`${board ? "Next shot" : "Next section"} ( . )`}
          >
            <NextIcon size={16} />
          </button>
        </div>
        <div className="spine-time">
          <b>{clock(displayTime)}</b> / {clock(shownDuration)}
          {excerptMode && <span className="spine-time-label"> excerpt</span>}
        </div>
        <div className="spine-now" aria-live="off">
          {nowShot ? <b>{nowShot.id}</b> : null}
          {nowSection ? (
            <span>{sectionName(nowSection, nowSectionIndex)}</span>
          ) : !nowShot ? (
            <span>{music ? "—" : "Not measured yet"}</span>
          ) : null}
        </div>
        <div className="spine-tools">
          <button
            type="button"
            className={`spine-chip ${player.loop ? "on" : ""}`}
            onClick={cycleLoop}
            aria-pressed={!!player.loop}
            title="Loop the shot, then the section, then off (L)"
          >
            <LoopIcon size={14} />
            <span>{player.loop ? player.loop.label.split(" ")[0] : "Loop"}</span>
          </button>
          <button
            type="button"
            className="spine-chip"
            onClick={cycleRate}
            title="Playback speed"
            aria-label={`Playback speed ${player.rate}×`}
          >
            {player.rate}×
          </button>
          <button
            type="button"
            className={`spine-chip icon ${player.muted ? "on" : ""}`}
            onClick={player.toggleMute}
            aria-pressed={player.muted}
            aria-label={player.muted ? "Unmute" : "Mute"}
            title={`${player.muted ? "Unmute" : "Mute"} (M)`}
          >
            <VolumeIcon size={14} muted={player.muted || player.volume === 0} />
          </button>
          <input
            className="spine-volume"
            type="range"
            min={0}
            max={1}
            step={0.05}
            value={player.muted ? 0 : player.volume}
            onChange={(event) => player.setVolume(Number(event.target.value))}
            aria-label="Volume"
          />
        </div>
      </div>
  );
}
