// The GlitchTip reporter itself, loaded on demand by observability.ts (issue 235).
import * as Sentry from "@sentry/react";
import type { ErrorEvent } from "@sentry/react";
import type { ReporterOptions } from "./observability";

const CREDENTIAL_HEADERS = new Set(["cookie", "set-cookie", "authorization", "proxy-authorization"]);
const TOKEN_PATTERNS: [RegExp, string][] = [
  [/\b(bearer|basic|token)\s+[A-Za-z0-9._~+/=-]{8,}/gi, "$1 [Filtered]"],
  [/\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]*/g, "[Filtered]"],
  [/((?:token|secret|password|passwd|api[_-]?key|code|session)["']?\s*[=:]\s*)[^\s&,;"']+/gi, "$1[Filtered]"],
  // Signed page tokens in /preview/<kind>/<token> and /print/... URLs.
  [/(\/(?:preview\/[a-z]+|print(?:\/draft)?)\/)[^/\s?#"']+/g, "$1[Filtered]"],
  [/\b[A-Za-z0-9_+=]{40,}/g, "[Filtered]"],
];

export function scrubText(text: string): string {
  return TOKEN_PATTERNS.reduce((out, [pattern, replacement]) => out.replace(pattern, replacement), text);
}

function scrubValue(value: unknown): unknown {
  if (typeof value === "string") return scrubText(value);
  if (Array.isArray(value)) return value.map(scrubValue);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, scrubValue(item)]));
  }
  return value;
}

/** Remove cookies, credential headers and token-shaped strings before the event leaves. */
export function beforeSend(event: ErrorEvent): ErrorEvent {
  if (event.request) {
    delete event.request.cookies;
    delete event.request.data;
    const headers = event.request.headers;
    if (headers) {
      event.request.headers = Object.fromEntries(
        Object.entries(headers).filter(([name]) => !CREDENTIAL_HEADERS.has(name.toLowerCase())),
      );
    }
    event.request = scrubValue(event.request) as ErrorEvent["request"];
  }
  if (event.message) event.message = scrubText(event.message);
  for (const value of event.exception?.values ?? []) {
    if (value.value) value.value = scrubText(value.value);
  }
  if (event.extra) event.extra = scrubValue(event.extra) as ErrorEvent["extra"];
  if (event.breadcrumbs) event.breadcrumbs = scrubValue(event.breadcrumbs) as ErrorEvent["breadcrumbs"];
  return event;
}

export function start({ dsn, release, environment }: ReporterOptions): void {
  Sentry.init({
    dsn,
    release,
    environment,
    // SDK 11's replacement for sendDefaultPii: false — no user info, cookies, headers or bodies.
    dataCollection: { userInfo: false, cookies: false, httpHeaders: false, httpBodies: [] },
    tracesSampleRate: 0,
    beforeSend,
  });
}
