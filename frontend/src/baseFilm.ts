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
