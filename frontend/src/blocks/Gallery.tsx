import { useEffect, useRef, useState } from "react";
import { Heading } from "./Heading";
import type { GalleryBlock } from "./types";

type Shown = { url: string; alt: string; caption?: string | null };

export function Gallery({ block, anchor }: { block: GalleryBlock; anchor: string }) {
  // The server fills in `url`; an image without one (media gone or not public) is skipped.
  const images: Shown[] = block.images.flatMap((image) =>
    image.url ? [{ url: image.url, alt: image.alt, caption: image.caption }] : [],
  );
  const [open, setOpen] = useState<number | null>(null);
  const opener = useRef<HTMLElement | null>(null);

  if (images.length === 0) return null;

  const close = () => {
    setOpen(null);
    opener.current?.focus();
  };

  return (
    <section className="block-gallery" aria-labelledby={block.title ? anchor : undefined}>
      {block.title && (
        <Heading level={3} id={anchor}>
          {block.title}
        </Heading>
      )}
      <ul className="gallery-grid">
        {images.map((image, index) => (
          <li key={index}>
            <button
              type="button"
              className="gallery-thumb"
              aria-label={`${image.alt} 크게 보기`}
              onClick={(event) => {
                opener.current = event.currentTarget;
                setOpen(index);
              }}
            >
              <img src={image.url} alt={image.alt} loading="lazy" />
            </button>
          </li>
        ))}
      </ul>
      {open !== null && (
        <Viewer images={images} index={open} onIndex={setOpen} onClose={close} />
      )}
    </section>
  );
}

function Viewer({
  images,
  index,
  onIndex,
  onClose,
}: {
  images: Shown[];
  index: number;
  onIndex: (index: number) => void;
  onClose: () => void;
}) {
  const closeButton = useRef<HTMLButtonElement>(null);
  const image = images[index];
  const step = (by: number) => onIndex((index + by + images.length) % images.length);

  useEffect(() => closeButton.current?.focus(), []);

  if (!image) return null;

  return (
    <div
      className="gallery-viewer"
      role="dialog"
      aria-modal="true"
      aria-label="이미지 보기"
      onKeyDown={(event) => {
        if (event.key === "Escape") onClose();
        else if (event.key === "ArrowRight") step(1);
        else if (event.key === "ArrowLeft") step(-1);
      }}
    >
      <div className="gallery-backdrop" onClick={onClose} />
      <figure className="gallery-figure">
        <img src={image.url} alt={image.alt} />
        {image.caption && <figcaption>{image.caption}</figcaption>}
      </figure>
      <p className="gallery-count">
        {index + 1} / {images.length}
      </p>
      <button ref={closeButton} type="button" className="gallery-close" onClick={onClose}>
        닫기
      </button>
      {images.length > 1 && (
        <>
          <button type="button" className="gallery-prev" onClick={() => step(-1)}>
            이전
          </button>
          <button type="button" className="gallery-next" onClick={() => step(1)}>
            다음
          </button>
        </>
      )}
    </div>
  );
}
