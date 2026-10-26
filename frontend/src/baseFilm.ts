import type { ComponentType } from "react";

// The renderer composition is plain JSX shared by the MP4 renderer and the
// Studio Player. Vite bundles it from the repository; TypeScript gets the typed
// surface below because the renderer is not part of the frontend's src root.
// @ts-ignore - shared renderer source, not a frontend module with a .d.ts
import { BaseFilm as RendererBaseFilm } from "../../renderers/remotion/src/BaseFilm.jsx";

export type CameraFraming = {
  zoom: number;
  x: number;
  y: number;
};

export type CameraKeyframe = CameraFraming & { frame: number };

export type EditTransition = {
  type:
    | "cut"
    | "fade"
    | "wipe_left"
    | "wipe_right"
    | "dip_to_black"
    | "dip_to_white"
    | "whip_pan"
    | "push"
    | "slide";
  frames: number;
  direction?: "left" | "right" | "up" | "down" | null;
  reason?: string;
};

export type EditMotion = {
  type: "hold" | "push_in" | "pull_back" | "pan_left" | "pan_right";
  from: number;
  to: number;
  easing: "linear" | "smoothstep";
  anchor: [number, number];
  reason?: string;
};

export type EditAccent = {
  frame: number;
  type: "punch_in" | "flash" | "light_leak";
  amount?: number;
  duration_frames?: number;
  reason?: string;
};

export type EditText = {
  id: string;
  style: "super" | "title" | "lower_third" | "lyric" | "card";
  text: string;
  in_frame: number;
  out_frame: number;
  animation: "fade" | "type_on" | "slide_up" | "pop" | "kinetic_words";
  reason?: string;
};

export type EditShot = {
  shot_id: string;
  start_frame: number;
  duration_frames: number;
  motion: EditMotion;
  transition_in: EditTransition;
  split_layout?: "row" | "column" | "grid" | null;
  accents: EditAccent[];
  text: EditText[];
};

export type Grade = {
  preset: "neutral" | "warm-night" | "clean-day" | "monochrome" | "vivid" | "film-fade";
  strength: number;
  overrides?: PreviewShot["post_effects"];
};

export type SplitPane = {
  shot_id: string;
  crop?: { zoom?: number; x?: number; y?: number };
  src?: string | null;
  image?: string;
};

export type PreviewShot = {
  id: string;
  image: string;
  src: string | null;
  still_current: boolean;
  start_frame: number;
  duration_frames: number;
  dissolve_frames: number;
  camera: string;
  camera_path?: {
    start?: CameraFraming;
    end?: CameraFraming;
    easing?: "linear" | "smoothstep";
  } | null;
  camera_keyframes?: CameraKeyframe[] | null;
  post_effects?: {
    contrast?: number;
    saturation?: number;
    brightness?: number;
    vignette?: number;
  } | null;
  transition?: "fade" | "wipe_left" | "wipe_right" | null;
  edit?: EditShot | null;
  grade?: Grade | null;
  split_panes?: SplitPane[] | null;
};

export type BaseFilmInput = {
  shots: PreviewShot[];
  preview_banner?: boolean;
  preview_placeholders?: string[];
  brand_plate?: string | null;
  brand_duration_frames?: number;
};

export type BaseFilmProps = { input: BaseFilmInput };

export const BaseFilm = RendererBaseFilm as ComponentType<BaseFilmProps>;
