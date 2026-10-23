import type { Document } from "../blocks/types";

/** One post in a list. Mirrors PostCard in backend/services/blog.py. */
export interface PostCard {
  slug: string;
  title: string;
  summary: string;
  cover_url: string;
  tags: string[];
  /** ISO 8601 */
  published_at: string;
}

export interface TagCount {
  tag: string;
  count: number;
}

/** The shell's #page-data on `/blog`. Mirrors PostListing in the backend. */
export interface BlogIndexData {
  posts: PostCard[];
  tags: TagCount[];
  /** "" for all posts */
  tag: string;
  page: number;
  pages: number;
  total: number;
}

export interface PostNeighbor {
  slug: string;
  title: string;
}

/** The shell's #page-data on `/blog/<slug>`. Mirrors PostDetail in the backend. `prev` is the
 * post published just before (older), `next` the one just after (newer). */
export interface BlogPostData {
  card: PostCard;
  body: Document;
  prev: PostNeighbor | null;
  next: PostNeighbor | null;
}

export function isBlogIndexData(value: unknown): value is BlogIndexData {
  if (typeof value !== "object" || value === null) return false;
  return "posts" in value && "tags" in value && "pages" in value;
}

export function isBlogPostData(value: unknown): value is BlogPostData {
  if (typeof value !== "object" || value === null) return false;
  return "card" in value && "body" in value && "prev" in value;
}

export const blogPath = (slug: string) => `/blog/${slug}`;

/** `/blog` with the filter and page the list is on (the first page and "all" leave no query). */
export function blogIndexHref(tag: string, page = 1): string {
  const query = new URLSearchParams();
  if (tag) query.set("tag", tag);
  if (page > 1) query.set("page", String(page));
  const text = query.toString();
  return text ? `/blog?${text}` : "/blog";
}
