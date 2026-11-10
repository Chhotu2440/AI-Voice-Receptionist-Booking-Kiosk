import { useCallback, useEffect, useRef, useState } from "react";

import { Button } from "./components/ui";
import { ApiError, deviceToken, heartbeat, loadCreds, saveCreds } from "./lib/api";
import { KioskSocket } from "./lib/socket";
import { ConfirmedScreen, CancelledScreen, EnquiryDoneScreen, StaffScreen } from "./screens/End";
import { DateScreen, PackagesScreen, SlotsScreen, SummaryScreen } from "./screens/Booking";
import { NameScreen, PhoneScreen } from "./screens/Customer";
import { CustomEventScreen, GuestsScreen, OccasionScreen } from "./screens/Group";
import { Greeting, Idle, Setup } from "./screens/Start";
import { useKiosk, useT } from "./store";
import type { KioskStateName } from "./types";

const SCREENS: Record<KioskStateName, () => JSX.Element | null> = {
  IDLE: Idle,
  GREETING: Greeting,
  CUSTOMER_NAME: NameScreen,
  CUSTOMER_PHONE: PhoneScreen,
  GUEST_COUNT: GuestsScreen,
  OCCASION: OccasionScreen,
  CUSTOM_EVENT_DETAILS: CustomEventScreen,
  PACKAGE_DISCOVERY: PackagesScreen,
  DATE_SELECTION: DateScreen,
  SLOT_SELECTION: SlotsScreen,
  BOOKING_SUMMARY: SummaryScreen,
  BOOKING_CONFIRMED: ConfirmedScreen,
  SESSION_COMPLETE: EnquiryDoneScreen,
  STAFF_ASSISTANCE: StaffScreen,
  SESSION_CANCELLED: CancelledScreen,
};

const TOKEN_REFRESH_MS = 50 * 60 * 1000;
const STILL_THERE_GRACE_S = 10;

export default function App() {
  const [paired, setPaired] = useState(() => loadCreds() !== null);
  if (!paired) return <Setup onPaired={() => setPaired(true)} />;
  return <Kiosk onUnpaired={() => setPaired(false)} />;
}

function Kiosk({ onUnpaired }: { onUnpaired: () => void }) {
  const { t } = useT();
  const { receive, setConn, setSocket, setConfig, send } = useKiosk.getState();
  const conn = useKiosk((s) => s.conn);
  const kioskState = useKiosk((s) => s.state?.state ?? "IDLE");
  const version = useKiosk((s) => s.state?.version ?? 0);
  const idleTimeout = useKiosk((s) => s.config.idle_timeout_s);
  const token = useRef<{ value: string; at: number } | null>(null);

  const getToken = useCallback(async () => {
    if (token.current && Date.now() - token.current.at < TOKEN_REFRESH_MS) return token.current.value;
    const creds = loadCreds();
    if (!creds) throw new Error("not paired");
    try {
      const value = await deviceToken(creds);
      token.current = { value, at: Date.now() };
      return value;
    } catch (e) {
      if (e instanceof ApiError && (e.status === 401 || e.status === 403)) {
        saveCreds(null); // revoked or disabled in admin: back to the pairing screen
        onUnpaired();
      }
      throw e;
    }
  }, [onUnpaired]);

  useEffect(() => {
    const socket = new KioskSocket(getToken, receive, setConn);
    setSocket(socket);
    void socket.connect();
    const beat = async () => {
      try {
        setConfig(await heartbeat(await getToken(), {}));
      } catch {
        /* offline; the socket shows the reconnecting banner */
      }
    };
    void beat();
    const hb = window.setInterval(() => void beat(), 60_000);
    return () => {
      window.clearInterval(hb);
      socket.close();
      setSocket(null);
    };
  }, [getToken, receive, setConn, setSocket, setConfig]);

  // Inactivity: after idle_timeout_s without a touch, ask "still there?", then clear the session (PII).
  const [stillThere, setStillThere] = useState(false);
  const lastTouch = useRef(Date.now());
  useEffect(() => {
    const touch = () => {
      lastTouch.current = Date.now();
      setStillThere(false);
    };
    window.addEventListener("pointerdown", touch);
    return () => window.removeEventListener("pointerdown", touch);
  }, []);
  useEffect(() => {
    lastTouch.current = Date.now();
  }, [version]);
  useEffect(() => {
    const exempt = ["IDLE", "BOOKING_CONFIRMED", "SESSION_COMPLETE", "SESSION_CANCELLED", "STAFF_ASSISTANCE"];
    const id = window.setInterval(() => {
      if (exempt.includes(kioskState)) return setStillThere(false);
      const idle = (Date.now() - lastTouch.current) / 1000;
      if (idle > idleTimeout + STILL_THERE_GRACE_S) {
        setStillThere(false);
        send("reset", { reason: "TIMEOUT" });
      } else if (idle > idleTimeout) setStillThere(true);
    }, 1000);
    return () => window.clearInterval(id);
  }, [kioskState, idleTimeout, send]);

  const Current = SCREENS[kioskState];
  return (
    <div className="relative h-full w-full">
      <Current />
      {conn !== "online" ? (
        <div data-testid="offline" className="absolute inset-x-0 top-0 bg-alert/90 py-3 text-center text-2xl font-semibold text-arena-950">
          {t.offline}
        </div>
      ) : null}
      {stillThere ? (
        <div className="absolute inset-0 flex flex-col items-center justify-center gap-8 bg-arena-950/90">
          <div className="font-display text-5xl">{t.stillThere}</div>
          <Button onClick={() => setStillThere(false)}>{t.imHere}</Button>
        </div>
      ) : null}
    </div>
  );
}
