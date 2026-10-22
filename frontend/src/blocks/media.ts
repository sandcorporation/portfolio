// Media URLs in served documents. The server fills each reference's `url`; for private media
// (proposals) that URL is presigned and expires after ten minutes. A page that can ask for a fresh
// one provides `MediaUrlContext`; renderers call `renew` when an element fails to load and resume
// where playback was. Public pages provide nothing and simply keep the URL they were given.
import { createContext, useCallback, useContext, useRef, useState } from "react";

export interface RefreshOptions {
  /** A URL that makes the browser save the file instead of playing it. */
  download?: boolean;
}

/** Asks the server for a fresh URL of a media item in this document; null when refused. */
export type RefreshMediaUrl = (mediaId: number, options?: RefreshOptions) => Promise<string | null>;

export const MediaUrlContext = createContext<RefreshMediaUrl | null>(null);

export function useMediaRefresh(): RefreshMediaUrl | null {
  return useContext(MediaUrlContext);
}

/** GET {endpoint}/{id} -> {"url": "..."} (see backend/core/shell.py `proposal_media`). */
export function endpointRefresher(
  endpoint: string,
  fetchImpl: typeof fetch = (...args) => fetch(...args),
): RefreshMediaUrl {
  return async (mediaId, options) => {
    const query = options?.download ? "?download=1" : "";
    try {
      const response = await fetchImpl(`${endpoint}/${mediaId}${query}`, {
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
      if (!response.ok) return null;
      const body: unknown = await response.json();
      if (typeof body === "object" && body !== null && "url" in body) {
        return typeof body.url === "string" ? body.url : null;
      }
      return null;
    } catch {
      return null;
    }
  };
}

/** A failure within this long after the last renewal is not an expired URL; do not loop. */
export const RENEW_GAP_MS = 5000;

interface MediaRef {
  media_id: number;
  url?: string | null;
}

/**
 * The current URL of each referenced media item, starting from what the server filled in.
 * `renew(id)` fetches a fresh one (once per RENEW_GAP_MS per item) and reports whether it did.
 */
export function useMediaUrls(refs: MediaRef[]) {
  const refresh = useMediaRefresh();
  const [urls, setUrls] = useState(
    () => new Map(refs.map((ref) => [ref.media_id, ref.url ?? null] as const)),
  );
  const lastRenewal = useRef(new Map<number, number>());

  const renew = useCallback(
    async (mediaId: number): Promise<boolean> => {
      if (!refresh) return false;
      const now = Date.now();
      const last = lastRenewal.current.get(mediaId);
      if (last !== undefined && now - last < RENEW_GAP_MS) return false;
      lastRenewal.current.set(mediaId, now);
      const fresh = await refresh(mediaId);
      if (!fresh) return false;
      setUrls((current) => new Map(current).set(mediaId, fresh));
      return true;
    },
    [refresh],
  );

  const urlOf = (mediaId: number): string | null => urls.get(mediaId) ?? null;
  return { urlOf, renew };
}

/**
 * Keeps playback going across a source change (a renewed URL, another track): `hold()` before
 * the change remembers the position and whether it was playing; the new source resumes there.
 */
export function usePlayback<T extends HTMLMediaElement>() {
  const ref = useRef<T>(null);
  const playing = useRef(false);
  const resume = useRef<{ at: number; play: boolean } | null>(null);

  const hold = () => {
    const element = ref.current;
    if (element) resume.current = { at: element.currentTime, play: playing.current };
  };

  const handlers = {
    onPlay: () => {
      playing.current = true;
    },
    onPause: () => {
      // Changing the source pauses the element; that is not the listener's choice.
      if (!resume.current) playing.current = false;
    },
    onLoadedMetadata: () => {
      const element = ref.current;
      const held = resume.current;
      resume.current = null;
      if (!element || !held) return;
      element.currentTime = held.at;
      if (held.play) element.play()?.catch(() => undefined);
    },
  };

  return { ref, hold, handlers };
}
