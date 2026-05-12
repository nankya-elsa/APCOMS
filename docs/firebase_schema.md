# APCOMS Firebase Schema Reference

This document describes the Firebase Realtime Database schema used by APCOMS, defining how data flows between the three subsystems (Counting Module, Mobile Application, and QR Scanner).

This is a living reference — updates to the schema should be reflected here. The schema is intentionally backward-compatible with existing mobile app code; new fields are added optionally rather than as breaking changes.

---

## Top-Level Structure

```
firebase-root/
  ├── shuttles/
  │   └── {shuttle_id}/      ← live shuttle state
  ├── bookings/
  │   └── {booking_id}/      ← global booking records
  └── user_bookings/
      └── {user_uid}/
          └── {booking_id}/  ← per-user mirror of bookings
```

---

## `/shuttles/{shuttle_id}`

Live state of a shuttle. Written by the counting module's `firebase_sync.py`, read by the mobile app and admin dashboard.

| Field              | Type      | Written by      | Description                                  |
| ------------------ | --------- | --------------- | -------------------------------------------- |
| `shuttle_id`       | string    | Counting Module | Unique identifier (e.g. `shuttle_001`)       |
| `current_count`    | int       | Counting Module | Number of passengers currently onboard       |
| `available_seats`  | int       | Counting Module | Capacity minus current_count                 |
| `occupancy_status` | string    | Counting Module | One of: `Available`, `Nearly Full`, `Full`   |
| `current_stop`     | string    | Counting Module | Name of the stop the shuttle is currently at |
| `next_stop`        | string    | Counting Module | Name of the next stop in the loop            |
| `last_updated`     | timestamp | Counting Module | When the counts were last synced             |

---

## `/bookings/{booking_id}`

Global booking records. Created by Cissy's mobile app via `BookingService.createBooking()`. Status transitions are managed by all three subsystems depending on the lifecycle event.

### Core fields (written at booking creation)

| Field               | Type      | Description                                                                          |
| ------------------- | --------- | ------------------------------------------------------------------------------------ |
| `booking_id`        | string    | Firebase push key, also stored in the record for convenience                         |
| `shuttle_key`       | string    | Which shuttle this booking is for (e.g. `shuttle_001`)                               |
| `user_uid`          | string    | Firebase Auth UID of the user who booked                                             |
| `pickup_stop`       | string    | Display name of pickup stop (e.g. `Western Gate`)                                    |
| `pickup_index`      | int       | Index of pickup stop in the designated stops list                                    |
| `destination_stop`  | string    | Display name of destination stop                                                     |
| `destination_index` | int       | Index of destination stop in the designated stops list                               |
| `status`            | string    | Current lifecycle state (see Status Lifecycle below)                                 |
| `qr_payload`        | string    | JSON string containing booking validation data                                       |
| `qr_token`          | string    | Random 16-character anti-forgery token. Must match the `t` field in `qr_payload`.    |
| `created_at`        | timestamp | Server timestamp when booking was created                                            |

### Lifecycle fields (added as the booking progresses)

These fields are optional and only present once the relevant event has occurred. They are added by the system without rewriting unrelated fields.

| Field           | Type      | Added by                      | When                                         |
| --------------- | --------- | ----------------------------- | -------------------------------------------- |
| `boarded_at`    | timestamp | QR Scanner                    | When user scans QR and is validated          |
| `completed_at`  | timestamp | Counting Module               | When matching alighting is detected          |
| `cancelled_at`  | timestamp | Mobile App or Counting Module | When booking is cancelled (manually or auto) |
| `cancel_reason` | string    | Mobile App or Counting Module | Reason for cancellation (see Cancel Reasons) |

### QR Payload structure

The `qr_payload` field is a JSON-encoded string. When decoded:

```json
{
  "v": 1,
  "bookingId": "-OsQZ9PF7woPSEOL5xy_",
  "t": "MnD8JprztIircEoK"
}
```

The payload is intentionally minimal — just the booking ID and a short anti-forgery token. All other booking details (pickup, destination, user, etc.) are fetched from the booking record itself once the ID is known.

The `t` field must match the `qr_token` stored on the booking record. This prevents an attacker from learning a `bookingId` (which might appear in logs) and forging a valid QR. Without the correct token, scans are rejected with reason `invalid_token`.

The QR scanner validates by parsing the payload, looking up `bookingId` in `/bookings/`, then checking status, pickup match, and token match.

---

## `/user_bookings/{user_uid}/{booking_id}`

Per-user mirror of bookings. Allows the mobile app to query a user's bookings without needing access to the global `/bookings/` collection. Written atomically alongside `/bookings/{id}` using Firebase multi-path updates.

