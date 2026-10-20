import React, {useEffect, useRef, useState} from "react";
import {Img, cancelRender, continueRender, delayRender, useCurrentFrame, useVideoConfig} from "remotion";
import {compactIntroPhases, compactPanels} from "./compact.mjs";
import {splitNames} from "./timing.mjs";

// Typography uses local font metrics. Fail on overflow rather than clipping copy.
function Module({field, alpha, family, children}) {
  const {width, height} = useVideoConfig();
  const root = useRef(null);
  const [handle] = useState(() => delayRender("compact local typography bounds"));
  useEffect(() => {
    let cancelled = false;
    Promise.resolve(document.fonts?.ready).then(() => {
      if (cancelled) return;
      const host = root.current?.getBoundingClientRect();
      for (const node of root.current?.querySelectorAll("[data-compact-ink]") ?? []) {
        const box = node.getBoundingClientRect();
        if (box.left < host.left - 1 || box.top < host.top - 1 || box.right > host.right + 1 || box.bottom > host.bottom + 1) {
          throw new Error(`compact text/logo exceeds its reviewed field: ${node.textContent}`);
        }
      }
      continueRender(handle);
    }).catch((error) => { cancelRender(error); });
    return () => { cancelled = true; };
  }, [handle, family]);
  return <div ref={root} style={{position:"absolute", left:field[0]*width, top:field[1]*height,
    width:(field[2]-field[0])*width, height:(field[3]-field[1])*height,
    opacity:alpha, color:"inherit", fontFamily:family}}>{children}</div>;
}

function Words({x=12, y, size, alpha=1, colour, children, weight=700}) {
  const {height} = useVideoConfig();
  const s = height / 1080;
  return <span data-compact-ink style={{position:"absolute",left:x*s,top:y*s,fontSize:size*s,
    fontWeight:weight,lineHeight:1.15,whiteSpace:"pre",opacity:alpha,color:colour}}>{children}</span>;
}

function Names({names, size=30, colour, ...props}) {
  const {height} = useVideoConfig();
  const scale = height / 1080;
  return <Words {...props} size={size} colour={colour}>{splitNames(names).parts.map((name,i) =>
    <React.Fragment key={i}>{i>0 ? <span style={{display:"inline-block",width:size*.17*scale,height:size*.17*scale,
      background:colour,transform:"rotate(45deg)",margin:`0 ${size*.32*scale}px`,verticalAlign:"middle"}}/>:null}{name}</React.Fragment>
  )}</Words>;
}

function Mark({logo, width=92, y=8, alpha=1}) {
  const {height} = useVideoConfig();
  const s = height / 1080;
  return logo ? <Img data-compact-ink src={logo} style={{position:"absolute",left:12*s,top:y*s,
    width:width*s,height:width*90/156*s,opacity:alpha}}/> : null;
}

function JointLine({value, y, size=24, alpha=1, colour}) {
  // Preserve every word; a production suffix occupies its own line in narrow fields.
  const suffix = " PRODUCTION";
  const lines = value?.endsWith(suffix) ? [value.slice(0,-suffix.length), "PRODUCTION"] : [value ?? ""];
  return lines.map((line,i) => <Words key={i} y={y+i*(size*1.25)} size={size} alpha={alpha} colour={colour}>{line}</Words>);
}

export function CompactGraphics({part, spec, intro, palette, logo, family}) {
  const frame = useCurrentFrame();
  const {fps} = useVideoConfig();
  const {height} = useVideoConfig();
  const scale = height / 1080;
  const panels = compactPanels(spec.layout, part, frame, fps);
  const phases = compactIntroPhases(frame,fps,spec.intro_seconds ?? 25);
  const names = intro.names;
  const ink = palette.ink, gold = palette.accent;
  return <>{panels.map((panel,i) => <Module key={i} {...panel} family={family}>
    {part.kind === "caption" ? <div data-compact-ink style={{position:"absolute",left:12*scale,top:12*scale,
      padding:`${12*scale}px ${18*scale}px`,background:ink,color:palette.night,border:`${3*scale}px solid ${palette.night}`,
      fontSize:48*scale,fontWeight:800,lineHeight:1.15,whiteSpace:"pre"}}>{part.caption.text}</div>
    : part.kind === "intro" ? <>
      <Mark logo={logo} width={124} alpha={phases.mark}/>
      <Names names={names} x={160} y={14} size={32} alpha={phases.names} colour={gold}/>
      <Words y={97} size={68} alpha={phases.title} colour={ink}>{intro.title}</Words>
      {intro.subtitle ? <Words y={180} size={26} alpha={phases.title} colour={ink}>{intro.subtitle}</Words>:null}
      {intro.time_line ? <Words y={95} size={36} alpha={phases.time} colour={gold}>{intro.time_line}</Words>:null}
      {(intro.mini_credits ?? []).slice(0,2).map((entry,j) => <React.Fragment key={j}>
        <Words y={85} size={28} alpha={phases[`mini_credits_${j+1}`]} colour={gold}>{entry[0]}</Words>
        <Words y={130} size={52} alpha={phases[`mini_credits_${j+1}`]} colour={ink}>{entry[1]}</Words>
      </React.Fragment>)}
      <JointLine value={intro.tagline} y={194} size={26} alpha={phases.tagline} colour={ink}/>
      {(intro.notes ?? []).slice(0,2).map((note,j) => <Words key={j} y={25+j*34} size={24} alpha={phases[`notes_${j+1}`]} colour={ink}>{note}</Words>)}
    </> : part.kind === "identity" ? <>
      <Mark logo={logo} width={90} y={6}/><Names names={names} y={70} colour={gold}/>
      <JointLine value={intro.tagline} y={121} colour={ink}/>
    </> : part.kind === "card" ? <>
      <Mark logo={logo}/><Names names={names} x={130} y={12} size={28} colour={gold}/>
      <Words y={82} size={30} colour={gold}>{part.card[0]}</Words>
      <Words y={132} size={58} colour={ink}>{part.card[1]}</Words>
    </> : <>
      <Mark logo={logo} width={124}/><Names names={names} x={166} y={15} size={42} colour={gold}/>
      <Words y={103} size={36} colour={ink}>{spec.credits.lockup}</Words>
      <Words y={161} size={54} colour={ink}>{intro.title}</Words>
    </>}
  </Module>)}</>;
}
