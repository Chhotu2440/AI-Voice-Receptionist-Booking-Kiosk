import { Component, type ErrorInfo, type ReactNode } from "react";

import { reloadKiosk, shellIsCached } from "../lib/resilience";

const RESTART_AFTER_MS = 5_000;

/**
 * If any screen throws while rendering, React would otherwise leave a blank page on an unattended kiosk.
 * Show a friendly bilingual message and restart into IDLE (a reload never keeps customer data).
 */
export class CrashGuard extends Component<{ children: ReactNode }, { crashed: boolean }> {
  state = { crashed: false };
  private timer: number | undefined;

  static getDerivedStateFromError(): { crashed: boolean } {
    return { crashed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    // eslint-disable-next-line no-console
    console.error("kiosk_crash", error, info.componentStack);
    const tryRestart = () => {
      // Only reload when the page will come back (cached shell or network); otherwise keep waiting.
      if (shellIsCached() || navigator.onLine) reloadKiosk("crash");
      else this.timer = window.setTimeout(tryRestart, RESTART_AFTER_MS);
    };
    this.timer = window.setTimeout(tryRestart, RESTART_AFTER_MS);
  }

  componentWillUnmount(): void {
    window.clearTimeout(this.timer);
  }

  render(): ReactNode {
    if (!this.state.crashed) return this.props.children;
    return (
      <div data-testid="crash-screen" className="flex h-full w-full flex-col items-center justify-center gap-6 bg-arena-950 text-center">
        <div className="font-display text-5xl">Restarting…</div>
        <div className="text-3xl">फिर से शुरू हो रहा है…</div>
        <div className="text-2xl text-white/70">One moment please. Staff at the reception desk can help.</div>
      </div>
    );
  }
}