The schema mirrors `/bookings/{id}` exactly. Updates to one path must be reflected in the other to keep them in sync.

---

## Status Lifecycle

A booking transitions through these states during its lifetime:

| Status      | Source                                      | Meaning                                                |
| ----------- | ------------------------------------------- | ------------------------------------------------------ |
| `reserved`  | Mobile App (on creation)                    | Booked but not yet boarded. Seat is held.              |
| `active`    | QR Scanner (on valid scan)                  | QR scanned, person has boarded the shuttle.            |
| `completed` | Counting Module (on alighting)              | Person alighted at their destination stop.             |
| `cancelled` | Mobile App (user) or Counting Module (auto) | Cancelled by user or auto-cancelled at pickup no-show. |

### Valid transitions

```
       ┌─────────────┐
       │  reserved   │ ← created by Cissy's app
       └──────┬──────┘
              │
       ┌──────┴──────┬──────────────┐
       │             │              │
       ▼             ▼              ▼
  ┌─────────┐  ┌───────────┐  ┌──────────┐
  │ active  │  │ cancelled │  │ cancelled│
  │(scanned)│  │  (user)   │  │  (auto)  │
  └────┬────┘  └───────────┘  └──────────┘
       │
       ▼
  ┌───────────┐
  │ completed │ ← marked on alighting
  └───────────┘
```

Once a booking reaches `completed` or `cancelled`, it is terminal — no further transitions occur.

### Backward compatibility note

Cissy's existing mobile app code only checks `isActive` (defined as `status == 'reserved'`). Adding the `active` and `completed` statuses does not break existing logic — bookings in those states will simply be treated as not-active by the existing code, which is correct (they're no longer awaiting boarding).

---

## Cancel Reasons

When a booking is cancelled, the `cancel_reason` field records why. Standard values:

| Reason              | Source          | Meaning                                                   |
| ------------------- | --------------- | --------------------------------------------------------- |
| `user_cancelled`    | Mobile App      | User tapped cancel in the app                             |
| `no_show_at_pickup` | Counting Module | Shuttle left the pickup stop without the QR being scanned |

Future reasons may be added — code should treat unknown reasons gracefully and not assume the list is exhaustive.

---

## Data Ownership

To prevent race conditions and unclear responsibility, each Firebase path has a single owner that writes to it. Other subsystems may read freely.

| Path / Field                               | Written by                               | Read by                     |
| ------------------------------------------ | ---------------------------------------- | --------------------------- |
| `/shuttles/{id}/*` (all live state)        | Counting Module                          | Mobile App, Admin Dashboard |
| `/bookings/{id}` (create)                  | Mobile App                               | All subsystems              |
| `/bookings/{id}/status → active`           | QR Scanner                               | Mobile App                  |
| `/bookings/{id}/status → completed`        | Counting Module                          | Mobile App                  |
| `/bookings/{id}/status → cancelled (auto)` | Counting Module                          | Mobile App                  |
| `/bookings/{id}/status → cancelled (user)` | Mobile App                               | All subsystems              |
| `/user_bookings/{uid}/{id}`                | Same writer as `/bookings/{id}` (mirror) | Mobile App                  |

---

## Validation Rules at QR Scan

When the QR scanner reads a QR code, it validates against these rules in order before transitioning a booking to `active`:

1. The QR payload must parse as JSON containing both `bookingId` and `t` fields
2. The `bookingId` from the payload must exist in `/bookings/`
3. The booking's `status` must be `reserved` (re-scanning a reserved booking is allowed in case of glitches)
4. The booking's `pickup_stop` must equal the shuttle's `current_stop`
5. The `t` field in the payload must equal the booking's `qr_token` (anti-forgery)

If any check fails, the scanner displays the rejection reason and does not modify Firebase state.

Once all checks pass, the scanner updates `/bookings/{id}/status` to `active` and adds `boarded_at`. The same update is mirrored to `/user_bookings/{uid}/{id}`.

---

## Looping Routes and Destination

The shuttle follows a continuous loop:

```
Western Gate → CEDAT → CONAS → Main Library → Africa Hall →
Swimming Pool → Mitchell Hall → COCIS → Complex Hall →
CEES → Lumumba Hall → (back to Western Gate)
```

Because the route loops, every destination is always reachable from every current stop. Destination validation is therefore not enforced at scan time — only the pickup stop must match.

---

## Notes for Implementers

- All Firebase writes from the counting module should use atomic multi-path updates when writing to multiple paths simultaneously (the same pattern Cissy's code already uses).
- Timestamps should always be `ServerValue.timestamp` (server-side) rather than client clock values, to avoid timezone and drift issues.
- The QR payload is a JSON string, not a JSON object. Decode it before validation.
- Treat the schema as additive, never remove fields, only add new optional ones.
