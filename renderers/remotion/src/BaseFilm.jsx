// The still-film composition shared by the renderer and the Studio Player.
//
// The renderer reaches this through src/index.jsx with local static-file names;
// the Player passes the same shot objects plus an `src` URL for each still. Both
// use src/timing.mjs, so spans, dissolves, camera moves, grades and transitions
// are the same pure functions of the frame in the browser and in the MP4.
import React from "react";
import {
  AbsoluteFill,
  Img,
  Sequence,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import * as timing from "./timing.mjs";

export const DEFAULT_FONT_STACK = '"Avenir Next", "Helvetica Neue", Arial, sans-serif';

export function ShotLayer({span, localFrame, reveal, width, height}) {
  const grade = timing.postEffectsStyle(span.post_effects);
  const camera = timing.cameraAtFrame(span, localFrame);
  const rect = timing.layerRect({width, height, ...camera});
  return (
    <AbsoluteFill
      style={{
        opacity: reveal.opacity,
        overflow: "hidden",
        clipPath: reveal.clipPath ?? undefined,
      }}
    >
      <div
        style={{
          position: "absolute",
          width: rect.width,
          height: rect.height,
          left: rect.left,
          top: rect.top,
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            filter: grade.filter === "none" ? undefined : grade.filter,
          }}
        >
          {span.src === null ? (
            // A missing selected still keeps its allocation and shows the same
            // placeholder marking as a preview render, without loading a file.
            <AbsoluteFill style={{backgroundColor: "#101014"}} />
          ) : (
            <Img
              src={span.src ?? staticFile(span.image)}
              style={{width: "100%", height: "100%", objectFit: "cover", display: "block"}}
            />
          )}
        </div>
      </div>
      {grade.vignette > 0 ? (
        <AbsoluteFill
          style={{
            background:
              "radial-gradient(ellipse at center," +
              ` rgba(0,0,0,0) 42%, rgba(0,0,0,${grade.vignette}) 100%)`,
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
}

export function BaseFilm({input}) {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const shots = input?.shots ?? [];
  const previewBanner = input?.preview_banner === true;
  const placeholders = new Set(input?.preview_placeholders ?? []);
  const brandPlate = input?.brand_plate ?? null;
  const brandSeconds = Number(
    input?.brand_duration_frames ? input.brand_duration_frames / fps : timing.BRAND_PLATE_SECONDS,
  );
  const brandFrames = Math.round(brandSeconds * fps);

  const {spans} = React.useMemo(() => timing.allocateSpans(shots), [shots]);
  const layers = timing.visibleLayers(spans, frame);
  const topLayer = layers.length > 0 ? layers[layers.length - 1] : null;
  const placeholderId =
    topLayer && placeholders.has(spans[topLayer.index].id) ? spans[topLayer.index].id : null;

  let brandAlpha = 0;
  if (brandPlate && frame < brandFrames) {
    const fadeFrames = Math.max(1, Math.round(timing.BRAND_PLATE_FADE_SECONDS * fps));
    brandAlpha =
      timing.rampAt(frame, 0, fadeFrames) *
      (1 - timing.rampAt(frame, brandFrames - fadeFrames, brandFrames));
  }

  return (
    <AbsoluteFill style={{backgroundColor: "#000"}}>
      {layers.map((layer, position) => {
        const span = spans[layer.index];
        const isTop = position === layers.length - 1;
        // The incoming plate reveals itself over the still-opaque outgoing plate.
        const reveal = isTop
          ? timing.transitionStyle(spans[layer.index - 1]?.transition ?? "fade", layer.progress)
          : {kind: "fade", clipPath: null, opacity: 1};
        return (
          <Sequence
            key={span.id}
            from={span.start_frame}
            durationInFrames={span.duration_frames + span.handle}
          >
            <ShotLayer
              span={span}
              localFrame={layer.localFrame}
              reveal={reveal}
              width={width}
              height={height}
            />
          </Sequence>
        );
      })}
      {brandAlpha > 0 ? (
        <AbsoluteFill style={{opacity: brandAlpha}}>
          <Img src={brandPlate} style={{width: "100%", height: "100%", objectFit: "cover"}} />
        </AbsoluteFill>
      ) : null}
      {placeholderId ? (
        <AbsoluteFill
          style={{
            alignItems: "center",
            justifyContent: "center",
            fontFamily: DEFAULT_FONT_STACK,
          }}
        >
          <div
            style={{
              padding: "18px 34px",
              background: "rgba(8,8,10,0.62)",
              color: "#FFD34D",
              fontSize: Math.round(height * 0.035),
              fontWeight: 800,
              letterSpacing: 3,
              textAlign: "center",
              border: "2px dashed rgba(255,211,77,0.75)",
            }}
          >
            PLACEHOLDER — NOT FINAL
            <div style={{fontSize: Math.round(height * 0.022), fontWeight: 500, letterSpacing: 2}}>
              {placeholderId}
            </div>
          </div>
        </AbsoluteFill>
      ) : null}
      {previewBanner ? (
        <AbsoluteFill
          style={{
            alignItems: "center",
            justifyContent: "flex-start",
            fontFamily: DEFAULT_FONT_STACK,
            pointerEvents: "none",
          }}
        >
          <div
            style={{
              marginTop: Math.round(height * 0.03),
              padding: "10px 26px",
              background: "linear-gradient(to bottom, rgba(8,8,10,0.72), rgba(8,8,10,0))",
              color: "#FFD34D",
              fontSize: Math.round(height * 0.028),
              fontWeight: 800,
              letterSpacing: 5,
            }}
          >
            PREVIEW — NOT FINAL
          </div>
        </AbsoluteFill>
      ) : null}
    </AbsoluteFill>
  );
}
