import type { ReactNode, SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement> & { size?: number };

function svg({ size = 20, children, ...rest }: IconProps & { children: ReactNode }) {
  return (
    <svg
      viewBox="0 0 20 20"
      width={size}
      height={size}
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      aria-hidden="true"
      {...rest}
    >
      {children}
    </svg>
  );
}

export function MarkIcon({ size = 26 }: { size?: number }) {
  return (
    <svg viewBox="0 0 120 120" width={size} height={size} aria-hidden="true">
      <path
        d="M21 21H74L99 46V78A21 21 0 0 1 78 99H42A21 21 0 0 1 21 78V42A21 21 0 0 1 42 21Z"
        fill="none"
        stroke="currentColor"
        strokeWidth="8"
      />
      <path d="M74 21L99 46" stroke="var(--gold)" strokeWidth="8" />
      <path d="M48 44v32l28-16z" fill="currentColor" />
    </svg>
  );
}

export function PlayIcon({ size = 16 }: { size?: number }) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="currentColor" aria-hidden="true">
      <path d="M4 2.5v11l9-5.5z" />
    </svg>
  );
}

export function PauseIcon({ size = 16 }: { size?: number }) {
  return (
    <svg viewBox="0 0 16 16" width={size} height={size} fill="currentColor" aria-hidden="true">
      <rect x="3.5" y="2.5" width="3" height="11" />
      <rect x="9.5" y="2.5" width="3" height="11" />
    </svg>
  );
}

export function ChatIcon(props: IconProps) {
  return svg({ ...props, children: <path d="M3.5 4.5h13v9h-7l-4 3v-3h-2z" /> });
}

export function ClockIcon(props: IconProps) {
  return svg({
    ...props,
    children: (
      <>
        <circle cx="10" cy="10" r="6.5" />
        <path d="M10 6v4l2.5 2" />
      </>
    ),
  });
}

export function GearIcon(props: IconProps) {
  return svg({
    ...props,
    children: (
      <>
        <circle cx="10" cy="10" r="2.6" />
        <path d="M10 2.5v2.2M10 15.3v2.2M2.5 10h2.2M15.3 10h2.2M4.7 4.7l1.6 1.6M13.7 13.7l1.6 1.6M4.7 15.3l1.6-1.6M13.7 6.3l1.6-1.6" />
      </>
    ),
  });
}

export function CloseIcon(props: IconProps) {
  return svg({ ...props, children: <path d="M5 5l10 10M15 5L5 15" /> });
}

export function LeftIcon(props: IconProps) {
  return svg({ ...props, children: <path d="M12.5 4.5L7 10l5.5 5.5" /> });
}

export function RightIcon(props: IconProps) {
  return svg({ ...props, children: <path d="M7.5 4.5L13 10l-5.5 5.5" /> });
}

export function PlusIcon(props: IconProps) {
  return svg({ ...props, children: <path d="M10 4v12M4 10h12" /> });
}

export function PrevIcon(props: IconProps) {
  return svg({
    ...props,
    children: (
      <>
        <path d="M6 5v10" strokeLinecap="round" />
        <path d="M15 5.5 8.5 10 15 14.5Z" fill="currentColor" stroke="none" />
      </>
    ),
  });
}

export function NextIcon(props: IconProps) {
  return svg({
    ...props,
    children: (
      <>
        <path d="M14 5v10" strokeLinecap="round" />
        <path d="M5 5.5 11.5 10 5 14.5Z" fill="currentColor" stroke="none" />
      </>
    ),
  });
}

export function LoopIcon(props: IconProps) {
  return svg({
    ...props,
    children: (
      <>
        <path d="M4 9V8a3 3 0 0 1 3-3h8l-2-2" strokeLinecap="round" strokeLinejoin="round" />
        <path d="M16 11v1a3 3 0 0 1-3 3H5l2 2" strokeLinecap="round" strokeLinejoin="round" />
      </>
    ),
  });
}

export function VolumeIcon({ muted = false, ...props }: IconProps & { muted?: boolean }) {
  return svg({
    ...props,
    children: (
      <>
        <path d="M3.5 8h2.5L10 4.5v11L6 12H3.5Z" fill="currentColor" stroke="none" />
        {muted ? (
          <path d="m13 7.5 5 5m0-5-5 5" strokeLinecap="round" />
        ) : (
          <>
            <path d="M13 7.5a3.5 3.5 0 0 1 0 5" strokeLinecap="round" />
            <path d="M15.2 5.3a6.6 6.6 0 0 1 0 9.4" strokeLinecap="round" />
          </>
        )}
      </>
    ),
  });
}
