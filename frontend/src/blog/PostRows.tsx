import { postDate } from "./format";
import { blogPath, type PostCard } from "./types";

/** Blog list: one hairline row per post — title → · mono date and tags · summary (two lines). */
export function PostRows({ posts }: { posts: PostCard[] }) {
  return (
    <ul className="work-list feed-list">
      {posts.map((post) => (
        <li key={post.slug}>
          <a className="work-row" href={blogPath(post.slug)}>
            <span className="work-row-body">
              <span className="work-row-title">{post.title} →</span>
              <span className="work-row-meta feed-meta">
                <time dateTime={post.published_at}>{postDate(post.published_at)}</time>
                {post.tags.map((tag) => (
                  <span key={tag}>{tag}</span>
                ))}
              </span>
              {post.summary && <span className="work-row-summary feed-summary">{post.summary}</span>}
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}
