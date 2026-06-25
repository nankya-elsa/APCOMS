import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/material.dart';

import '../../models/booking_availability.dart';
import '../../models/user_profile.dart';
import '../../models/booking_record.dart';
import '../../services/auth_service.dart';
import '../../services/booking_service.dart';
import '../my_bookings_screen.dart';
import '../booking_screen.dart';

class DashboardHomeTab extends StatelessWidget {
  const DashboardHomeTab({
    super.key,
    required this.uid,
    required this.trackedShuttleKey,
  });

  final String uid;
  final String trackedShuttleKey;

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<UserProfile?>(
      stream: const AuthService().watchUserProfile(uid),
      builder: (context, profileSnapshot) {
        final profile = profileSnapshot.data;

        final firstName = (profile?.firstName ?? '').trim();
        final nameText = firstName.isEmpty ? 'User' : firstName;
        final greeting = _timeGreeting(DateTime.now());
        final role = (profile?.role ?? '').trim();

        final avatar = _Avatar(
          photoUrl: FirebaseAuth.instance.currentUser?.photoURL,
          nameFallback: nameText,
        );

        return SafeArea(
          child: Padding(
            padding: const EdgeInsets.fromLTRB(16, 36, 16, 16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                Row(
                  children: [
                    avatar,
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            greeting,
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(color: Colors.black54),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            nameText,
                            style: Theme.of(context)
                                .textTheme
                                .titleMedium
                                ?.copyWith(fontWeight: FontWeight.w700),
                          ),
                        ],
                      ),
                    ),
                    if (role.isNotEmpty) _RolePill(role: role),
                  ],
                ),

                const SizedBox(height: 20),

                _ShuttleCard(trackedShuttleKey: trackedShuttleKey),

                const SizedBox(height: 14),

                Text(
                  'Booking',
                  style: Theme.of(context)
                      .textTheme
                      .titleSmall
                      ?.copyWith(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 8),

                _BookingEntryCard(
                  trackedShuttleKey: trackedShuttleKey,
                  uid: uid,
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  static String _timeGreeting(DateTime now) {
    final h = now.hour;
    if (h < 12) return 'Good morning,';
    if (h < 17) return 'Good afternoon,';
    return 'Good evening,';
  }
}

class _Avatar extends StatelessWidget {
  const _Avatar({required this.photoUrl, required this.nameFallback});

  final String? photoUrl;
  final String nameFallback;

  @override
  Widget build(BuildContext context) {
    final initial = nameFallback.isEmpty ? '?' : nameFallback.characters.first;
    final photo = photoUrl?.trim();
    final hasPhoto = photo?.isNotEmpty ?? false;
    return CircleAvatar(
      radius: 22,
      backgroundColor: hasPhoto
          ? Theme.of(context).colorScheme.primaryContainer
          : Colors.amber.shade200,
      foregroundImage: hasPhoto ? NetworkImage(photo!) : null,
      child: Text(
        initial.toUpperCase(),
        style: Theme.of(context)
            .textTheme
            .titleMedium
            ?.copyWith(fontWeight: FontWeight.w700),
      ),
    );
  }
}

class _RolePill extends StatelessWidget {
  const _RolePill({required this.role});

  final String role;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: Color.alphaBlend(
          scheme.primaryContainer.withValues(alpha: 0.6),
          Colors.white,
        ),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: scheme.primary.withValues(alpha: 0.18)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.verified, size: 16, color: scheme.primary),
          const SizedBox(width: 6),
          Text(
            role,
            style: Theme.of(context).textTheme.labelMedium?.copyWith(
              color: scheme.primary,
              fontWeight: FontWeight.w600,
            ),
          ),
        ],
      ),
    );
  }
}

class _ShuttleCard extends StatelessWidget {
  const _ShuttleCard({required this.trackedShuttleKey});

  final String trackedShuttleKey;

  // ── The one true offline signal for Firebase RTDB ─────────────────────────
  // .info/connected is false the moment the SDK loses its server connection,
  // even though data streams keep emitting from the local disk cache silently.
  static Stream<bool> get _connectedStream => FirebaseDatabase.instance
      .ref('.info/connected')
      .onValue
      .map((event) => event.snapshot.value == true);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ref = FirebaseDatabase.instance
        .ref()
        .child('shuttles')
        .child(trackedShuttleKey);

