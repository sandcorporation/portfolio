import { useRef, useState, type ImgHTMLAttributes } from "react";
import { Viewer } from "../blocks/Gallery";

/**
 * An image that opens at its original size when pressed (issue 221): the gallery's viewer
 * (Esc closes, focus returns), drawn without shrinking so small type reads; the frame scrolls
 * and the page can be pinched. The server HTML draws the same image inside a link to the original.
 */
export function ZoomImage({ src, alt, ...rest }: ImgHTMLAttributes<HTMLImageElement> & { src: string; alt: string }) {
  const [open, setOpen] = useState(false);
  const opener = useRef<HTMLButtonElement>(null);
  const close = () => {
    setOpen(false);
    opener.current?.focus();
  };
  return (
    <>
      <button ref={opener} type="button" className="service-zoom" aria-label={`${alt} 크게 보기`} onClick={() => setOpen(true)}>
        <img src={src} alt={alt} {...rest} />
      </button>
      {open && <Viewer images={[{ url: src, alt, onError: () => {} }]} index={0} onIndex={() => {}} onClose={close} natural />}
    </>
  );
}
