# 15 — Webcam & Kiosk Hardware

> **Price status:** the figures below are **indicative estimates for the Indian market and have not yet been verified against live listings.** Task HW-01 collects three dated vendor quotes (Amazon.in / Flipkart / local integrators such as Nehru Place dealers) before purchase. No hardware should be bought from this table alone.

## 1. Form-factor comparison

| | A: Mini PC + touchscreen monitor (**recommended**) | B: All-in-one touch PC | C: Commercial kiosk enclosure |
|---|---|---|---|
| Cost | Medium | Medium | High |
| Repairability | High (swap either part) | Low (one unit) | Medium |
| Continuous operation | Good, with fanless/quiet mini PC | Consumer AIOs are not built for 12 h/day | Designed for it |
| Mounting | Monitor on VESA floor stand or wall | Desk stand | Floor-standing, lockable |
| Tamper resistance | Needs a lockable stand/enclosure | Low | High |

## 2. Configurations

| Component | Budget (≈ ₹55–75k, est.) | Premium (≈ ₹1.4–2.2 lakh, est.) |
|---|---|---|
| Compute | Mini PC, Intel Core i5 (12th gen+) / Ryzen 5, **16 GB RAM**, 512 GB NVMe | Mini PC Core i7 / Ryzen 7, 16–32 GB, 1 TB NVMe, fanless or industrial |
| Display | 21.5"–24" 1080p 10-point capacitive touch monitor (USB touch, VESA) | 27"–32" commercial-grade PCAP touch display, anti-glare, rated 16/7 |
| Camera | 1080p USB webcam with wide FOV (e.g. Logitech C920/C922 class) | Logitech Brio-class 4K webcam (better low light) |
| Microphone | USB **conference speakerphone** with built-in AEC (Jabra Speak / Poly Sync class). Recommended even on budget, because echo cancellation is critical for barge-in | Directional USB array mic (beamforming) + separate speakers |
| Speakers | Speakerphone's speaker, or powered 2.0 speakers | Powered speakers mounted in the enclosure |
| Enclosure | Steel floor stand with VESA mount + lockable mini PC bay | Commercial kiosk shell with integrated stand, cable management, ventilation |
| Power | 1 kVA line-interactive UPS (≈ 20–30 min) | 1–2 kVA online UPS |
| Network | Wired Ethernet to the venue router + 4G USB/router failover | Same + dual WAN router |
| OS | Windows 11 Pro (Assigned Access kiosk mode) **or** Ubuntu 24.04 LTS + Chromium kiosk | Same |

GPU: **not required**, because AI inference is in the cloud and MediaPipe face detection runs fine on an integrated GPU/CPU at 5 fps.

## 3. Placement & environment
- Mount the camera at eye level (~150–160 cm), angled slightly down. Avoid backlight (no window behind the customer).
- The reception area is noisy (game audio, groups). Steps: a speakerphone with AEC, a distance threshold so only the nearest person triggers presence, and a server VAD threshold tuned on-site.
- Ventilation: keep the mini PC bay vented, since the kiosk runs ~12 h/day.
- Physical security: lock USB ports inside the enclosure. Disable OS hotkeys in kiosk mode.

## 4. Recommendation
**Budget configuration with a speakerphone + 24" touch monitor + steel floor stand**, as the pilot. Upgrade the display or enclosure after 1–2 months of real usage data. Decision D-08 (budget tier) is open for the owner.
