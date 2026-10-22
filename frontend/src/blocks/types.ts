// Hand-written names on top of the generated types. Never edit types.gen.ts by hand.
import type { Tab } from "./types.gen";

export type * from "./types.gen";

/** Any block the backend schema knows. Discriminated by `type`. */
export type Block = Tab["blocks"][number];
export type BlockType = Block["type"];
