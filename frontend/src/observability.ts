// Browser error reports to our self-hosted GlitchTip (issue 235). The page shell puts the DSN and
// the deployed release in window.__PUBLIC__ only when SENTRY_DSN_FRONTEND is set and never on
// /print/ pages; without it nothing loads. The SDK is a separate chunk (dynamic import) so the first
// screen does not get heavier.

export interface PublicConfig {
  sentryDsn?: string;
  sentryRelease?: string;
  sentryEnvironment?: string;
}

declare global {
  interface Window {
    __PUBLIC__?: PublicConfig;
  }
}

export interface ReporterOptions {
  dsn: string;
  release: string | undefined;
  environment: string;
}

type Loader = () => Promise<{ start: (options: ReporterOptions) => void }>;

/** Start the reporter when the shell handed us a DSN. Resolves true if it started. */
export async function startErrorReporting(
  config: PublicConfig | undefined = window.__PUBLIC__,
  load: Loader = () => import("./sentry"),
): Promise<boolean> {
  const dsn = config?.sentryDsn?.trim();
  if (!dsn) return false;
  const reporter = await load();
  reporter.start({
    dsn,
    release: config?.sentryRelease || undefined,
    environment: config?.sentryEnvironment || "production",
  });
  return true;
}
