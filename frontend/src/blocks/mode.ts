// How a document is rendered. Print is a mode of the same block renderers (not a second set of
// components): every tab laid out in order, media that cannot play on paper turned into a QR code.
import { createContext, useContext } from "react";

export interface RenderMode {
  print: boolean;
  /** The customer-facing address of the proposal (`https://…/p/<slug>`); print mode only. */
  shareUrl: string | null;
}

export const screenMode: RenderMode = { print: false, shareUrl: null };

export const RenderModeContext = createContext<RenderMode>(screenMode);

export function useRenderMode(): RenderMode {
  return useContext(RenderModeContext);
}

/** Where a block lives on the customer page: `<proposal url>#<block id>`. */
export function blockLink(shareUrl: string, blockId: string): string {
  return `${shareUrl}#${blockId}`;
}
