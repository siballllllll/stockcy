"use client";

import { useEffect } from "react";
import { useAiTask } from "@/contexts/AiTaskContext";

/**
 * 서버측 완료 이벤트(백엔드 스케줄러가 끝낸 자동 시나리오·트리거된 가격알림 등)를
 * 주기적으로 폴링해 벨 알림으로 등록한다. notifyDone이 멱등이라 같은 이벤트는 1회만 뜬다.
 * 화면에는 아무것도 렌더하지 않는다(null).
 */
export function NotificationPoller() {
  const { notifyDone } = useAiTask();

  useEffect(() => {
    let cancelled = false;

    const poll = async () => {
      try {
        const res = await fetch("/backend/api/ai/notifications/feed");
        if (!res.ok) return;
        const txt = await res.text();
        let j: any = null;
        try { j = JSON.parse(txt); } catch { return; }
        if (cancelled || !Array.isArray(j?.events)) return;
        for (const e of j.events) {
          if (e?.id && e?.title) notifyDone(e.id, e.title, e.route || "/");
        }
      } catch { /* 네트워크 오류 무시 */ }
    };

    poll();                                   // 마운트 직후 1회
    const iv = setInterval(poll, 180_000);    // 이후 3분마다
    return () => { cancelled = true; clearInterval(iv); };
  }, [notifyDone]);

  return null;
}
