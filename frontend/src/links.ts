/** A link to another host (http(s) or //host); /path, #anchor, mailto: and the site's own host are not. Mirror of public_html.is_external. */
export function isExternalHref(href: string | undefined, siteHost: string = window.location.host): boolean {
  if (!href || !/^(https?:)?\/\//i.test(href.trim())) return false;
  try {
    return new URL(href.trim(), "https://x.invalid").host.toLowerCase() !== siteHost.toLowerCase();
  } catch {
    return false;
  }
}

/** target/rel for a link: another host opens in a new tab. */
export function linkAttrs(href: string | undefined): { target?: string; rel?: string } {
  return isExternalHref(href) ? { target: "_blank", rel: "noopener noreferrer" } : {};
}
