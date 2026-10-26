import { useEffect, useRef, useState } from "react";
import { linkAttrs } from "../links";
import { themedSrc } from "./embedSrc";
import { useRenderMode } from "./mode";
import type { EmbedBlock } from "./types";

const HELLO = "sandcorp-flow:hello";
const HEIGHT = "sandcorp-flow:height";
const START_HEIGHT = 640;
const MIN_HEIGHT = 200;
const MAX_HEIGHT = 4000;

/** The site follows the reader's colour scheme (tokens.css has no toggle), and so does the frame. */
function usePrefersDark(): boolean {
  const query = "(prefers-color-scheme: dark)";
  const [dark, setDark] = useState(() => window.matchMedia?.(query).matches ?? false);
  useEffect(() => {
    const media = window.matchMedia?.(query);
    if (!media) return;
    const sync = () => setDark(media.matches);
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);
  return dark;
}

export function Embed({ block }: { block: EmbedBlock; anchor: string }) {
  const { print } = useRenderMode();
  const intro = block.intro && <p className="embed-intro">{block.intro}</p>;

  if (print) {
    // Paper has no live frame: the label, then where it is.
    return (
      <section className="block-embed" data-print>
        {intro}
        <p className="embed-open">
          <span className="embed-label">{block.open_label}</span>
          <span className="embed-where"> {block.src}</span>
        </p>
      </section>
    );
  }
  return <EmbedFrame block={block} intro={intro} />;
}

function EmbedFrame({ block, intro }: { block: EmbedBlock; intro: React.ReactNode }) {
  const dark = usePrefersDark();
  const frame = useRef<HTMLIFrameElement>(null);
  const [height, setHeight] = useState(START_HEIGHT);
  const src = themedSrc(block.src, dark);
  const origin = new URL(block.src).origin;

  useEffect(() => {
    const onMessage = (event: MessageEvent) => {
      // Both checks: another page (or another frame of this page) must not size ours.
      if (event.origin !== origin || event.source !== frame.current?.contentWindow) return;
      const data = event.data as { type?: unknown; height?: unknown } | null;
      if (data?.type !== HEIGHT || typeof data.height !== "number" || !Number.isFinite(data.height)) return;
      setHeight(Math.min(MAX_HEIGHT, Math.max(MIN_HEIGHT, Math.round(data.height))));
    };
    window.addEventListener("message", onMessage);
    return () => window.removeEventListener("message", onMessage);
  }, [origin]);

  return (
    <section className="block-embed">
      {intro}
      <iframe
        ref={frame}
        className="embed-frame"
        src={src}
        title={block.title}
        loading="lazy"
        referrerPolicy="strict-origin-when-cross-origin"
        style={{ height }}
        onLoad={() => frame.current?.contentWindow?.postMessage({ type: HELLO }, origin)}
      />
      <p className="embed-open">
        <a href={block.src} {...linkAttrs(block.src)}>
          {block.open_label}
        </a>
      </p>
    </section>
  );
}
