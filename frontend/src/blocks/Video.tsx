import type { MouseEvent } from "react";
import { Heading } from "./Heading";
import { useMediaRefresh, useMediaUrls, usePlayback } from "./media";
import { blockLink, useRenderMode } from "./mode";
import { QrLink } from "./QrLink";
import type { VideoBlock } from "./types";

export function Video({ block, anchor }: { block: VideoBlock; anchor: string }) {
  const { print, shareUrl } = useRenderMode();
  if (print && shareUrl) return <VideoOnPaper block={block} anchor={anchor} shareUrl={shareUrl} />;
  return <VideoPlayer block={block} anchor={anchor} />;
}

/** Print mode: the file cannot play on paper (and its URL expires), so a QR code and a link. */
function VideoOnPaper({
  block,
  anchor,
  shareUrl,
}: {
  block: VideoBlock;
  anchor: string;
  shareUrl: string;
}) {
  return (
    <section className="block-video" aria-labelledby={block.title ? anchor : undefined}>
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      <QrLink href={blockLink(shareUrl, block.id)} kind="영상" />
      {block.caption && <p className="media-description">{block.caption}</p>}
    </section>
  );
}

function VideoPlayer({ block, anchor }: { block: VideoBlock; anchor: string }) {
  const { urlOf, renew } = useMediaUrls([{ media_id: block.media_id, url: block.url }]);
  const { ref, hold, handlers } = usePlayback<HTMLVideoElement>();
  const refresh = useMediaRefresh();
  const url = urlOf(block.media_id);

  const download = async (event: MouseEvent<HTMLAnchorElement>) => {
    if (!refresh) return; // a public file: the link itself downloads it
    event.preventDefault();
    const saved = await refresh(block.media_id, { download: true });
    if (saved) window.location.assign(saved);
  };

  return (
    <section className="block-video" aria-labelledby={block.title ? anchor : undefined}>
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      <figure>
        {url ? (
          <video
            ref={ref}
            controls
            playsInline
            preload="metadata"
            src={url}
            poster={block.poster_url ?? undefined}
            controlsList={block.allow_download ? undefined : "nodownload"}
            aria-label={block.title ?? block.caption ?? "영상"}
            onError={() => {
              hold();
              void renew(block.media_id);
            }}
            {...handlers}
          />
        ) : (
          <p className="media-missing">이 영상은 더 이상 제공되지 않습니다.</p>
        )}
        {block.caption && <figcaption>{block.caption}</figcaption>}
      </figure>
      {block.allow_download && url && (
        <a className="media-download" href={url} download onClick={download}>
          영상 파일 내려받기
        </a>
      )}
    </section>
  );
}
