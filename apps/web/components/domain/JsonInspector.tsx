"use client";

import { useState } from "react";

export function JsonInspector({ value, title = "Raw JSON" }: { value: unknown; title?: string }) {
  const [open, setOpen] = useState(false);
  const text = JSON.stringify(value, null, 2);

  return (
    <div className="json-panel" style={{ marginTop: "1rem" }}>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="btn btn-ghost"
        style={{ width: "100%", justifyContent: "flex-start", borderRadius: 0 }}
        aria-expanded={open}
      >
        {open ? "▼" : "▶"} {title}
      </button>
      <div
        style={{
          overflow: "hidden",
          transition: "max-height 0.2s var(--ease-out, ease)",
          maxHeight: open ? "24rem" : 0,
        }}
      >
        <pre>{text}</pre>
      </div>
    </div>
  );
}
