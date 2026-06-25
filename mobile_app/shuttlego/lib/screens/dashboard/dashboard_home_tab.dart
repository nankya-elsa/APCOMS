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
import '../dashboard_screen.dart'; // for ShuttleOption

class DashboardHomeTab extends StatelessWidget {
  const DashboardHomeTab({
    super.key,
    required this.uid,
    required this.trackedShuttleKey,
    required this.availableShuttles,
    required this.onShuttleChanged,
  });

  final String uid;
  final String trackedShuttleKey;
  final List<ShuttleOption> availableShuttles;
  final ValueChanged<String> onShuttleChanged;

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

        // Resolve display name for the selected shuttle.
        final selectedShuttle = availableShuttles.firstWhere(
          (s) => s.key == trackedShuttleKey,
          orElse: () =>
              ShuttleOption(key: trackedShuttleKey, name: trackedShuttleKey),
        );

        return SafeArea(
          child: SingleChildScrollView(
            padding: const EdgeInsets.fromLTRB(16, 36, 16, 24),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.stretch,
              children: [
                // ── Greeting row ──────────────────────────────────────────
                Row(
                  children: [
                    _Avatar(
                      photoUrl: FirebaseAuth.instance.currentUser?.photoURL,
                      nameFallback: nameText,
                    ),
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

                // ── Shuttle selector — always shown ───────────────────────
                _ShuttleDropdown(
                  shuttles: availableShuttles,
                  selectedKey: trackedShuttleKey,
                  onChanged: onShuttleChanged,
                ),

                const SizedBox(height: 14),

                // ── Shuttle info card ─────────────────────────────────────
                _ShuttleCard(
                  trackedShuttleKey: trackedShuttleKey,
                  shuttleDisplayName: selectedShuttle.name,
                ),

                const SizedBox(height: 14),

                // ── Booking section ───────────────────────────────────────
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

// ── Shuttle dropdown ──────────────────────────────────────────────────────────
class _ShuttleDropdown extends StatelessWidget {
  const _ShuttleDropdown({
    required this.shuttles,
    required this.selectedKey,
    required this.onChanged,
  });

  final List<ShuttleOption> shuttles;
  final String selectedKey;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    // Guard: if selectedKey isn't in the list yet, fall back to first item.
    final safeValue = shuttles.any((s) => s.key == selectedKey)
        ? selectedKey
        : (shuttles.isNotEmpty ? shuttles.first.key : selectedKey);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          'Select Shuttle',
          style: Theme.of(context)
              .textTheme
              .titleSmall
              ?.copyWith(fontWeight: FontWeight.w700),
        ),
        const SizedBox(height: 8),
        Container(
          decoration: BoxDecoration(
            color: Color.alphaBlend(
              scheme.primaryContainer.withValues(alpha: 0.10),
              Colors.white,
            ),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: scheme.outlineVariant.withValues(alpha: 0.5),
            ),
          ),
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
          child: DropdownButtonHideUnderline(
            child: DropdownButton<String>(
              isExpanded: true,
              value: safeValue,
              icon: Icon(Icons.keyboard_arrow_down_rounded,
                  color: scheme.primary),
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: scheme.onSurface,
                    fontWeight: FontWeight.w600,
                  ),
              onChanged: (value) {
                if (value != null) onChanged(value);
              },
              items: shuttles.map((shuttle) {
                final isSelected = shuttle.key == safeValue;
                return DropdownMenuItem<String>(
                  value: shuttle.key,
                  child: Row(
                    children: [
                      Icon(
                        Icons.directions_bus_rounded,
                        size: 18,
                        color: isSelected
                            ? scheme.primary
                            : scheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 10),
                      Text(shuttle.name),
                    ],
                  ),
                );
              }).toList(),
            ),
          ),
        ),
      ],
    );
  }
}

// ── Avatar ────────────────────────────────────────────────────────────────────
class _Avatar extends StatelessWidget {
  const _Avatar({required this.photoUrl, required this.nameFallback});

  final String? photoUrl;
  final String nameFallback;

