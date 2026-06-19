# APCOMS Final Year Project — Demo Plan

**Project:** AI-Powered Passenger Counting and Real-Time Occupancy Monitoring System
**Team:** BSE26-8 — Nankya Elsa (Counting Module) & Musiimenta Cissylyn (Mobile Application)
**Institution:** Makerere University, BSc Software Engineering, Department of Networks
**Demo format:** Live walk-through, ~30-35 minutes total (incl. Q&A)

---

## Demo Structure

| Phase                              | Duration  | Lead         | What                                      |
| ---------------------------------- | --------- | ------------ | ----------------------------------------- |
| 1. Intro & architecture            | 3-5 min   | Elsa + Cissy | Project, problem, team split, tech stack  |
| 2. Pre-demo state walkthrough      | 2-3 min   | Elsa         | Show dashboard tabs on fresh service day  |
| 3. Live scenarios (the main event) | 12-15 min | Both         | 8 scenarios telling one coherent story    |
| 4. Edge cases & robustness         | 3-5 min   | Elsa         | Illegal boarding, forged QR, manual reset |
| 5. Analytics deep-dive             | 3-5 min   | Elsa         | Charts populated with demo-generated data |
| 6. Q&A                             | 5-10 min  | Both         | Free exploration                          |

---

## The Story: "A Morning on Shuttle 001"

A coherent narrative where state carries from scenario to scenario. The shuttle starts the service day with count = 0 and goes through a realistic morning of pickups and drop-offs. The panel sees the count grow and shrink naturally, like a real shuttle would.

**Names of test passengers:** TBD (real-feeling names like Alice, Bob, Carla, Daniel, Elena, Frank — finalise with Cissy)

---

## Scenario Walk-Through

### Scenario 1 — Western Gate: First boardings of the day

- **State before:** count = 0
- **Bookings:** 3 passengers booked (Alice → CONAS, Bob → Africa Hall, Carla → CONAS)
- **What happens:** Orchestrator arrives Western Gate. Scanner queue opens. All 3 scan their QRs. Main.py launches. AI counts 3 boardings in the visualization window.
- **State after:** count = 3
- **Panel sees:**
  - Pickups Expected: 3 → 0
  - Boarded Here: 0 → 3
  - Passengers Onboard: 0 → 3
  - Live Bookings tab: 3 active rows
  - AI viz window: bounding boxes + IDs + counting line

### Scenario 2 — CEDAT: More pickups, alightings starting to appear

- **State before:** count = 3
- **Bookings:** Daniel → Main Library, Elena → Africa Hall
- **What happens:** Scanner opens, 2 more scans. Main.py launches. AI counts 2 boardings.
- **State after:** count = 5
- **Panel sees:**
  - Pickups Expected: 2 → 0
  - Boarded Here: 0 → 2
  - Alightings Expected (at future stops) showing non-zero now

### Scenario 3 — CONAS: First alightings

- **State before:** count = 5
- **Bookings:** No new pickups. Alice + Carla destined here.
- **What happens:** Orchestrator skips scanner (no pickups) and logs "alighting-only stop". Main.py launches. AI counts 2 alightings. Booking completer fires for Alice and Carla.
- **State after:** count = 3
- **Panel sees:**
  - "[NO SCANNER] alighting-only stop" log
  - Alightings Expected: 2 → 0
  - Alighted Here: 0 → 2
  - Live Bookings: Alice and Carla flip to "completed"

### Scenario 4 — Main Library: Daniel alights

- **State before:** count = 3
- **Bookings:** No new pickups. Daniel destined here.
- **What happens:** Same as Scenario 3 — alighting-only, scanner skipped.
- **State after:** count = 2
- **Panel sees:** Same as Scenario 3, with 1 alighting

### Scenario 5 — Africa Hall: Empty stop

- **State before:** count = 2 (Bob and Elena still onboard, but their destinations are still ahead)
- **Wait — actually Elena IS destined for Africa Hall, so this is alighting-only**

> **Revision needed:** check the booking destinations — Elena booked Western → Africa Hall means at Africa Hall she alights. So Africa Hall is NOT empty.

> **Alternative empty stop:** Swimming Pool. No bookings there at all.

- **Bookings:** (after revising the script)
- **What happens:** Orchestrator logs "[SKIPPING] no pickups or alightings". Shuttle passes through. Main.py never launches.
- **State after:** count unchanged
- **Panel sees:** Shuttle still updates current_stop, but no scanner queue, no AI run. Empty-stop optimization in action.

### Scenario 6 — User cancels their booking (Frank)

- **Wait — this scenario needs Cissy's app to cancel.**
- **What happens:** Cissy opens the mobile app on her phone. She has a booking for COCIS. She cancels it from the app. The Live Bookings tab on the dashboard updates within 5 seconds to show the booking as "cancelled".
- **Panel sees:** End-user can self-cancel. Status flips in real time on dashboard.

### Scenario 7 — No-show at Swimming Pool

- **Bookings:** A test passenger booked but doesn't appear at the stop.
- **What happens:** Orchestrator arrives, scanner queue opens, operator presses Q to advance (or just waits for the queue to be empty). NoShowCanceller fires. Booking flips to cancelled.
- **Panel sees:**
  - Scanner waited, nobody scanned
  - Booking status: reserved → cancelled
  - Dashboard "Alighted Here" doesn't increment (passenger never boarded)

### Scenario 8 — Forged QR code attempt

- **What happens:** Someone tries to scan a QR with an invalid signature (or one for a different shuttle).
- **Panel sees:**
  - Scanner logs "[SCAN REJECTED] forged QR"
  - Booking does NOT flip to active
  - Diagnostic shows in the dashboard logs

