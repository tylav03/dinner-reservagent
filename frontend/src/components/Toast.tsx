import { useEffect, useRef, useState } from "react";

export interface ToastMessage {
  id: number;
  text: string;
}

const VISIBLE_MS = 3600; // how long it stays fully shown
const REMOVE_MS = 4000; // when it actually unmounts (after the fade-out)

/**
 * A single floating confirmation toast, fixed to the viewport so it's visible
 * regardless of which tab is active. Deliberately decoupled from any form's
 * state: once fired, it lives and dies on its own timer, never on what the
 * user does elsewhere on the page.
 */
export function Toast({
  message,
  onDismiss,
}: {
  message: ToastMessage | null;
  onDismiss: () => void;
}) {
  const [visible, setVisible] = useState(false);

  // Keep the latest onDismiss without it being a timer-effect dependency: the
  // host page (App) re-renders every few seconds from the reservations poll,
  // and if this effect depended on `onDismiss` directly, an inline callback
  // there would recreate it each render and reset the timer before it ever
  // fires. Keying only on `message` keeps the countdown honest regardless of
  // how the caller passes the callback.
  const onDismissRef = useRef(onDismiss);
  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => {
    if (!message) return;
    setVisible(true);
    const hide = window.setTimeout(() => setVisible(false), VISIBLE_MS);
    const remove = window.setTimeout(() => onDismissRef.current(), REMOVE_MS);
    return () => {
      window.clearTimeout(hide);
      window.clearTimeout(remove);
    };
  }, [message]);

  if (!message) return null;

  return (
    <div
      className={`fixed bottom-4 left-4 z-50 transition-all duration-300 ease-out ${
        visible ? "translate-y-0 opacity-100" : "translate-y-2 opacity-0"
      }`}
    >
      <div className="flex items-center gap-3 rounded-lg bg-emerald-600 px-4 py-3 text-sm text-white shadow-lg">
        <span className="text-base leading-none">✓</span>
        <span>{message.text}</span>
        <button
          onClick={onDismiss}
          aria-label="Dismiss"
          className="ml-1 text-emerald-100 hover:text-white"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
