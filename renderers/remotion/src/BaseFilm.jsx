// The still-film composition shared by the renderer and the Studio Player.
//
// The renderer reaches this through src/index.jsx with local static-file names;
// the Player passes the same shot objects plus an `src` URL for each still. Both
// use src/timing.mjs, so spans, dissolves, camera moves, grades, edit
// transitions, accents, split layouts and text animation are the same pure
// functions of the frame in the browser and in the MP4.
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

function paneSource(pane) {
  return pane.src ?? (pane.image ? staticFile(pane.image) : null);
}

function SplitPanes({panes, layout, width, height}) {
  const rects = timing.splitLayout(panes.length, layout);
  return (
    <AbsoluteFill style={{backgroundColor: "#000"}}>
      {panes.map((pane, index) => {
        const rect = rects[index];
        const source = paneSource(pane);
        const crop = pane.crop ?? {};
        const zoom = Number(crop.zoom ?? 1);
        return (
          <div
            key={pane.shot_id ?? index}
            style={{
              position: "absolute",
              left: rect.left * width,
              top: rect.top * height,
              width: rect.width * width,
              height: rect.height * height,
              overflow: "hidden",
              background: "#101014",
            }}
          >
            {source ? (
              <Img
                src={source}
                style={{
                  width: "100%",
                  height: "100%",
                  objectFit: "cover",
                  objectPosition: `${Number(crop.x ?? 0.5) * 100}% ${Number(crop.y ?? 0.5) * 100}%`,
                  transform: zoom === 1 ? undefined : `scale(${zoom})`,
                  display: "block",
                }}
              />
            ) : null}
          </div>
        );
      })}
    </AbsoluteFill>
  );
}

function textBox(style, width, height) {
  const base = {
    position: "absolute",
    fontFamily: DEFAULT_FONT_STACK,
    color: "#FFFFFF",
    textShadow: "0 2px 18px rgba(0,0,0,0.55)",
  };
  if (style === "title") {
    return {
      ...base,
      left: width * 0.1,
      right: width * 0.1,
      top: height * 0.38,
      textAlign: "center",
      fontSize: height * 0.082,
      fontWeight: 900,
      letterSpacing: "0.02em",
      lineHeight: 1.02,
      textTransform: "uppercase",
    };
  }
  if (style === "card") {
    return {
      ...base,
      left: width * 0.12,
      right: width * 0.12,
      top: height * 0.32,
      textAlign: "center",
      fontSize: height * 0.062,
      fontWeight: 800,
      lineHeight: 1.12,
    };
  }
  if (style === "lyric") {
    return {
      ...base,
      left: width * 0.1,
      right: width * 0.1,
      bottom: height * 0.14,
      textAlign: "center",
      fontSize: height * 0.048,
      fontWeight: 700,
      fontStyle: "italic",
      lineHeight: 1.15,
    };
  }
  if (style === "lower_third") {
    return {
      ...base,
      left: width * 0.08,
      bottom: height * 0.18,
      maxWidth: width * 0.7,
      padding: `${height * 0.016}px ${width * 0.024}px`,
      background: "rgba(8,8,10,0.68)",
      borderLeft: `${Math.max(3, width * 0.006)}px solid #D8FF3E`,
      fontSize: height * 0.036,
      fontWeight: 700,
      letterSpacing: "0.04em",
      lineHeight: 1.14,
    };
  }
  return {
    ...base,
    left: width * 0.08,
    bottom: height * 0.1,
    maxWidth: width * 0.84,
    padding: `${height * 0.014}px ${width * 0.02}px`,
    background: "rgba(8,8,10,0.55)",
    fontSize: height * 0.042,
    fontWeight: 800,
    letterSpacing: "0.08em",
    lineHeight: 1.08,
    textTransform: "uppercase",
  };
}

