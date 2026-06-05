"use client";
import { useState, useEffect } from "react";

/** 화면 폭이 breakpoint(기본 768px) 이하이면 true. SSR에서는 false로 시작 후 마운트 시 보정. */
export function useIsMobile(breakpoint = 768): boolean {
  const [isMobile, setIsMobile] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia(`(max-width: ${breakpoint}px)`);
    const update = () => setIsMobile(mq.matches);
    update();
    mq.addEventListener("change", update);
    return () => mq.removeEventListener("change", update);
  }, [breakpoint]);
  return isMobile;
}
