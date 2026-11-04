/** Stroke icons from the AskWRI design system's wireframes (24px grid, currentColor). */

const PATHS = {
  globe: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18",
  chevron: "M6 9l6 6 6-6",
  download: "M12 4v11M7 10l5 5 5-5M5 20h14",
  plus: "M12 5v14M5 12h14",
  external: "M14 4h6v6M20 4l-9 9M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5",
  copy: "M10 8h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2h-8a2 2 0 0 1-2-2v-8a2 2 0 0 1 2-2M16 8V5a1 1 0 0 0-1-1H5a1 1 0 0 0-1 1v10a1 1 0 0 0 1 1h3",
  send: "M12 19V5M5 12l7-7 7 7",
  warning: "M12 3l10 18H2zM12 10v4M12 17v.5",
  info: "M12 3a9 9 0 1 0 0 18a9 9 0 1 0 0-18M12 11v6M12 7.5v.5",
  layers: "M12 3l9 5-9 5-9-5zM3 13l9 5 9-5",
  check: "M5 12l5 5 9-10",
  close: "M6 6l12 12M18 6L6 18",
  prev: "M15 6l-6 6 6 6",
  next: "M9 6l6 6-6 6",
  file: "M14 3H6a1 1 0 0 0-1 1v16a1 1 0 0 0 1 1h12a1 1 0 0 0 1-1V8zM14 3v5h5",
  person: "M12 4a4 4 0 1 0 0 8a4 4 0 1 0 0-8M4 21a8 8 0 0 1 16 0",
  translate: "M4 5h8M8 3v2M6 5c0 4 3 7 6 8M10 5c0 4-3 8-6 9M13 21l4-9 4 9M14.5 18h5",
  filter: "M4 6h16M7 12h10M10 18h4",
  quote: "M7 7h4v4H7zM7 11c0 3-1 5-3 6M15 7h4v4h-4zM15 11c0 3-1 5-3 6",
} as const;

export type IconName = keyof typeof PATHS;

/** An inline SVG icon; decorative unless `label` is given. */
export function Icon({ name, small, label }: { name: IconName; small?: boolean; label?: string }) {
  return (
    <svg
      className={small ? "aw-i sm" : "aw-i"}
      viewBox="0 0 24 24"
      aria-hidden={label ? undefined : true}
      aria-label={label}
      role={label ? "img" : undefined}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
