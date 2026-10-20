// Remotion compositions for the mp3-to-videoclip renderer module.
//
// Two compositions, both driven purely by input props:
//   "Base"     -> the still film (shots, cameras, dissolves, wipes, grade)
//   "Graphics" -> one local overlay element (intro, identity, role card, lockup, caption)
//
// Every animated value is a function of the current frame. There are no CSS
// transitions/animations, no clocks, no randomness and no second editorial
// timeline: the shot list and the graphics spec arrive fully resolved.
import React, {useEffect, useState} from "react";
import {
  AbsoluteFill,
  Composition,
  Img,
  Sequence,
  continueRender,
  delayRender,
  registerRoot,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from "remotion";

import * as timing from "./timing.mjs";
import {CompactGraphics} from "./CompactGraphics.jsx";
import {validateCompactLayout} from "./compact.mjs";

const DEFAULT_FONT_STACK = '"Avenir Next", "Helvetica Neue", Arial, sans-serif';
const LOCAL_FONT_FAMILY = "IdentityLocal";

const DEFAULT_PALETTE = {
  night: "#0B0710",
  ink: "#F4F1F7",
  accent: "#FF3D8B",
  secondary: "#7B4DFF",
};

// --------------------------------------------------------------------------- //
// small helpers
// --------------------------------------------------------------------------- //
function hexToRgb(hex, fallback) {
  const value = typeof hex === "string" ? hex.trim().replace(/^#/, "") : "";
  if (!/^[0-9a-fA-F]{6}$/.test(value)) return fallback;
  return [
    parseInt(value.slice(0, 2), 16),
    parseInt(value.slice(2, 4), 16),
    parseInt(value.slice(4, 6), 16),
  ];
}

function resolvePalette(palette) {
  const source = palette && typeof palette === "object" ? palette : {};
  return {
    night: source.night ?? DEFAULT_PALETTE.night,
    ink: source.ink ?? DEFAULT_PALETTE.ink,
    accent: source.accent ?? DEFAULT_PALETTE.accent,
    secondary: source.secondary ?? DEFAULT_PALETTE.secondary,
  };
}

/** A soft full-width vertical band: no hard top/bottom edge can cut a face. */
function softBand(rgb, opacity) {
  const [r, g, b] = rgb;
  return (
    "linear-gradient(to bottom," +
    ` rgba(${r},${g},${b},0) 6%,` +
    ` rgba(${r},${g},${b},${opacity}) 26%,` +
    ` rgba(${r},${g},${b},${opacity}) 74%,` +
    ` rgba(${r},${g},${b},0) 96%)`
  );
}

/** A soft left-to-right gradient for caption backing, instead of a hard box. */
function softFade(rgb, opacity) {
  const [r, g, b] = rgb;
  return (
    "linear-gradient(to right," +
    ` rgba(${r},${g},${b},${opacity}) 0%,` +
    ` rgba(${r},${g},${b},${opacity * 0.75}) 55%,` +
    ` rgba(${r},${g},${b},0) 100%)`
  );
}

/**
 * Optional local font as a `data:` URL. The bytes come from the caller; the
 * component only serves them. Never a remote font, never a CDN.
 */
function useLocalFont(font) {
  const [handle] = useState(() => (font ? delayRender("local identity font") : null));
  useEffect(() => {
    if (!font) return undefined;
    const style = document.createElement("style");
    style.setAttribute("data-identity-font", "1");
    style.textContent =
      `@font-face{font-family:'${LOCAL_FONT_FAMILY}';src:url(${font});` +
      "font-display:block;font-weight:100 900;}";
    document.head.appendChild(style);
    let released = false;
    const release = () => {
      if (!released) {
        released = true;
        continueRender(handle);
      }
    };
    const load = document.fonts?.load
      ? document.fonts.load(`700 100px ${LOCAL_FONT_FAMILY}`)
      : Promise.resolve();
    Promise.resolve(load)
      .then(() => (document.fonts?.ready ? document.fonts.ready : undefined))
      .then(release)
      .catch(release);
    return () => {
      style.remove();
    };
  }, [font, handle]);
  return font ? LOCAL_FONT_FAMILY : null;
}

function fontFamily(family) {
  return family ? `${family}, ${DEFAULT_FONT_STACK}` : DEFAULT_FONT_STACK;
}

/** One absolutely positioned text layer: fade + a modest translate. */
function Line({
  top,
  size,
  colour,
  alpha = 1,
  weight = 400,
  spacing = 0,
  align = "center",
  left = 0,
  right = 0,
  family,
  lineHeight = 1.15,
  lift = 12,
  children,
}) {
  return (
    <div
      style={{
        position: "absolute",
        top,
        left,
        right,
        textAlign: align,
        color: colour,
        fontFamily: family ?? DEFAULT_FONT_STACK,
        fontSize: size,
        fontWeight: weight,
        letterSpacing: spacing,
        lineHeight,
        opacity: alpha,
        transform: `translateY(calc(-50% + ${(1 - Math.min(alpha, 1)) * lift}px))`,
        whiteSpace: "pre",
      }}
    >
      {children}
    </div>
  );
}

/** A thin accent rule whose width grows with the frame, never a clock. */
function Rule({top, width, thickness, alpha, colour, centre = true, left}) {
  return (
    <div
      style={{
        position: "absolute",
        top,
        left: centre ? "50%" : left,
        width,
        height: thickness,
        background: colour,
        opacity: alpha,
        transformOrigin: centre ? "center" : "left",
        transform: centre
          ? `translateX(-50%) scaleX(${timing.clamp01(alpha)})`
          : `scaleX(${timing.clamp01(alpha)})`,
      }}
    />
  );
}

/**
 * The supplied identity artwork, unchanged.
 *
 * A vector/SVG logo is drawn exactly as received. A rasterised reference is
 * screen-blended so its black background field is ignored rather than shipped as
 * a black box; the artwork's own pixels are otherwise untouched.
 */
function IdentityMark({src, height, top, left, right, centre, alpha, width = "auto"}) {
  const svg = typeof src === "string" && src.startsWith("data:image/svg");
  return (
    <div
      style={{
        position: "absolute",
        top,
        left: centre ? "50%" : left,
        right,
        height,
        width: centre ? height : width,
        opacity: alpha,
        transform: centre
          ? `translate(-50%, calc(-50% + ${(1 - Math.min(alpha, 1)) * 10}px))`
          : `translateY(calc(-50% + ${(1 - Math.min(alpha, 1)) * 10}px))`,
        mixBlendMode: svg ? "normal" : "screen",
      }}
    >
      <Img src={src} style={{width: "100%", height: "100%", objectFit: "contain"}} />
    </div>
  );
}

/** The widely spaced joint wordmark with an accent diamond separator. */
function Wordmark({names, size, colour, separatorColour, alpha, spacing, top, family, weight = 800}) {
  const {parts} = timing.splitNames(names);
  return (
    <Line
      top={top}
      size={size}
      colour={colour}
      alpha={alpha}
      weight={weight}
      spacing={spacing}
      family={family}
    >
      {parts.map((part, index) => (
        <React.Fragment key={`${part}-${index}`}>
          {index > 0 ? (
            <span style={{color: separatorColour, margin: `0 ${size * 0.45}px`}}>◆</span>
          ) : null}
          {part}
        </React.Fragment>
      ))}
    </Line>
  );
}

// --------------------------------------------------------------------------- //
// base film
// --------------------------------------------------------------------------- //
function ShotLayer({span, localFrame, reveal, width, height}) {
  const grade = timing.postEffectsStyle(span.post_effects);
  const camera = timing.cameraAtFrame(span, localFrame);
  const rect = timing.layerRect({width, height, ...camera});
  return (
    <AbsoluteFill style={{opacity: reveal.opacity, overflow: "hidden", clipPath: reveal.clipPath ?? undefined}}>
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
          <Img
            src={staticFile(span.image)}
            style={{width: "100%", height: "100%", objectFit: "cover", display: "block"}}
          />
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

function BaseFilm({input}) {
  const frame = useCurrentFrame();
  const {width, height, fps} = useVideoConfig();
  const shots = input?.shots ?? [];
  const previewBanner = input?.preview_banner === true;
  const placeholders = new Set(input?.preview_placeholders ?? []);
  const brandPlate = input?.brand_plate ?? null;
  const brandSeconds = Number(input?.brand_duration_frames ? input.brand_duration_frames / fps : timing.BRAND_PLATE_SECONDS);
  const brandFrames = Math.round(brandSeconds * fps);

  const {spans} = React.useMemo(() => timing.allocateSpans(shots), [shots]);
  const layers = timing.visibleLayers(spans, frame);
  const topLayer = layers.length > 0 ? layers[layers.length - 1] : null;
  const placeholderId = topLayer && placeholders.has(spans[topLayer.index].id)
    ? spans[topLayer.index].id
    : null;

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

// --------------------------------------------------------------------------- //
// graphics overlay parts
// --------------------------------------------------------------------------- //
function IntroPart({spec, intro, palette, logo, family, t}) {
  const {width, height} = useVideoConfig();
  const seconds = Number(spec?.intro_seconds ?? timing.INTRO_REFERENCE_SECONDS);
  const phases = timing.introPhasesAt(t, seconds);
  const ink = palette.ink;
  const rgb = hexToRgb(palette.night, [11, 7, 16]);
  const mini = Array.isArray(intro.mini_credits) ? intro.mini_credits.slice(0, 2) : [];
  const notes = Array.isArray(intro.notes) ? intro.notes.slice(0, 2) : [];
  const ruleAlpha = Math.max(phases.names, phases.title);

  return (
    <AbsoluteFill>
      <AbsoluteFill style={{background: softBand(rgb, 0.62), opacity: phases.scrim}} />
      {logo ? (
        <IdentityMark
          src={logo}
          height={height * 0.19}
          top={height * 0.225}
          centre
          alpha={phases.mark}
        />
      ) : null}
      <Wordmark
        names={intro.names}
        top={height * 0.385}
        size={height * 0.036}
        colour={ink}
        separatorColour={palette.accent}
        alpha={phases.names}
        weight={600}
        spacing={height * 0.012}
        family={family}
      />
      <Rule
        top={height * 0.428}
        width={width * 0.084}
        thickness={Math.max(2, height * 0.0035)}
        alpha={ruleAlpha}
        colour={palette.accent}
      />
      <Line
        top={height * 0.512}
        size={height * 0.098}
        colour={ink}
        alpha={phases.title}
        weight={800}
        spacing={height * 0.002}
        family={family}
      >
        {intro.title}
      </Line>
      {intro.subtitle ? (
        <Line
          top={height * 0.612}
          size={height * 0.031}
          colour={ink}
          alpha={phases.title}
          weight={600}
          spacing={height * 0.0015}
          family={family}
        >
          {intro.subtitle}
        </Line>
      ) : null}
      {intro.time_line ? (
        <Line
          top={height * 0.678}
          size={height * 0.038}
          colour={palette.accent}
          alpha={phases.time}
          weight={800}
          spacing={height * 0.002}
          family={family}
        >
          {intro.time_line}
        </Line>
      ) : null}
      {mini.map((entry, index) => {
        const alpha = phases[index === 0 ? "mini_credits_1" : "mini_credits_2"];
        const roleTop = height * (index === 0 ? 0.734 : 0.808);
        return (
          <React.Fragment key={`mini-${index}`}>
            <Line
              top={roleTop}
              size={height * 0.02}
              colour={palette.accent}
              alpha={alpha * 0.92}
              weight={700}
              spacing={height * 0.002}
              family={family}
              lift={8}
            >
              {entry[0]}
            </Line>
            <Line
              top={roleTop + height * 0.034}
              size={height * 0.036}
              colour={ink}
              alpha={alpha}
              weight={600}
              family={family}
              lift={8}
            >
              {entry[1]}
            </Line>
          </React.Fragment>
        );
      })}
      {intro.tagline ? (
        <Line
          top={height * 0.902}
          size={height * 0.026}
          colour={ink}
          alpha={phases.tagline * 0.9}
          weight={400}
          family={family}
        >
          {intro.tagline}
        </Line>
      ) : null}
      {notes.map((note, index) => (
        <Line
          key={`note-${index}`}
          top={height * (index === 0 ? 0.938 : 0.962)}
          size={height * 0.019}
          colour={ink}
          alpha={phases[index === 0 ? "notes_1" : "notes_2"] * 0.8}
          family={family}
        >
          {note}
        </Line>
      ))}
    </AbsoluteFill>
  );
}

function IdentityPart({spec, intro, palette, logo, family, t, seconds}) {
  const {width, height} = useVideoConfig();
  const alpha = timing.graphicsAlpha("identity", t, seconds);
  const rgb = hexToRgb(palette.night, [11, 7, 16]);
  return (
    <AbsoluteFill style={{opacity: alpha}}>
      <AbsoluteFill style={{background: softBand(rgb, 0.58)}} />
      {logo ? (
        <IdentityMark src={logo} height={height * 0.144} top={height * 0.352} centre alpha={1} />
      ) : null}
      <Line
        top={height * 0.483}
        size={height * 0.042}
        colour={palette.ink}
        alpha={1}
        weight={800}
        spacing={height * 0.011}
        family={family}
      >
        {intro.names}
      </Line>
      <Rule
        top={height * 0.53}
        width={width * 0.084}
        thickness={Math.max(2, height * 0.0032)}
        alpha={1}
        colour={palette.accent}
      />
      {intro.tagline ? (
        <Line
          top={height * 0.585}
          size={height * 0.025}
          colour={palette.ink}
          alpha={0.85}
          family={family}
        >
          {intro.tagline}
        </Line>
      ) : null}
    </AbsoluteFill>
  );
}

function CardPart({spec, palette, logo, family, t, seconds}) {
  const {width, height} = useVideoConfig();
  const alpha = timing.graphicsAlpha("card", t, seconds);
  const rgb = hexToRgb(palette.night, [11, 7, 16]);
  const [role, name] = spec.card;
  const x = width * timing.SAFE_MARGIN;
  return (
    <AbsoluteFill style={{opacity: alpha}}>
      <AbsoluteFill style={{background: softBand(rgb, 0.5)}} />
      {logo ? (
        // The monogram header sits in the upper area; the role block stays in the
        // lower-left area, so the two can never overlap.
        <IdentityMark
          src={logo}
          height={height * 0.11}
          top={height * 0.11}
          left={x}
          width={width * 0.34}
          alpha={1}
        />
      ) : null}
      <Line
        top={height * 0.6}
        size={height * 0.022}
        colour={palette.accent}
        alpha={1}
        weight={700}
        align="left"
        left={x}
        right={0}
        spacing={height * 0.003}
        family={family}
      >
        {role}
      </Line>
      <Rule
        top={height * 0.655}
        width={width * 0.22}
        thickness={Math.max(2, height * 0.0032)}
        alpha={1}
        colour={palette.accent}
        centre={false}
        left={x}
      />
      <Line
        top={height * 0.7}
        size={height * 0.058}
        colour={palette.ink}
        alpha={1}
        weight={800}
        align="left"
        left={x}
        right={0}
        family={family}
      >
        {name}
      </Line>
    </AbsoluteFill>
  );
}

function LockupPart({spec, palette, logo, family, t, seconds}) {
  const {width, height} = useVideoConfig();
  const alpha = timing.graphicsAlpha("lockup", t, seconds);
  const rgb = hexToRgb(palette.night, [11, 7, 16]);
  const line = spec?.credits?.lockup ?? spec?.lockup ?? "";
  return (
    <AbsoluteFill style={{opacity: alpha}}>
      <AbsoluteFill style={{background: softBand(rgb, 0.6)}} />
      {logo ? (
        <IdentityMark src={logo} height={height * 0.104} top={height * 0.4} centre alpha={1} />
      ) : null}
      <Line
        top={height * 0.512}
        size={height * 0.038}
        colour={palette.ink}
        alpha={1}
        weight={800}
        spacing={height * 0.002}
        family={family}
      >
        {line}
      </Line>
      <Rule
        top={height * 0.56}
        width={width * 0.06}
        thickness={Math.max(2, height * 0.0028)}
        alpha={1}
        colour={palette.accent}
      />
      <Line
        top={height * 0.612}
        size={height * 0.027}
        colour={palette.ink}
        alpha={0.9}
        weight={600}
        family={family}
      >
        {spec?.intro?.names ?? ""}
      </Line>
      {spec?.intro?.title ? (
        <Line
          top={height * 0.668}
          size={height * 0.028}
          colour={palette.ink}
          alpha={0.8}
          family={family}
        >
          {spec.intro.title}
        </Line>
      ) : null}
    </AbsoluteFill>
  );
}

function CaptionPart({part, palette, family, t, seconds}) {
  const {width, height} = useVideoConfig();
  const caption = part.caption;
  const alpha = timing.graphicsAlpha("caption", t, seconds);
  const rgb = hexToRgb(palette.night, [11, 7, 16]);
  const pad = height * 0.014;
  const barWidth = width * 0.006;
  const size = height * 0.032;
  const boxHeight = size * 1.45 + pad;
  const bottom = height * 0.1;
  const x0 = width * 0.085;
  const textLeft = x0 + barWidth + pad;
  return (
    <AbsoluteFill style={{opacity: alpha}}>
      <div
        style={{
          position: "absolute",
          left: x0,
          bottom: bottom - pad,
          width: width * 0.62,
          height: boxHeight,
          background: softFade(rgb, 0.82),
        }}
      />
      <div
        style={{
          position: "absolute",
          left: x0,
          bottom: bottom - pad,
          width: barWidth,
          height: boxHeight,
          background: palette.accent,
        }}
      />
      <div
        style={{
          position: "absolute",
          left: textLeft,
          bottom: bottom - pad + boxHeight / 2,
          transform: "translateY(50%)",
          color: palette.ink,
          fontFamily: family,
          fontSize: size,
          fontWeight: 700,
          letterSpacing: height * 0.002,
          whiteSpace: "pre",
        }}
      >
        {caption.text}
      </div>
    </AbsoluteFill>
  );
}

function GraphicsFrame({input}) {
  const frame = useCurrentFrame();
  const {fps, durationInFrames} = useVideoConfig();
  const part = input?.part;
  const spec = input?.spec ?? {};
  const intro = input?.intro ?? spec.intro ?? {};
  const palette = resolvePalette(input?.palette ?? spec.palette);
  const logo = input?.logo ?? null;
  const family = useLocalFont(input?.font ?? null);
  const seconds = (part?.frames ?? durationInFrames) / fps;
  const t = frame / fps;
  const resolvedFamily = fontFamily(family);

  if (!part) throw new Error("graphics input.part is required");
  if (validateCompactLayout(spec.layout, part)) {
    const resolvedPart = part.kind === "card" ? {...part, card:part.card ?? spec?.credits?.cards?.[part.index ?? 0]} : part;
    return <CompactGraphics part={resolvedPart} spec={spec} intro={intro} palette={palette}
      logo={logo} family={resolvedFamily}/>;
  }
  if (part.kind === "intro") {
    return (
      <IntroPart
        spec={spec}
        intro={intro}
        palette={palette}
        logo={logo}
        family={resolvedFamily}
        t={t}
      />
    );
  }
  if (part.kind === "identity") {
    return (
      <IdentityPart
        spec={spec}
        intro={intro}
        palette={palette}
        logo={logo}
        family={resolvedFamily}
        t={t}
        seconds={seconds}
      />
    );
  }
  if (part.kind === "card") {
    const card = part.card ?? spec?.credits?.cards?.[part.index ?? 0];
    return (
      <CardPart
        spec={{card}}
        palette={palette}
        logo={logo}
        family={resolvedFamily}
        t={t}
        seconds={seconds}
      />
    );
  }
  if (part.kind === "lockup") {
    return (
      <LockupPart
        spec={spec}
        palette={palette}
        logo={logo}
        family={resolvedFamily}
        t={t}
        seconds={seconds}
      />
    );
  }
  if (part.kind === "caption") {
    return (
      <CaptionPart
        part={part}
        palette={palette}
        family={resolvedFamily}
        t={t}
        seconds={seconds}
      />
    );
  }
  throw new Error(`unsupported graphics part kind ${JSON.stringify(part.kind)}`);
}

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
