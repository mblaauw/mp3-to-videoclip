// Remotion compositions for the mp3-to-videoclip renderer module.
//
// Two compositions, both driven purely by input props:
//   "Base"     -> the still film (shots, cameras, dissolves, wipes, grade)
//   "Graphics" -> one local overlay element (intro, identity, role card, lockup, caption)
//
// Every animated value is a function of the current frame. There are no CSS
// transitions/animations, no clocks, no randomness and no second editorial
// timeline: the shot list and the graphics spec arrive fully resolved.
import React from "react";
import {Composition, registerRoot} from "remotion";

import {BaseFilm} from "./BaseFilm.jsx";
import {GraphicsFrame} from "./Titles.jsx";

// --------------------------------------------------------------------------- //
// registration
// --------------------------------------------------------------------------- //
function metadataFor(kind) {
  return ({props}) => {
    const width = Number(props?.width);
    const height = Number(props?.height);
    const fps = Number(props?.fps);
    const frames = Number(props?.frames);
    if (![width, height, fps, frames].every((value) => Number.isInteger(value) && value > 0)) {
      throw new Error(
        `${kind} composition needs integer width, height, fps and frames in its input props`,
      );
    }
    return {
      width,
      height,
      fps,
      durationInFrames: frames,
      defaultCodec: kind === "graphics" ? "prores" : "h264",
      defaultVideoImageFormat: "png",
      defaultPixelFormat: kind === "graphics" ? "yuva444p10le" : "yuv420p",
      defaultProResProfile: kind === "graphics" ? "4444" : undefined,
    };
  };
}

const DEFAULT_PROPS = {kind: "base", width: 1920, height: 1080, fps: 24, frames: 1, input: {}};

const Root = () => (
  <>
    <Composition
      id="Base"
      component={BaseFilm}
      width={DEFAULT_PROPS.width}
      height={DEFAULT_PROPS.height}
      fps={DEFAULT_PROPS.fps}
      durationInFrames={DEFAULT_PROPS.frames}
      defaultProps={{...DEFAULT_PROPS, kind: "base"}}
      calculateMetadata={metadataFor("base")}
    />
    <Composition
      id="Graphics"
      component={GraphicsFrame}
      width={DEFAULT_PROPS.width}
      height={DEFAULT_PROPS.height}
      fps={DEFAULT_PROPS.fps}
      durationInFrames={DEFAULT_PROPS.frames}
      defaultProps={{...DEFAULT_PROPS, kind: "graphics"}}
      calculateMetadata={metadataFor("graphics")}
    />
  </>
);

registerRoot(Root);
