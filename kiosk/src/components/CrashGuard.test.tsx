import { render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("../lib/resilience", () => ({ reloadKiosk: vi.fn(), shellIsCached: vi.fn(() => true) }));

import { reloadKiosk } from "../lib/resilience";
import { CrashGuard } from "./CrashGuard";

function Boom(): JSX.Element {
  throw new Error("render failed");
}

describe("CrashGuard", () => {
  afterEach(() => vi.useRealTimers());

  it("replaces a crashed screen with a restart message, then reloads into IDLE", () => {
    vi.useFakeTimers();
    vi.spyOn(console, "error").mockImplementation(() => undefined);
    render(
      <CrashGuard>
        <Boom />
      </CrashGuard>,
    );
    expect(screen.getByTestId("crash-screen").textContent).toContain("Restarting");
    expect(reloadKiosk).not.toHaveBeenCalled();
    vi.advanceTimersByTime(5_000);
    expect(reloadKiosk).toHaveBeenCalledWith("crash");
  });
});
