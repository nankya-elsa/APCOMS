# TODO: future enhancement — Firebase resilience
    #
    # Two known limitations with the current queue+retry approach:
    #
    # 1. Periodic drain timing
    #    The pending_cancellations queue only drains when
    #    cancel_no_shows() is called, which happens once per
    #    shuttle stop transition (every few minutes). Queued
    #    cancellations from prior Firebase outages can therefore
    #    sit for several minutes before being applied. For
    #    production, a periodic background drain (every 30 seconds)
    #    would tighten this to near-realtime.
    #
    # 2. Query-side failures
    #    The queue only protects against WRITE failures (cancel_one
    #    couldn't reach Firebase). If find_no_show_bookings fails
    #    because Firebase is unreachable for the QUERY, we never
    #    discover the no-shows in the first place — so nothing gets
    #    queued. Those bookings remain 'reserved' until the next
    #    successful advance_and_sync with network. The booker keeps
    #    their seat in the app until then, which is arguably the
    #    correct behaviour (we shouldn't pretend a cancellation
    #    happened when we can't verify ground truth).
    #
    # The broader fix would be a local mirror cache of Firebase
    # bookings (similar to firebase_sync's offline queue for
    # occupancy updates, but for reads). That's a system-wide
    # design decision that affects BookingValidator, BookingCompleter,
    # and any other component that reads Firebase — better tackled
    # as a dedicated phase than retrofitted to one component.
