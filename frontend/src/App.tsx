import { HomePage } from "./home/HomePage";
import { isHomeData } from "./home/types";

/** Picks the page for the current path. `data` is the shell's #page-data. */
export function App({ path, data }: { path: string; data: unknown }) {
  if (path === "/" && isHomeData(data)) return <HomePage data={data} />;
  return (
    <main className="placeholder">
      <h1>Sandcorp</h1>
      <p>사이트를 준비하고 있습니다.</p>
    </main>
  );
}