    return StreamBuilder<bool>(
      // Default to true (connected) until we hear otherwise so the card
      // doesn't flash "offline" on startup before the first event arrives.
      initialData: true,
      stream: _connectedStream,
      builder: (context, connectedSnapshot) {
        final isConnected = connectedSnapshot.data ?? true;

        return StreamBuilder<BookingAvailability>(
          stream: BookingService().watchAvailability(
            shuttleKey: trackedShuttleKey,
            persistDerived: false,
          ),
          builder: (context, availabilitySnapshot) {
            final availability = availabilitySnapshot.data;

            return StreamBuilder<DatabaseEvent>(
              stream: ref.onValue,
              builder: (context, snapshot) {
                // Still waiting for first cache/server event and no
                // BookingService cache yet — show spinner.
                if (snapshot.connectionState == ConnectionState.waiting &&
                    availability == null) {
                  return _cardShell(context, child: const _CardLoading());
                }

                // Firebase errored (e.g. permission denied) with no cache.
                if (snapshot.hasError && availability == null) {
                  return _cardShell(
                    context,
                    child: _FullOfflineBanner(
                      message:
                          'No cached data available. Connect to the internet to load shuttle information.',
                    ),
                  );
                }

                final raw = snapshot.data?.snapshot.value;
                final data = raw is Map
                    ? Map<String, Object?>.from(raw)
                    : const <String, Object?>{};

                final locationRaw = data['location'];
                final location = locationRaw is Map
                    ? Map<String, Object?>.from(locationRaw)
                    : null;

                // When offline, Firebase serves its local disk cache so
                // data values are still present — we use them as-is.
                // We only fall back to BookingService cache when data is
                // completely empty (first-ever launch with no internet).
                final hasLiveOrCachedFirebaseData = raw != null;

                final rawAvailableSeats = hasLiveOrCachedFirebaseData
                    ? _readInt(data['available_seats'])
                    : (availability?.reportedAvailableSeats ?? 0);
                final occupiedSeats = hasLiveOrCachedFirebaseData
                    ? _readInt(data['current_count'])
                    : (availability?.occupiedSeats ?? 0);
                final reservedSeats = availability?.reservedSeats ?? 0;
                final availableSeats = rawAvailableSeats.clamp(0, 999).toInt();

                final occupancyStatus =
                    (data['occupancy_status'] as String?)?.trim();
                final currentStop = (((data['current_stop'] as String?) ??
                            (location?['current_stop'] as String?)) ??
                        '')
                    .trim();
                final nextStop = (((data['next_stop'] as String?) ??
                            (location?['next_stop'] as String?)) ??
                        '')
                    .trim();

                final normalizedStatus = (occupancyStatus ?? '').toLowerCase();
                final isFull = availableSeats <= 0 ||
                    normalizedStatus == 'full';

                final freeBg = Color.alphaBlend(
                  scheme.primaryContainer.withValues(alpha: 0.55),
                  Colors.white,
                );
                final occupiedBg = Color.alphaBlend(
                  scheme.errorContainer.withValues(alpha: 0.55),
                  Colors.white,
                );
                final statusBg = isFull
                    ? Color.alphaBlend(
                        scheme.errorContainer.withValues(alpha: 0.6),
                        Colors.white,
                      )
                    : Color.alphaBlend(
                        scheme.primaryContainer.withValues(alpha: 0.6),
                        Colors.white,
                      );
                final statusFg = isFull ? scheme.error : scheme.primary;
                final statusTitle = isFull
                    ? 'This shuttle is full'
                    : '${availableSeats.clamp(0, 999)} seats available!';
                final statusSubtitle =
                    isFull ? 'Select another shuttle' : 'Head to the next stop';

                // Build an effective availability for the staleness pill.
                // isStale=true whenever we are not connected to Firebase.
                final effectiveAvailability = availability ??
                    BookingAvailability(
                      reportedAvailableSeats: rawAvailableSeats,
                      occupiedSeats: occupiedSeats,
                      reservedSeats: reservedSeats,
                      isStale: !isConnected,
                    );

                final pillAvailability = !isConnected
                    ? BookingAvailability(
                        reportedAvailableSeats:
                            effectiveAvailability.reportedAvailableSeats,
                        occupiedSeats: effectiveAvailability.occupiedSeats,
                        reservedSeats: effectiveAvailability.reservedSeats,
                        lastComputedAt: effectiveAvailability.lastComputedAt,
                        isStale: true,
                      )
                    : effectiveAvailability;

                return _cardShell(
                  context,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // ── Header: logo + live/offline pill ─────────────────
                      Row(
                        children: [
                          Image.asset(
                            'assets/images/logo.png',
                            height: 22,
                            fit: BoxFit.contain,
                          ),
                          const Spacer(),
                          _StalenessPill(availability: pillAvailability),
                        ],
                      ),

                      // ── Inline offline notice ─────────────────────────────
                      // Shown whenever .info/connected is false, regardless of
                      // whether Firebase errored or served from its local cache.
                      if (!isConnected) ...[
                        const SizedBox(height: 8),
                        _InlineOfflineNotice(
                          lastSeen: effectiveAvailability.lastComputedAt,
                        ),
                      ],

                      const SizedBox(height: 10),

                      // ── Seat stats ────────────────────────────────────────
                      Row(
                        children: [
                          Expanded(
                            child: _StatBox(
                              value: availableSeats,
                              label: 'Free seats',
                              background: freeBg,
                              foreground: scheme.primary,
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: _StatBox(
                              value: occupiedSeats,
                              label: 'Occupied',
                              background: occupiedBg,
                              foreground: scheme.error,
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: _StatBox(
                              value: reservedSeats,
                              label: 'Reserved',
                              background: scheme.surface,
                              foreground: scheme.onSurface,
                              borderColor: scheme.outlineVariant,
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),

                      // ── Current & next stop ───────────────────────────────
                      Row(
                        children: [
                          Icon(
                            Icons.place_outlined,
                            size: 16,
                            color: scheme.primary,
                          ),
                          const SizedBox(width: 4),
                          Text(
                            'At: ${currentStop.isEmpty ? '—' : currentStop}',
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(color: scheme.onSurfaceVariant),
                          ),
                          const SizedBox(width: 10),
                          Icon(
                            Icons.arrow_forward,
                            size: 14,
                            color: scheme.onSurfaceVariant,
                          ),
                          const SizedBox(width: 4),
                          Expanded(
                            child: Text(
                              'Next: ${nextStop.isEmpty ? '—' : nextStop}',
                              maxLines: 1,
                              overflow: TextOverflow.ellipsis,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(color: scheme.onSurfaceVariant),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),

                      // ── Availability status banner ─────────────────────────
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: statusBg,
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              statusTitle,
                              style: Theme.of(context)
                                  .textTheme
                                  .titleSmall
                                  ?.copyWith(
                                    color: statusFg,
                                    fontWeight: FontWeight.w700,
                                  ),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              statusSubtitle,
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(
                                    color: statusFg.withValues(alpha: 0.85),
                                  ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                );
              },
            );
          },
        );
      },
    );
  }

  static int _readInt(Object? value) {
    if (value is int) return value;
    if (value is double) return value.round();
    if (value is String) return int.tryParse(value) ?? 0;
    return 0;
  }

  static Widget _cardShell(BuildContext context, {required Widget child}) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Color.alphaBlend(
          scheme.primaryContainer.withValues(alpha: 0.12),
          Colors.white,
        ),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: scheme.outlineVariant.withValues(alpha: 0.22),
        ),
      ),
      child: child,
    );
  }
}

// ── Inline notice shown inside the card when offline ────────────────────────
class _InlineOfflineNotice extends StatelessWidget {
  const _InlineOfflineNotice({required this.lastSeen});

  final int? lastSeen;

  String _fmt(int? ms) {
    if (ms == null) return 'unknown time';
    final dt = DateTime.fromMillisecondsSinceEpoch(ms).toLocal();
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    const months = [
      'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
      'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
    ];
    return '${months[dt.month - 1]} ${dt.day} at $h:$m';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: Color.alphaBlend(
          scheme.errorContainer.withValues(alpha: 0.18),
          Colors.white,
        ),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: scheme.error.withValues(alpha: 0.18)),
      ),
      child: Row(
        children: [
          Icon(Icons.wifi_off_rounded, size: 14, color: scheme.error),
          const SizedBox(width: 6),
          Expanded(
            child: Text(
              'You\'re offline. Showing data from ${_fmt(lastSeen)}.',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: scheme.error),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Full replacement when offline with zero cached data ─────────────────────
class _FullOfflineBanner extends StatelessWidget {
  const _FullOfflineBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        Container(
          padding: const EdgeInsets.all(8),
          decoration: BoxDecoration(
            color: scheme.errorContainer.withValues(alpha: 0.4),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(Icons.wifi_off_rounded, size: 20, color: scheme.error),
        ),
        const SizedBox(width: 12),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(
                'Offline',
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: scheme.error,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 2),
              Text(
                message,
                style: Theme.of(context)
                    .textTheme
                    .bodySmall
                    ?.copyWith(color: scheme.onSurfaceVariant),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _StatBox extends StatelessWidget {
  const _StatBox({
    required this.value,
    required this.label,
    required this.background,
    required this.foreground,
    this.borderColor,
  });

  final int value;
  final String label;
  final Color background;
  final Color foreground;
  final Color? borderColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(10),
        border: borderColor == null ? null : Border.all(color: borderColor!),
      ),
      child: Column(
        children: [
          Text(
            '$value',
            style: Theme.of(context).textTheme.titleLarge?.copyWith(
              fontWeight: FontWeight.w800,
              color: foreground,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.labelSmall?.copyWith(
              color: foreground.withValues(alpha: 0.9),
            ),
          ),
        ],
      ),
    );
  }
}

class _StalenessPill extends StatelessWidget {
  const _StalenessPill({required this.availability});

  final BookingAvailability availability;

  String _fmt(int? ms) {
    if (ms == null) return 'unknown';
    final dt = DateTime.fromMillisecondsSinceEpoch(ms);
    final h = dt.hour.toString().padLeft(2, '0');
    final m = dt.minute.toString().padLeft(2, '0');
    return '$h:$m';
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    if (availability.isStale) {
      return Container(
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
        decoration: BoxDecoration(
          color: Color.alphaBlend(
            scheme.errorContainer.withValues(alpha: 0.12),
            Colors.white,
          ),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: scheme.error.withValues(alpha: 0.12)),
        ),
        child: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.wifi_off_rounded, size: 14, color: scheme.error),
            const SizedBox(width: 4),
            Text(
              'Offline • ${_fmt(availability.lastComputedAt)}',
              style: Theme.of(context)
                  .textTheme
                  .bodySmall
                  ?.copyWith(color: scheme.error),
            ),
          ],
        ),
      );
    }

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
      decoration: BoxDecoration(
        color: Color.alphaBlend(
          scheme.primaryContainer.withValues(alpha: 0.12),
          Colors.white,
        ),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.primary.withValues(alpha: 0.12)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(Icons.wifi, size: 14, color: scheme.primary),
          const SizedBox(width: 6),
          Text(
            'Live',
            style: Theme.of(context)
                .textTheme
                .bodySmall
                ?.copyWith(color: scheme.primary),
          ),
        ],
      ),
    );
  }
}

class _CardLoading extends StatelessWidget {
  const _CardLoading();

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        const SizedBox(
          width: 18,
          height: 18,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
        const SizedBox(width: 10),
        Text(
          'Loading shuttle…',
          style: Theme.of(context).textTheme.bodyMedium,
        ),
      ],
    );
  }
}

