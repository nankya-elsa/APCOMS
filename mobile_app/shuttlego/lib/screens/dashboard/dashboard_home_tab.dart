import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart';

import '../../models/user_profile.dart';
import '../../services/auth_service.dart';

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

        return ListView(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
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
              'Live location',
              style: Theme.of(
                context,
              ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 8),
            _LiveLocationMap(trackedShuttleKey: trackedShuttleKey),
          ],
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
    final hasPhoto = photoUrl != null && photoUrl!.trim().isNotEmpty;
    return CircleAvatar(
      radius: 22,
      backgroundColor: hasPhoto
          ? Theme.of(context).colorScheme.primaryContainer
          : Colors.amber.shade200,
      foregroundImage: hasPhoto ? NetworkImage(photoUrl!) : null,
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

    return StreamBuilder<DatabaseEvent>(
      stream: ref.onValue,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return _cardShell(context, child: const _CardLoading());
        }

        final raw = snapshot.data?.snapshot.value;
        final data = raw is Map ? Map<String, Object?>.from(raw) : const {};

        final availableSeats = _readInt(data['available_seats']);
        final occupiedSeats = _readInt(data['current_count']);
        final totalSeats = (availableSeats + occupiedSeats);
        final occupancyStatus = (data['occupancy_status'] as String?)?.trim();

        final isFull =
            availableSeats <= 0 ||
            (occupancyStatus ?? '').toLowerCase().contains('full');

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
                      value: totalSeats,
                      label: 'Total',
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
                  Text(
                    'Next stop: Library',
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
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

class _LiveLocationMap extends StatelessWidget {
  const _LiveLocationMap({required this.trackedShuttleKey});

  final String trackedShuttleKey;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final ref = FirebaseDatabase.instance
        .ref()
        .child('shuttles')
        .child(trackedShuttleKey);

    return ClipRRect(
      borderRadius: BorderRadius.circular(16),
      child: Container(
        height: 210,
        decoration: BoxDecoration(
          color: scheme.surface,
          border: Border.all(
            color: scheme.outlineVariant.withValues(alpha: 0.22),
          ),
          borderRadius: BorderRadius.circular(16),
        ),
        child: kIsWeb
            ? Center(
                child: Text(
                  'Map preview on web requires a Google Maps JS API key.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: scheme.onSurfaceVariant,
                  ),
                ),
              )
            : StreamBuilder<DatabaseEvent>(
                stream: ref.onValue,
                builder: (context, snapshot) {
                  final raw = snapshot.data?.snapshot.value;
                  final data = raw is Map
                      ? Map<String, Object?>.from(raw)
                      : const {};

                  final lat =
                      _readDouble(data['lat']) ??
                      _readDouble(data['latitude']) ??
                      0.0;
                  final lng =
                      _readDouble(data['lng']) ??
                      _readDouble(data['longitude']) ??
                      0.0;

                  final position = LatLng(lat, lng);
                  final marker = Marker(
                    markerId: const MarkerId('shuttle'),
                    position: position,
                  );

                  return GoogleMap(
                    initialCameraPosition: CameraPosition(
                      target: position,
                      zoom: lat == 0.0 && lng == 0.0 ? 2 : 15,
                    ),
                    markers: {marker},
                    myLocationButtonEnabled: false,
                    zoomControlsEnabled: false,
                  );
                },
              ),
      ),
    );
  }

  static double? _readDouble(Object? value) {
    if (value is double) return value;
    if (value is int) return value.toDouble();
    if (value is String) return double.tryParse(value);
    return null;
  }
}
