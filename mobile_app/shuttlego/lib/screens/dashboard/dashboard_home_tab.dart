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

        return LayoutBuilder(
          builder: (context, constraints) {
            return SingleChildScrollView(
              child: ConstrainedBox(
                constraints: BoxConstraints(minHeight: constraints.maxHeight),
                child: IntrinsicHeight(
                  child: Padding(
                    // Add a bit more top spacing so greeting isn't flush to the
                    // top edge, without pushing the booking card to the bottom.
                    padding: const EdgeInsets.fromLTRB(16, 36, 16, 16),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
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
                                    style: Theme.of(
                                      context,
                                    ).textTheme.bodySmall?.copyWith(color: Colors.black54),
                                  ),
                                  const SizedBox(height: 2),
                                  Text(
                                    nameText,
                                    style: Theme.of(context).textTheme.titleMedium
                                        ?.copyWith(fontWeight: FontWeight.w700),
                                  ),
                                ],
                              ),
                            ),
                            if (role.isNotEmpty) _RolePill(role: role),
                          ],
                        ),
                        const SizedBox(height: 14),
                        _ShuttleCard(trackedShuttleKey: trackedShuttleKey),
                        const SizedBox(height: 14),
                        Text(
                          'Booking',
                          style: Theme.of(
                            context,
                          ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
                        ),
                        const SizedBox(height: 8),
                        _BookingEntryCard(
                          trackedShuttleKey: trackedShuttleKey,
                          uid: uid,
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            );
          },
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
      final _photo = photoUrl?.trim();
      final hasPhoto = _photo?.isNotEmpty ?? false;
      return CircleAvatar(
      radius: 22,
      backgroundColor: hasPhoto
          ? Theme.of(context).colorScheme.primaryContainer
          : Colors.amber.shade200,
        foregroundImage: hasPhoto ? NetworkImage(_photo!) : null,
      child: Text(
        initial.toUpperCase(),
        style: Theme.of(
          context,
        ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700),
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

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ref = FirebaseDatabase.instance
        .ref()
        .child('shuttles')
        .child(trackedShuttleKey);

    return StreamBuilder<BookingAvailability>(
      stream: BookingService().watchAvailability(shuttleKey: trackedShuttleKey),
      builder: (context, availabilitySnapshot) {
        final availability = availabilitySnapshot.data;

        return StreamBuilder<DatabaseEvent>(
          stream: ref.onValue,
          builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _cardShell(context, child: const _CardLoading());
        }

        if (snapshot.hasError) {
          return _cardShell(
            context,
            child: Text(
              'Failed to load shuttle data.\n${snapshot.error}',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          );
        }

        final raw = snapshot.data?.snapshot.value;
        if (raw == null) {
          return _cardShell(
            context,
            child: Text(
              'No data found at shuttles/$trackedShuttleKey.\n'
              'Check your Realtime Database path and rules.',
              style: Theme.of(context).textTheme.bodySmall,
            ),
          );
        }
        final data = raw is Map ? Map<String, Object?>.from(raw) : const {};

        final locationRaw = data['location'];
        final location = locationRaw is Map
            ? Map<String, Object?>.from(locationRaw)
            : null;

        final rawAvailableSeats = _readInt(data['available_seats']);
        final occupiedSeats = _readInt(data['current_count']);
        final reservedSeats = availability?.reservedSeats ?? 0;
        final availableSeats = rawAvailableSeats.clamp(0, 999).toInt();
        final occupancyStatus = (data['occupancy_status'] as String?)?.trim();

        final currentStop =
            (((data['current_stop'] as String?) ??
                        (location?['current_stop'] as String?)) ??
                    '')
                .trim();
        final nextStop =
            (((data['next_stop'] as String?) ??
                        (location?['next_stop'] as String?)) ??
                    '')
                .trim();

        final normalizedStatus = (occupancyStatus ?? '').toLowerCase();
        final hasHardFullStatus = normalizedStatus == 'full';

        final isFull =
            availableSeats <= 0 ||
            hasHardFullStatus;

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
        final statusSubtitle = isFull
            ? 'Select another shuttle'
            : 'Head to the next stop';

        return _cardShell(
          context,
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Image.asset(
                    'assets/images/logo.png',
                    height: 22,
                    fit: BoxFit.contain,
                  ),
                  const Spacer(),
                ],
              ),
              const SizedBox(height: 10),
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
              Row(
                children: [
                  Icon(Icons.place_outlined, size: 16, color: scheme.primary),
                  const SizedBox(width: 4),
                  Text(
                    '5 min away from you',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                  ),
                  const Spacer(),
                  Flexible(
                    child: Text(
                      'Current: ${currentStop.isEmpty ? '—' : currentStop}  •  Next: ${nextStop.isEmpty ? '—' : nextStop}',
                      textAlign: TextAlign.right,
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: scheme.onSurfaceVariant,
                      ),
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 10),
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
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        color: statusFg,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      statusSubtitle,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
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
        Text('Loading shuttle…', style: Theme.of(context).textTheme.bodyMedium),
      ],
    );
  }
}

class _BookingEntryCard extends StatelessWidget {
  const _BookingEntryCard({required this.trackedShuttleKey, required this.uid});

  final String trackedShuttleKey;
  final String uid;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return StreamBuilder<List<BookingRecord>>(
      stream: BookingService().watchUserBookings(userUid: uid),
      builder: (context, snapshot) {
        final hasActive = snapshot.data?.any((b) => b.isActive) ?? false;

        void action() {
          if (hasActive) {
            Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => MyBookingsScreen()),
            );
            return;
          }

          Navigator.of(context).push(
            MaterialPageRoute(
              builder: (_) => BookingScreen(trackedShuttleKey: trackedShuttleKey),
            ),
          );
        }

        final buttonLabel = hasActive ? 'View Booking' : 'Book Now';

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
                              hasActive ? 'You have an active booking' : 'Book a seat',
                              style: Theme.of(context).textTheme.titleSmall
                                  ?.copyWith(fontWeight: FontWeight.w800),
                            ),
                            const SizedBox(height: 2),
                            Text(
                              hasActive ? 'Cancel or complete it to make a new booking' : 'Choose pick up and destination',
                              style: Theme.of(context).textTheme.bodySmall
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
                      onPressed: action,
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
