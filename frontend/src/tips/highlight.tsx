import hljs from "highlight.js/lib/core";
import bash from "highlight.js/lib/languages/bash";
import css from "highlight.js/lib/languages/css";
import diff from "highlight.js/lib/languages/diff";
import dockerfile from "highlight.js/lib/languages/dockerfile";
import javascript from "highlight.js/lib/languages/javascript";
import json from "highlight.js/lib/languages/json";
import python from "highlight.js/lib/languages/python";
import sql from "highlight.js/lib/languages/sql";
import typescript from "highlight.js/lib/languages/typescript";
import xml from "highlight.js/lib/languages/xml";
import yaml from "highlight.js/lib/languages/yaml";
import type { Components } from "react-markdown";

// issue 203: the highlight.js core with only the languages tips are likely to use (each brings
// its own aliases: py, ts, js, sh/shell, yml, html, docker). Colours are the --color-code-*
// tokens (styles.css), not a highlight.js theme.
for (const [name, language] of Object.entries({
  bash,
  css,
  diff,
  dockerfile,
  javascript,
  json,
  python,
  sql,
  typescript,
  xml,
  yaml,
})) {
  hljs.registerLanguage(name, language);
}

/** The language a fenced block names (`language-<name>`) when it is one we highlight. */
export function highlightLanguage(className: string | undefined): string | null {
  const name = /\blanguage-([\w-]+)/.exec(className ?? "")?.[1];
  return name && hljs.getLanguage(name) ? name : null;
}

/** react-markdown's `code`: a fenced block in a known language comes out coloured (highlight.js
 * escapes the text it wraps); inline code and other languages stay as they are. */
export const highlightedCode: Components["code"] = ({ className, children }) => {
  const language = highlightLanguage(className);
  if (!language || typeof children !== "string") return <code className={className}>{children}</code>;
  const html = hljs.highlight(children, { language, ignoreIllegals: true }).value;
  return <code className={`${className ?? ""} hljs`} dangerouslySetInnerHTML={{ __html: html }} />;
};
