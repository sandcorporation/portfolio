import Markdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { linkAttrs } from "../links";

// Tables scroll inside their own box so a wide one never widens the page.
const components: Components = {
  a: ({ href, title, children }) => (
    <a href={href} title={title} {...linkAttrs(href)}>
      {children}
    </a>
  ),
  table: ({ children }) => (
    <div className="table-scroll">
      <table>{children}</table>
    </div>
  ),
};

/** Markdown (GFM) body text. Raw HTML in the source is not rendered. */
export function Prose({ source }: { source: string }) {
  if (!source.trim()) return null;
  return (
    <div className="prose">
      <Markdown remarkPlugins={[remarkGfm]} skipHtml components={components}>
        {source}
      </Markdown>
    </div>
  );
}