  @override
  Widget build(BuildContext context) {
    final initial = nameFallback.isEmpty ? '?' : nameFallback.characters.first;
    final photo = photoUrl?.trim();
    final hasPhoto = photo != null && photo.isNotEmpty;
    return CircleAvatar(
      radius: 22,
      backgroundColor: hasPhoto
          ? Theme.of(context).colorScheme.primaryContainer
          : Colors.amber.shade200,
      foregroundImage: hasPhoto ? NetworkImage(photo) : null,
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

// ── Role pill ─────────────────────────────────────────────────────────────────
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

// ── Shuttle card ──────────────────────────────────────────────────────────────
class _ShuttleCard extends StatelessWidget {
  const _ShuttleCard({
    required this.trackedShuttleKey,
    required this.shuttleDisplayName,
  });

  final String trackedShuttleKey;
  final String shuttleDisplayName;

  static Stream<bool> get _connectedStream => FirebaseDatabase.instance
      .ref('.info/connected')
      .onValue
      .map((event) => event.snapshot.value == true);

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ref = FirebaseDatabase.instance
        .ref('shuttles')
        .child(trackedShuttleKey);

    return StreamBuilder<bool>(
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
                // Waiting with no cache yet — show spinner.
                if (snapshot.connectionState == ConnectionState.waiting &&
                    availability == null) {
                  return _cardShell(
                    context,
                    scheme: scheme,
                    child: const _CardLoading(),
                  );
                }

                // Error with no cache — show offline banner.
                if (snapshot.hasError && availability == null) {
                  return _cardShell(
                    context,
                    scheme: scheme,
                    child: const _FullOfflineBanner(
                      message:
                          'No cached data available. Connect to the internet to load shuttle information.',
                    ),
                  );
                }

                final raw = snapshot.data?.snapshot.value;
                final data = raw is Map
                    ? Map<String, Object?>.from(raw)
                    : const <String, Object?>{};

                final hasFirebaseData = raw != null;

                final rawAvailableSeats = hasFirebaseData
                    ? _readInt(data['available_seats'])
                    : (availability?.reportedAvailableSeats ?? 0);
                final occupiedSeats = hasFirebaseData
                    ? _readInt(data['current_count'])
                    : (availability?.occupiedSeats ?? 0);
                final reservedSeats = availability?.reservedSeats ?? 0;
                final availableSeats =
                    rawAvailableSeats.clamp(0, 999).toInt();

                final occupancyStatus =
                    (data['occupancy_status'] as String?)?.trim() ?? '';
                final currentStop =
                    ((data['current_stop'] as String?) ?? '').trim();
                final nextStop =
                    ((data['next_stop'] as String?) ?? '').trim();

                final isFull = availableSeats <= 0 ||
                    occupancyStatus.toLowerCase() == 'full';

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
                    : '$availableSeats seats available!';
                final statusSubtitle = isFull
                    ? 'Select another shuttle'
                    : 'Head to the next stop';

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
                  scheme: scheme,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      // ── Card header: logo + shuttle name badge + live pill
                      Row(
                        children: [
                          Image.asset(
                            'assets/images/logo.png',
                            height: 22,
                            fit: BoxFit.contain,
                          ),
                          const SizedBox(width: 8),
                          // Shuttle name badge
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: Color.alphaBlend(
                                scheme.primaryContainer
                                    .withValues(alpha: 0.45),
                                Colors.white,
                              ),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              mainAxisSize: MainAxisSize.min,
                              children: [
                                Icon(Icons.directions_bus_rounded,
                                    size: 13, color: scheme.primary),
                                const SizedBox(width: 4),
                                Text(
                                  shuttleDisplayName,
                                  style: Theme.of(context)
                                      .textTheme
                                      .labelSmall
                                      ?.copyWith(
                                        color: scheme.primary,
                                        fontWeight: FontWeight.w700,
                                      ),
                                ),
                              ],
                            ),
                          ),
                          const Spacer(),
                          _StalenessPill(availability: pillAvailability),
                        ],
                      ),

                      // ── Offline notice ────────────────────────────────────
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
                          Icon(Icons.place_outlined,
                              size: 16, color: scheme.primary),
                          const SizedBox(width: 4),
                          Text(
                            'At: ${currentStop.isEmpty ? '—' : currentStop}',
                            style: Theme.of(context)
                                .textTheme
                                .bodySmall
                                ?.copyWith(color: scheme.onSurfaceVariant),
                          ),
                          const SizedBox(width: 10),
                          Icon(Icons.arrow_forward,
                              size: 14, color: scheme.onSurfaceVariant),
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
                            horizontal: 12, vertical: 10),
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

  static Widget _cardShell(
    BuildContext context, {
    required ColorScheme scheme,
    required Widget child,
  }) {
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

// ── Inline offline notice ─────────────────────────────────────────────────────
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
              "You're offline. Showing data from ${_fmt(lastSeen)}.",
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

// ── Full offline banner ───────────────────────────────────────────────────────
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

// ── Stat box ──────────────────────────────────────────────────────────────────
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

// ── Staleness pill ────────────────────────────────────────────────────────────
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

// ── Card loading ──────────────────────────────────────────────────────────────
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

// ── Booking entry card ────────────────────────────────────────────────────────
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
        final hasOnTrip =
            bookings.any((b) => b.status.toLowerCase() == 'active');
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
                                  ? 'Scanner detected you as onboard. Safe travels!'
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