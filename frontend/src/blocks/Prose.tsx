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
    <div className="sc-prose-table-scroll">
      <table>{children}</table>
    </div>
  ),
};

/** Markdown (GFM) body text. Raw HTML in the source is not rendered. `code` replaces how code is
 * drawn (tips colour their fenced blocks, issue 203). */
export function Prose({ source, code }: { source: string; code?: Components["code"] }) {
  if (!source.trim()) return null;
  return (
    <div className="prose sc-prose">
      <Markdown remarkPlugins={[remarkGfm]} skipHtml components={code ? { ...components, code } : components}>
        {source}
      </Markdown>
    </div>
  );
}
