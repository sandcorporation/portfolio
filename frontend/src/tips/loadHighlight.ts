type HighlightModule = typeof import("./highlight");

/** The highlight chunk, tried twice. A stale tab after a deploy (old chunk hash gone) or a flaky
 * network rejects the import; colouring is optional, so after the retry the page keeps plain code
 * and the rejection goes nowhere (an unhandled rejection, GlitchTip 119). */
export async function loadHighlight(
  load: () => Promise<HighlightModule> = () => import("./highlight"),
): Promise<HighlightModule | undefined> {
  for (let attempt = 0; attempt < 2; attempt++) {
    try {
      return await load();
    } catch {
      // try once more, then give up quietly
    }
  }
  return undefined;
}