class _BookingEntryCard extends StatelessWidget {
  const _BookingEntryCard({
    required this.trackedShuttleKey,
    required this.uid,
  });

  final String trackedShuttleKey;
  final String uid;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return StreamBuilder<List<BookingRecord>>(
      stream: BookingService().watchUserBookings(userUid: uid),
      builder: (context, snapshot) {
        final bookings = snapshot.data ?? const <BookingRecord>[];
        final hasAnyActiveOrReserved = bookings.any((b) => b.isActive);
        final hasOnTrip = bookings.any(
          (b) => (b.status).toLowerCase() == 'active',
        );
        final hasReservedOnly = hasAnyActiveOrReserved && !hasOnTrip;

        void action() {
          if (hasAnyActiveOrReserved) {
            Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => MyBookingsScreen()),
            );
            return;
          }
          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) =>
                  BookingScreen(trackedShuttleKey: trackedShuttleKey),
            ),
          );
        }

        final buttonLabel = hasAnyActiveOrReserved
            ? (hasOnTrip ? 'On Trip' : 'View Booking')
            : 'Book Now';

        return Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: action,
            borderRadius: BorderRadius.circular(16),
            child: Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(
                color: Color.alphaBlend(
                  scheme.primaryContainer.withValues(alpha: 0.12),
                  Colors.white,
                ),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                  color: scheme.outlineVariant.withValues(alpha: 0.22),
                ),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      Container(
                        width: 44,
                        height: 44,
                        decoration: BoxDecoration(
                          color: Color.alphaBlend(
                            scheme.primaryContainer.withValues(alpha: 0.55),
                            Colors.white,
                          ),
                          borderRadius: BorderRadius.circular(12),
                        ),
                        child: Icon(Icons.event_seat, color: scheme.primary),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              hasOnTrip
                                  ? 'You are on a trip'
                                  : hasReservedOnly
                                      ? 'You have a reserved booking'
                                      : 'Book a seat',
                              style: Theme.of(context)
                                  .textTheme
                                  .titleSmall
                                  ?.copyWith(fontWeight: FontWeight.w800),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              hasOnTrip
                                  ? 'Scanner detected you as onboard. Safe travels! Details unavailable while onboard.'
                                  : hasReservedOnly
                                      ? 'Cancel or complete it to make a new booking'
                                      : 'Choose pick up and destination',
                              style: Theme.of(context)
                                  .textTheme
                                  .bodySmall
                                  ?.copyWith(color: scheme.onSurfaceVariant),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    height: 44,
                    child: FilledButton(
                      onPressed: hasOnTrip ? null : action,
                      child: Text(buttonLabel),
                    ),
                  ),
                ],
              ),
            ),
          ),
        );
      },
    );
  }
}