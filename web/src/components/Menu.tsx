"use client";

/** A button that opens a popover menu; closes on outside click, Escape or after a choice. */

import { type ReactNode, useEffect, useRef, useState } from "react";

type MenuProps = {
  trigger: (props: { open: boolean; toggle: () => void }) => ReactNode;
  children: (close: () => void) => ReactNode;
  align?: "left" | "right";
  placement?: "below" | "above";
};

export function Menu({ trigger, children, align = "right", placement = "below" }: MenuProps) {
  const [open, setOpen] = useState(false);
  const wrap = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onPointer = (event: PointerEvent) => {
      if (!wrap.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => event.key === "Escape" && setOpen(false);
    document.addEventListener("pointerdown", onPointer);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("pointerdown", onPointer);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const position = {
    [align]: 0,
    ...(placement === "below" ? { top: "calc(100% + 6px)" } : { bottom: "calc(100% + 6px)" }),
  };

  return (
    <div className="aw-menu-wrap" ref={wrap}>
      {trigger({ open, toggle: () => setOpen((value) => !value) })}
      {open && (
        <div className="aw-menu" role="menu" style={position}>
          {children(() => setOpen(false))}
        </div>
      )}
    </div>
  );
}
