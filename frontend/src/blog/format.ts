const DATE = new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" });

/** 2026.10.23 in Seoul time, whatever the reader's clock says. */
export function postDate(iso: string): string {
  const at = new Date(iso);
  return Number.isNaN(at.getTime()) ? "" : DATE.format(at).replaceAll("-", ".");
}
