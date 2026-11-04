import { useState } from "react";
import { linkAttrs } from "../links";
import type { ShortCard } from "./types";

const SHORTS_CHANNEL_URL = "https://www.youtube.com/@sandcorporation";

/** The player that replaces a card once its button is pressed (never on the first load). */
function embedUrl(youtubeId: string): string {
  return `https://www.youtube-nocookie.com/embed/${encodeURIComponent(youtubeId)}?autoplay=1&playsinline=1`;
}

function ShortItem({ short }: { short: ShortCard }) {
  const [playing, setPlaying] = useState(false);
  return (
    <li className="short-card">
      {playing ? (
        <div className="short-frame">
          <iframe
            src={embedUrl(short.youtube_id)}
            title={short.title}
            allow="autoplay; encrypted-media; picture-in-picture"
            allowFullScreen
            // The site sends Referrer-Policy: same-origin; without the origin YouTube refuses to
            // play (error 153), so the player alone gets the origin (never the path).
            referrerPolicy="strict-origin-when-cross-origin"
          />
        </div>
      ) : (
        <button type="button" className="short-frame" aria-label={`${short.title} 재생`} onClick={() => setPlaying(true)}>
          <img src={short.thumbnail_url} alt="" width={480} height={360} loading="lazy" />
          <span className="short-play" aria-hidden="true" />
        </button>
      )}
      <p className="short-title">{short.title}</p>
      {short.link && (
        <a className="short-link" href={short.link}>
          {short.link_label}
        </a>
      )}
    </li>
  );
}

/** Home 「짧은 영상」 (issue 207): thumbnails and play buttons only; pressing one swaps in the
 * youtube-nocookie player right there. The server HTML draws the same cards as YouTube links. */
export function ShortsSection({ index, shorts }: { index: string; shorts: ShortCard[] }) {
  return (
    <section className="page-section" aria-labelledby="home-shorts">
      <p className="section-head">
        <span aria-hidden="true">{index} — Shorts</span>
        <a href={SHORTS_CHANNEL_URL} {...linkAttrs(SHORTS_CHANNEL_URL)}>
          유튜브에서 보기 →
        </a>
      </p>
      <h2 id="home-shorts" className="page-section-title">
        짧은 영상
      </h2>
      <p className="section-lead">만들고 운영하며 겪은 일을 1분 안팎으로 보여 줍니다.</p>
      <ul className="shorts-list">
        {shorts.map((short) => (
          <ShortItem key={short.youtube_id} short={short} />
        ))}
      </ul>
    </section>
  );
}
