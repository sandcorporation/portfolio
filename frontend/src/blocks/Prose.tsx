import Markdown from "react-markdown";
import remarkGfm from "remark-gfm";

/** Markdown (GFM) body text. Raw HTML in the source is not rendered. */
export function Prose({ source }: { source: string }) {
  if (!source.trim()) return null;
  return (
    <div className="prose">
      <Markdown remarkPlugins={[remarkGfm]} skipHtml>
        {source}
      </Markdown>
    </div>
  );
}
