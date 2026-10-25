/** The address with `theme=dark` for the dark scheme (and no `theme` for light, whatever the author wrote). */
export function themedSrc(src: string, dark: boolean): string {
  const url = new URL(src);
  if (dark) url.searchParams.set("theme", "dark");
  else url.searchParams.delete("theme");
  return url.toString();
}