function TextLayer({item, absoluteFrame, width, height}) {
  if (absoluteFrame < item.in_frame || absoluteFrame >= item.out_frame) return null;
  const duration = Math.max(item.out_frame - item.in_frame, 1);
  const progress = (absoluteFrame - item.in_frame) / duration;
  const box = textBox(item.style, width, height);
  const words = item.text.split(/\s+/).filter(Boolean);
  if (item.animation === "kinetic_words") {
    return (
      <div style={box}>
        {words.map((word, index) => {
          const state = timing.textAnimationStyle(
            "kinetic_words",
            progress,
            index,
            words.length,
          );
          return (
            <span
              key={`${item.id}-${index}`}
              style={{
                display: "inline-block",
                opacity: state.opacity,
                transform: state.transform ?? undefined,
                marginRight: "0.28em",
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
    );
  }
  const state = timing.textAnimationStyle(item.animation, progress);
  const visible =
    item.animation === "type_on"
      ? item.text.slice(0, Math.max(0, Math.ceil(item.text.length * state.reveal)))
      : item.text;
  return (
    <div
      style={{
        ...box,
        opacity: state.opacity,
        transform: state.transform ?? undefined,
      }}
    >
      {visible}
    </div>
  );
}

// One tile of noise, drawn once and only moved per frame, which is what keeps it cheap.
const GRAIN_IMAGE = `url("data:image/svg+xml,${encodeURIComponent(
  `<svg xmlns='http://www.w3.org/2000/svg' width='${timing.GRAIN_TILE}' height='${timing.GRAIN_TILE}'>` +
    "<filter id='g'><feTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='2' seed='7' stitchTiles='stitch'/>" +
    "<feColorMatrix type='saturate' values='0'/></filter>" +
    "<rect width='100%' height='100%' filter='url(#g)'/></svg>",
)}")`;

const WHIP_BLUR_ID = "whip-blur";

export function ShotLayer({span, localFrame, absoluteFrame, reveal, width, height, whipBlur = 0}) {
  const grade = timing.gradeStyle(span.grade, span.post_effects);
  const accent = timing.accentState(span.edit?.accents, absoluteFrame);
  const camera = timing.cameraAtFrame(span, localFrame);
  const rect = timing.layerRect({
    width,
    height,
    ...camera,
    zoom: camera.zoom * accent.punch,
  });
  const {fps} = useVideoConfig();
  const look = timing.lookState(span.grade?.look, localFrame, span.id, width, height, fps);
  const panes = Array.isArray(span.split_panes) ? span.split_panes : [];
  const splitLayout = span.edit?.split_layout ?? "row";
  return (
    <AbsoluteFill
      style={{
        opacity: reveal.opacity,
        overflow: "hidden",
        clipPath: reveal.clipPath ?? undefined,
        transform: reveal.transform ?? undefined,
        filter: reveal.filter ?? (whipBlur > 0 ? `url(#${WHIP_BLUR_ID})` : undefined),
      }}
    >
      <div
        style={{
          position: "absolute",
          width: rect.width,
          height: rect.height,
          left: rect.left,
          top: rect.top,
          transform: look?.transform,
        }}
      >
        <div
          style={{
            position: "absolute",
            inset: 0,
            filter: grade.filter === "none" ? undefined : grade.filter,
          }}
        >
          {panes.length >= 2 ? (
            <SplitPanes panes={panes} layout={splitLayout} width={rect.width} height={rect.height} />
          ) : span.src === null ? (
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
        {grade.tint ? (
          <AbsoluteFill
            style={{
              background: grade.tint,
              mixBlendMode: "soft-light",
              pointerEvents: "none",
            }}
          />
        ) : null}
        {grade.vignette > 0 ? (
          <AbsoluteFill
            style={{
              background:
                "radial-gradient(ellipse at center," +
                ` rgba(0,0,0,0) 42%, rgba(0,0,0,${grade.vignette}) 100%)`,
            }}
          />
        ) : null}
      </div>
      {look && look.grainOpacity > 0 ? (
        <AbsoluteFill
          style={{
            backgroundImage: GRAIN_IMAGE,
            backgroundSize: `${timing.GRAIN_TILE}px ${timing.GRAIN_TILE}px`,
            backgroundPosition: `${look.grainX}px ${look.grainY}px`,
            mixBlendMode: "overlay",
            opacity: look.grainOpacity,
            pointerEvents: "none",
          }}
        />
      ) : null}
      {(span.edit?.text ?? []).map((item) => (
        <TextLayer
          key={item.id}
          item={item}
          absoluteFrame={absoluteFrame}
          width={width}
          height={height}
        />
      ))}
      {accent.flash > 0 ? (
        <AbsoluteFill style={{backgroundColor: "#FFFFFF", opacity: accent.flash * 0.9}} />
      ) : null}
      {accent.leak > 0 ? (
        <AbsoluteFill
          style={{
            background:
              "linear-gradient(105deg, rgba(255,214,150,0) 30%, " +
              `rgba(255,177,92,${0.7 * accent.leak}) 58%, rgba(255,236,207,0) 82%)`,
            mixBlendMode: "screen",
          }}
        />
      ) : null}
    </AbsoluteFill>
  );
}

/**
 * The still film. `overlay` is drawn over the pictures and the brand plate but
 * under the placeholder and preview markings; Film passes the title layer here.
 */
export function BaseFilm({input, overlay = null}) {
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

  let incoming = {kind: "cut", opacity: 1, clipPath: null, transform: null, filter: null, black: 0, white: 0};
  if (topLayer && topLayer.index > 0) {
    const span = spans[topLayer.index];
    if (span.edit?.transition_in) {
      incoming = timing.editTransitionStyle(span.edit.transition_in, topLayer.progress);
    } else {
      const previous = spans[topLayer.index - 1];
      incoming = {
        ...timing.transitionStyle(previous.transition ?? "fade", topLayer.progress),
        transform: null,
        filter: null,
        black: 0,
        white: 0,
      };
    }
  }

  const whipBlur = (incoming.blurShare ?? 0) * width;

  return (
    <AbsoluteFill style={{backgroundColor: "#000"}}>
      {whipBlur > 0 ? (
        <svg style={{position: "absolute", width: 0, height: 0}} aria-hidden="true">
          <filter id={WHIP_BLUR_ID} x="-10%" width="120%">
            <feGaussianBlur stdDeviation={`${whipBlur.toFixed(2)} 0`} />
          </filter>
        </svg>
      ) : null}
      {layers.map((layer, position) => {
        const span = spans[layer.index];
        const isTop = position === layers.length - 1;
        const reveal = isTop
          ? incoming
          : {
              kind: "fade",
              clipPath: null,
              opacity: 1,
              transform: incoming.outgoingTransform ?? null,
              filter: null,
              black: 0,
              white: 0,
            };
        return (
          <Sequence
            key={span.id}
            from={span.start_frame}
            durationInFrames={span.duration_frames + span.handle}
          >
            <ShotLayer
              span={span}
              localFrame={layer.localFrame}
              absoluteFrame={frame}
              reveal={reveal}
              width={width}
              height={height}
              whipBlur={whipBlur}
            />
          </Sequence>
        );
      })}
      {incoming.black > 0 ? (
        <AbsoluteFill style={{backgroundColor: "#000", opacity: incoming.black}} />
      ) : null}
      {incoming.white > 0 ? (
        <AbsoluteFill style={{backgroundColor: "#FFF", opacity: incoming.white}} />
      ) : null}
      {brandAlpha > 0 ? (
        <AbsoluteFill style={{opacity: brandAlpha}}>
          <Img src={brandPlate} style={{width: "100%", height: "100%", objectFit: "cover"}} />
        </AbsoluteFill>
      ) : null}
      {overlay}
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