### Scenario 9 — Capacity reached, app refuses booking

- **State:** count = 20 (we'll seed this manually or run multiple scenarios to fill up)
- **What happens:** Cissy opens her app, tries to create a new booking. App detects the shuttle is full from Firebase and refuses the booking with a clear message.
- **Panel sees:** Mobile-side validation works. System-wide consistency.

### Scenario 10 — Illegal boarding detection (the safety guard)

- **State:** count = 20 (full)
- **What happens:** A passenger tries to board anyway (bypassing the app). AI detects the person crossing inward. Count refuses to increment (safety guard). Diagnostic log shows red ERROR badge.
- **Panel sees:**
  - Count stays at 20
  - "[ERROR] Illegal boarding attempt: shuttle at full capacity" in Recent Diagnostic Logs panel
  - Operator alerted to investigate

### Scenario 11 — Manual emergency reset

- **What happens:** Operator opens Settings → clicks Reset Count → modal pops up → Confirm Reset.
- **Panel sees:**
  - Count flips from 20 to 0
  - Available Seats flips to 20
  - OLED, AI viz, mobile app, Firebase all sync
  - Recent Diagnostic Logs: "[WARNING] Manual count reset performed by administrator"
  - Audit trail captured

### Scenario 12 — Analytics deep dive

- **What happens:** Click the Analytics tab. Show the charts now populated with the demo's data.
- **Panel sees:**
  - Total Boardings reflects everything from the demo
  - Peak Hour, Most Popular Stop visible
  - Booking Funnel: reservations vs completions
  - No-Show Rate by Stop
  - Adoption over time, day of week patterns

---

## Pre-Demo Checklist

### Database state

- [ ] Run service-day reset (set count to 0)
- [ ] Wipe stale May 4 test data from passenger_events (optional but recommended)
- [ ] Set shuttle to Western Gate (current_stop_index = 0)
- [ ] Confirm Firebase has the right pre-seeded bookings for the 12 scenarios

### Pre-seeded bookings in Firebase

- [ ] Alice → Western Gate → CONAS (reserved)
- [ ] Bob → Western Gate → Africa Hall (reserved)
- [ ] Carla → Western Gate → CONAS (reserved)
- [ ] Daniel → CEDAT → Main Library (reserved)
- [ ] Elena → CEDAT → Africa Hall (reserved)
- [ ] Frank → COCIS (reserved, to be cancelled by Cissy in Scenario 6)
- [ ] One more for the no-show at Swimming Pool
- [ ] Forged QR test record for Scenario 8

### Video files to record

- [ ] `western_gate_3_board.mp4` (3 people boarding)
- [ ] `cedat_2_board.mp4` (2 people boarding)
- [ ] `conas_2_alight.mp4` (Alice + Carla alighting)
- [ ] `main_library_1_alight.mp4` (Daniel alighting)
- [ ] `africa_hall_1_alight.mp4` (Bob OR Elena alighting depending on script)
- [ ] `swimming_pool_empty.mp4` (no movement, for no-show scenario)
- [ ] `cocis_overflow.mp4` (capacity + 1 extra person trying to enter)

### Hardware/setup

- [ ] Laptop charged
- [ ] Two phones for Cissy's app (passenger + maybe second user)
- [ ] Dashboard open in browser, logged in
- [ ] Terminal 1 ready for `python dashboard.py`
- [ ] Terminal 2 ready for `python qr_scanner_runtime.py`
- [ ] Firebase console open in another tab (just in case)
- [ ] Backup video files in case live AI struggles
- [ ] Test the YOLOv8n fine-tuned model on shuttle-specific data (Phase 10)

### Practice runs

- [ ] Full run-through #1 with team alone
- [ ] Full run-through #2 with a friend acting as panelist
- [ ] Time each scenario to confirm pacing
- [ ] Identify which scenarios feel weak and either strengthen or drop

---

## Open Questions Before Demo Day

- [ ] Confirm with Cissy: does mobile app support user-cancellation (Scenario 6)?
- [ ] Confirm with Cissy: does mobile app refuse booking when shuttle is full (Scenario 9)?
- [ ] Decide: who narrates each phase? (suggest Elsa narrates technical/dashboard, Cissy narrates passenger flow)
- [ ] Decide: final passenger names (Alice/Bob/Carla style, or use real student names)
- [ ] Decide: include offline-mode scenario or skip (time tradeoff)

---

## Architectural Pillars to Cover

The 12 scenarios above hit all 4 pillars of the system. Quick mapping for the panel:

| Pillar                          | Demonstrated in                                           |
| ------------------------------- | --------------------------------------------------------- |
| Booking + QR scanning           | Scenarios 1, 2, 6, 7, 8                                   |
| AI counting (YOLOv8 + DeepSORT) | Every scenario where main.py runs                         |
| Real-time dashboard             | Throughout, especially Scenarios 10, 11, 12               |
| Mobile passenger experience     | Scenarios 1-2 (booking), 6 (cancel), 9 (capacity refusal) |
| Safety & observability          | Scenarios 8, 10, 11                                       |
| Operational optimization        | Scenarios 3, 4, 5                                         |

---

## Mental Note for Future Improvement (POST-DEMO)

**Soft-hold reservation model needs revisiting.**

Currently `reserved` bookings do NOT decrement available_seats — only `active` (scanned) bookings do. This means User A and User B can each reserve "the last seat" simultaneously, and only one actually gets it when they arrive.

**Better model:** `reserved` should also decrement available_seats (a true seat hold). Cancellation/no-show should increment it back. Requires sync with Cissy's app which reads available_seats from Firebase.

This is a real architectural improvement to discuss with Cissy after the project closes.
