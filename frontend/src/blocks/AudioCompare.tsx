import { useState } from "react";
import { Heading } from "./Heading";
import { TableRows } from "./Table";
import { useMediaUrls, usePlayback } from "./media";
import { blockLink, useRenderMode } from "./mode";
import { QrLink } from "./QrLink";
import type { AudioCompareBlock, AudioTrack } from "./types";

/**
 * One player for the original and its separated tracks. Switching tracks keeps the position and
 * play state, so the listener hears the same moment from another track. The selected track's
 * transcript and original script are shown side by side.
 */
export function AudioCompare({ block, anchor }: { block: AudioCompareBlock; anchor: string }) {
  const { print, shareUrl } = useRenderMode();
  if (print && shareUrl) {
    return <AudioCompareOnPaper block={block} anchor={anchor} shareUrl={shareUrl} />;
  }
  return <AudioComparePlayer block={block} anchor={anchor} />;
}

/** Print mode: no player; a QR code and link to the online block, and every track's text. */
function AudioCompareOnPaper({
  block,
  anchor,
  shareUrl,
}: {
  block: AudioCompareBlock;
  anchor: string;
  shareUrl: string;
}) {
  const tracks: AudioTrack[] = [block.original, ...block.tracks];
  return (
    <section className="block-audio-compare" aria-labelledby={block.title ? anchor : undefined}>
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      {block.description && <p className="media-description">{block.description}</p>}
      <QrLink href={blockLink(shareUrl, block.id)} kind="오디오" />
      <p className="audio-track-names">트랙: {tracks.map((t) => t.label).join(" · ")}</p>
      {tracks.map((t, index) => (
        <div key={`${index}-${t.media_id}`} className="audio-track-print">
          <p className="audio-track-label">{t.label}</p>
          <TrackText track={t} />
        </div>
      ))}
      <Metrics block={block} />
    </section>
  );
}

function AudioComparePlayer({ block, anchor }: { block: AudioCompareBlock; anchor: string }) {
  const tracks: AudioTrack[] = [block.original, ...block.tracks];
  const { urlOf, renew } = useMediaUrls(tracks);
  const { ref, hold, handlers } = usePlayback<HTMLAudioElement>();
  const firstPlayable = Math.max(
    0,
    tracks.findIndex((track) => urlOf(track.media_id)),
  );
  const [selected, setSelected] = useState(firstPlayable);
  const track = tracks[selected] ?? tracks[0];
  if (!track) return null;
  const url = urlOf(track.media_id);

  const select = (index: number) => {
    if (index === selected) return;
    hold();
    setSelected(index);
  };

  const recover = () => {
    hold();
    void renew(track.media_id);
  };

  return (
    <section className="block-audio-compare" aria-labelledby={block.title ? anchor : undefined}>
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      {block.description && <p className="media-description">{block.description}</p>}
      <div className="audio-compare-player">
        <div className="audio-tracks" role="group" aria-label="재생할 트랙">
          {tracks.map((t, index) => (
            <button
              key={`${index}-${t.media_id}`}
              type="button"
              aria-pressed={index === selected}
              disabled={!urlOf(t.media_id)}
              onClick={() => select(index)}
            >
              {t.label}
            </button>
          ))}
        </div>
        {url ? (
          <audio
            ref={ref}
            controls
            preload="metadata"
            src={url}
            aria-label={`${track.label} 재생`}
            onError={recover}
            {...handlers}
          />
        ) : (
          <p className="media-missing">이 자료는 더 이상 제공되지 않습니다.</p>
        )}
      </div>
      <TrackText track={track} />
      <Metrics block={block} />
    </section>
  );
}

function TrackText({ track }: { track: AudioTrack }) {
  if (!track.transcript && !track.script) return null;
  return (
    <div className="audio-compare-text" aria-label={`${track.label} 글 비교`} role="group">
      {track.transcript && (
        <section>
          <h4>변환한 글</h4>
          <p>{track.transcript}</p>
        </section>
      )}
      {track.script && (
        <section>
          <h4>원래 대본</h4>
          <p>{track.script}</p>
        </section>
      )}
    </div>
  );
}

function Metrics({ block }: { block: AudioCompareBlock }) {
  const metrics = block.metrics;
  if (!metrics) return null;
  return (
    <div className="block-table audio-compare-metrics">
      <div className="sc-prose-table-scroll">
        <table>
          <thead>
            <tr>
              {metrics.columns.map((label, column) => (
                <th key={column} scope="col">
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <TableRows rows={metrics.rows} />
          </tbody>
        </table>
      </div>
      {metrics.note && <p className="media-description">{metrics.note}</p>}
    </div>
  );
}
