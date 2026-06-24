import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../models/booking_availability.dart';
import '../models/booking_receipt.dart';
import '../models/booking_record.dart';
import '../models/shuttle_route.dart';
import '../services/booking_service.dart';
import '../widgets/shuttle_location_map.dart';
import 'package:google_maps_flutter/google_maps_flutter.dart' as gmaps;
import '../services/shuttle_route_geometry_service.dart';
import '../models/shuttle_route_geometry.dart';
import '../services/device_location_service.dart';

class BookingScreen extends StatefulWidget {
  const BookingScreen({
    super.key,
    required this.trackedShuttleKey,
    this.service,
  });

  final String trackedShuttleKey;
  final BookingService? service;

  @override
  State<BookingScreen> createState() => _BookingScreenState();
}

class _BookingScreenState extends State<BookingScreen> {
  final _pickupController = TextEditingController();
  final _destinationController = TextEditingController();

  int? _pickupIndex;
  int? _destinationIndex;
  bool _isSubmitting = false;
  bool _useDeviceLocation = false;
  int? _minutesToCurrentStop;
  int? _minutesToPickup;

  late final BookingService _service = widget.service ?? BookingService();

  @override
  void dispose() {
    _pickupController.dispose();
    _destinationController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;

    return Scaffold(
      backgroundColor: Colors.white,
      appBar: AppBar(
        title: const Text('Booking'),
        backgroundColor: Colors.white,
        foregroundColor: scheme.onSurface,
        elevation: 0,
        surfaceTintColor: Colors.white,
        actions: [
          IconButton(
            tooltip: 'Booking history',
            onPressed: _showBookingHistory,
            icon: const Icon(Icons.history),
          ),
        ],
      ),
      body: StreamBuilder<BookingAvailability>(
        stream: _service.watchAvailability(
          shuttleKey: widget.trackedShuttleKey,
        ),
        builder: (context, snapshot) {
          final availability = snapshot.data;
          final isLoadingSeats =
              availability == null &&
              snapshot.connectionState == ConnectionState.waiting;
          final canBook = availability?.canBook ?? false;
          final hasValidStops =
              _pickupIndex != null && _destinationIndex != null;
          final canSubmit = canBook && hasValidStops && !_isSubmitting;

          return Stack(
            children: [
              StreamBuilder<ShuttleRouteGeometry?>(
                stream: ShuttleRouteGeometryService().watchRoute(
                  shuttleKey: widget.trackedShuttleKey,
                ),
                builder: (context, routeSnap) {
                  final route = routeSnap.data;
                  gmaps.LatLng? pickupPoint;
                  final pickupIndex = _pickupIndex;
                  if (pickupIndex != null) {
                    final stopName = ShuttleRoute.stops[pickupIndex];
                    final stop = route?.findStopByName(stopName);
                    if (stop != null)
                      pickupPoint = gmaps.LatLng(stop.lat, stop.lng);
                  }

                  if (_useDeviceLocation) {
                    return StreamBuilder<gmaps.LatLng?>(
                      stream: DeviceLocationService().watchDeviceLocation(),
                      builder: (context, deviceSnap) {
                        final devicePoint = deviceSnap.data;
                        return ShuttleLocationMap(
                          shuttleKey: widget.trackedShuttleKey,
                          height: 380,
                          targetLocation: devicePoint ?? pickupPoint,
                        );
                      },
                    );
                  }

                  return ShuttleLocationMap(
                    shuttleKey: widget.trackedShuttleKey,
                    height: 380,
                    targetLocation: pickupPoint,
                  );
                },
              ),
              Align(
                alignment: Alignment.bottomCenter,
                child: SafeArea(
                  top: false,
                  child: Container(
                    width: double.infinity,
                    padding: const EdgeInsets.fromLTRB(16, 14, 16, 16),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: const BorderRadius.vertical(
                        top: Radius.circular(18),
                      ),
                      border: Border.all(
                        color: scheme.outlineVariant.withValues(alpha: 0.22),
                      ),
                    ),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (_minutesToCurrentStop != null ||
                            _minutesToPickup != null)
                          Padding(
                            padding: const EdgeInsets.only(bottom: 12),
                            child: Row(
                              children: [
                                if (_minutesToCurrentStop != null)
                                  Expanded(
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 10,
                                        vertical: 8,
                                      ),
                                      decoration: BoxDecoration(
                                        color: Colors.white,
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: Theme.of(context)
                                              .colorScheme
                                              .outlineVariant
                                              .withValues(alpha: 0.22),
                                        ),
                                      ),
                                      child: Text(
                                        'Bus ≈ ${_minutesToCurrentStop} min to current stop',
                                        style: Theme.of(
                                          context,
                                        ).textTheme.bodySmall,
                                      ),
                                    ),
                                  ),
                                if (_minutesToPickup != null) ...[
                                  const SizedBox(width: 8),
                                  Expanded(
                                    child: Container(
                                      padding: const EdgeInsets.symmetric(
                                        horizontal: 10,
                                        vertical: 8,
                                      ),
                                      decoration: BoxDecoration(
                                        color: Colors.white,
                                        borderRadius: BorderRadius.circular(10),
                                        border: Border.all(
                                          color: Theme.of(context)
                                              .colorScheme
                                              .outlineVariant
                                              .withValues(alpha: 0.22),
                                        ),
                                      ),
                                      child: Text(
                                        'Bus ≈ ${_minutesToPickup} min to your pickup',
                                        style: Theme.of(
                                          context,
                                        ).textTheme.bodySmall,
                                      ),
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.end,
                          children: [
                            const Text('Use my location'),
                            const SizedBox(width: 8),
                            Switch(
                              value: _useDeviceLocation,
                              onChanged: (v) =>
                                  setState(() => _useDeviceLocation = v),
                            ),
                          ],
                        ),
                        _LabeledField(
                          label: 'Pick Up',
                          controller: _pickupController,
                          hintText: 'Select pick up stop',
                          readOnly: true,
                          onTap: _isSubmitting ? null : _selectPickup,
                        ),
                        const SizedBox(height: 10),
                        _LabeledField(
                          label: 'Where To',
                          controller: _destinationController,
                          hintText: 'Select destination stop',
                          readOnly: true,
                          onTap: _isSubmitting ? null : _selectDestination,
                        ),
                        const SizedBox(height: 12),
                        SizedBox(
                          width: double.infinity,
                          height: 46,
                          child: FilledButton(
                            onPressed: canSubmit ? _submitBooking : null,
                            child: _isSubmitting
                                ? const SizedBox(
                                    height: 22,
                                    width: 22,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : Text(
                                    isLoadingSeats
                                        ? 'Loading seats...'
                                        : canBook
                                        ? 'Reserve Seat'
                                        : 'No free seats available',
                                  ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ],
          );
        },
      ),
    );
  }

  Future<void> _selectPickup() async {
    final selected = await _pickStop(context, stops: ShuttleRoute.stops);
    if (!mounted || selected == null) return;

    setState(() {
      _pickupIndex = selected;
      _pickupController.text = ShuttleRoute.stops[selected];

      final destinationIndex = _destinationIndex;
      if (destinationIndex != null && destinationIndex <= selected) {
        _destinationIndex = null;
        _destinationController.clear();
      }
    });
  }

  Future<void> _selectDestination() async {
    final pickupIndex = _pickupIndex;
    if (pickupIndex == null) {
      _showSnack(context, 'Select a pickup stop first.');
      return;
    }

    final stops = ShuttleRoute.destinationChoicesForPickup(pickupIndex);
    final selected = await _pickStop(context, stops: stops);
    if (!mounted || selected == null) return;

    // Map the selected stop name back to its absolute index in the master
    // `ShuttleRoute.stops` list so we can store the canonical index.
    final selectedStopName = stops[selected];
    final resolvedIndex = ShuttleRoute.stops.indexOf(selectedStopName);
    if (resolvedIndex < 0) return;
    setState(() {
      _destinationIndex = resolvedIndex;
      _destinationController.text = ShuttleRoute.stops[resolvedIndex];
    });
  }

  Future<int?> _pickStop(BuildContext context, {required List<String> stops}) {
    return showModalBottomSheet<int>(
      context: context,
      showDragHandle: true,
      builder: (context) {
        return SafeArea(
          child: ListView.separated(
            shrinkWrap: true,
            itemCount: stops.length,
            separatorBuilder: (context, index) => const Divider(height: 1),
            itemBuilder: (context, index) {
              return ListTile(
                title: Text(stops[index]),
                onTap: () => Navigator.of(context).pop(index),
              );
            },
          ),
        );
      },
    );
  }

  Future<void> _submitBooking() async {
    final pickupIndex = _pickupIndex;
    final destinationIndex = _destinationIndex;
    if (pickupIndex == null || destinationIndex == null) {
      _showSnack(context, 'Select pickup and destination stops.');
      return;
    }
    if (!ShuttleRoute.isValidTripSegment(
      pickupIndex: pickupIndex,
      destinationIndex: destinationIndex,
    )) {
      final msg = ShuttleRoute.isCircular
          ? 'Destination must be different from pickup.'
          : 'Destination must come after pickup.';
      _showSnack(context, msg);
      return;
    }

    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      _showSnack(context, 'Please sign in to book a seat.');
      return;
    }

    setState(() => _isSubmitting = true);
    try {
      final receipt = await _service.createBooking(
        shuttleKey: widget.trackedShuttleKey,
        userUid: user.uid,
        pickupStop: ShuttleRoute.stops[pickupIndex],
        pickupIndex: pickupIndex,
        destinationStop: ShuttleRoute.stops[destinationIndex],
        destinationIndex: destinationIndex,
      );

      if (!mounted) return;
      await showDialog<void>(
        context: context,
        builder: (context) => _BookingQrDialog(receipt: receipt),
      );
    } catch (e) {
      if (!mounted) return;
      _showSnack(context, 'Booking failed. ${e.toString()}');
    } finally {
      if (mounted) setState(() => _isSubmitting = false);
    }
  }

  Future<void> _showBookingHistory() async {
    final user = FirebaseAuth.instance.currentUser;
    if (user == null) {
      _showSnack(context, 'Please sign in to view bookings.');
      return;
    }

    await showModalBottomSheet<void>(
      context: context,
      showDragHandle: true,
      isScrollControlled: true,
      builder: (context) {
        return _BookingHistorySheet(
          service: _service,
          userUid: user.uid,
          onCancel: _cancelBooking,
        );
      },
    );
  }

  Future<void> _cancelBooking(BookingRecord booking) async {
    final reason = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => const _CancelReasonSheet(),
    );
    if (!mounted || reason == null || reason.trim().isEmpty) return;

    try {
      await _service.cancelBooking(booking: booking, reason: reason);
      if (!mounted) return;
      _showSnack(context, 'Booking cancelled.');
    } catch (e) {
      if (!mounted) return;
      _showSnack(context, 'Cancel failed. ${e.toString()}');
    }
  }

  static void _showSnack(BuildContext context, String message) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        content: Text(message, textAlign: TextAlign.center),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
  }
}

class _BookingHistorySheet extends StatelessWidget {
  const _BookingHistorySheet({
    required this.service,
    required this.userUid,
    required this.onCancel,
  });

  final BookingService service;
  final String userUid;
  final ValueChanged<BookingRecord> onCancel;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: SizedBox(
        height: MediaQuery.sizeOf(context).height * 0.76,
        child: StreamBuilder<List<BookingRecord>>(
          stream: service.watchUserBookings(userUid: userUid),
          builder: (context, snapshot) {
            final bookings = snapshot.data ?? const <BookingRecord>[];

            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Center(child: CircularProgressIndicator());
            }

            if (bookings.isEmpty) {
              return const Center(child: Text('No bookings yet.'));
            }

            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
              itemCount: bookings.length + 1,
              separatorBuilder: (context, index) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                if (index == 0) {
                  return Text(
                    'Booking history',
                    style: Theme.of(context).textTheme.titleLarge?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  );
                }

                final booking = bookings[index - 1];
                return _BookingHistoryTile(
                  booking: booking,
                  onCancel: booking.isActive ? () => onCancel(booking) : null,
                );
              },
            );
          },
        ),
      ),
    );
  }
}

class _BookingHistoryTile extends StatelessWidget {
  const _BookingHistoryTile({required this.booking, required this.onCancel});

  final BookingRecord booking;
  final VoidCallback? onCancel;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final statusLower = booking.status.toLowerCase();
    final statusColor = statusLower == 'reserved'
        ? scheme.primary
        : statusLower == 'active'
        ? const Color(0xFFFFA726)
        : scheme.error;

    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: scheme.outlineVariant.withValues(alpha: 0.4)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  '${booking.pickupStop} to ${booking.destinationStop}',
                  style: Theme.of(
                    context,
                  ).textTheme.titleSmall?.copyWith(fontWeight: FontWeight.w800),
                ),
              ),
              Text(
                booking.status,
                style: Theme.of(context).textTheme.labelMedium?.copyWith(
                  color: statusColor,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            'Ticket: ${booking.bookingId}',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: Theme.of(
              context,
            ).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
          ),
          if ((booking.cancelReason ?? '').isNotEmpty) ...[
            const SizedBox(height: 4),
            Text(
              'Reason: ${booking.cancelReason}',
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ],
          const SizedBox(height: 10),
          Row(
            children: [
              OutlinedButton.icon(
                onPressed: () {
                  showDialog<void>(
                    context: context,
                    builder: (context) => _BookingQrDialog(
                      receipt: BookingReceipt(
                        bookingId: booking.bookingId,
                        shuttleKey: booking.shuttleKey,
                        userUid: booking.userUid,
                        pickupStop: booking.pickupStop,
                        pickupIndex: booking.pickupIndex,
                        destinationStop: booking.destinationStop,
                        destinationIndex: booking.destinationIndex,
                        createdAt: booking.createdAt,
                        qrPayload: booking.qrPayload,
                      ),
                    ),
                  );
                },
                icon: const Icon(Icons.qr_code_2, size: 18),
                label: const Text('QR'),
              ),
              const Spacer(),
              if (onCancel != null)
                TextButton(onPressed: onCancel, child: const Text('Cancel')),
            ],
          ),
        ],
      ),
    );
  }
}

class _CancelReasonSheet extends StatefulWidget {
  const _CancelReasonSheet();

  @override
  State<_CancelReasonSheet> createState() => _CancelReasonSheetState();
}

class _CancelReasonSheetState extends State<_CancelReasonSheet> {
  static const _reasons = <String>[
    'Changed my mind',
    'Used another route',
    'No longer travelling',
    'Booked by mistake',
    'Other',
  ];

  String? _selectedReason = _reasons.first;

  @override
  Widget build(BuildContext context) {
    return SafeArea(
      child: Padding(
        padding: const EdgeInsets.fromLTRB(16, 4, 16, 16),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Cancel booking',
              style: Theme.of(
                context,
              ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 12),
            DropdownButtonFormField<String>(
              value: _selectedReason,
              decoration: const InputDecoration(
                labelText: 'Reason',
                border: OutlineInputBorder(),
              ),
              items: _reasons
                  .map(
                    (reason) => DropdownMenuItem<String>(
                      value: reason,
                      child: Text(reason),
                    ),
                  )
                  .toList(),
              onChanged: (value) => setState(() => _selectedReason = value),
            ),
            const SizedBox(height: 14),
            SizedBox(
              width: double.infinity,
              child: FilledButton(
                onPressed: _selectedReason == null
                    ? null
                    : () => Navigator.of(context).pop(_selectedReason),
                child: const Text('Confirm cancellation'),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LabeledField extends StatelessWidget {
  const _LabeledField({
    required this.label,
    required this.controller,
    required this.hintText,
    this.readOnly = false,
    this.onTap,
  });

  final String label;
  final TextEditingController controller;
  final String hintText;
  final bool readOnly;
  final VoidCallback? onTap;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Row(
      children: [
        SizedBox(
          width: 76,
          child: Text(
            label,
            style: Theme.of(
              context,
            ).textTheme.labelLarge?.copyWith(fontWeight: FontWeight.w700),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: TextField(
            controller: controller,
            readOnly: readOnly,
            onTap: onTap,
            decoration: InputDecoration(
              hintText: hintText,
              isDense: true,
              filled: true,
              fillColor: Color.alphaBlend(
                scheme.primaryContainer.withValues(alpha: 0.10),
                Colors.white,
              ),
              suffixIcon: readOnly
                  ? const Icon(Icons.keyboard_arrow_down_rounded)
                  : null,
              border: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(
                  color: scheme.outlineVariant.withValues(alpha: 0.30),
                ),
              ),
              enabledBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(
                  color: scheme.outlineVariant.withValues(alpha: 0.30),
                ),
              ),
              focusedBorder: OutlineInputBorder(
                borderRadius: BorderRadius.circular(10),
                borderSide: BorderSide(color: scheme.primary),
              ),
            ),
          ),
        ),
      ],
    );
  }
}

class _BookingQrDialog extends StatelessWidget {
  const _BookingQrDialog({required this.receipt});

  final BookingReceipt receipt;

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return AlertDialog(
      title: const Text('Booking Confirmed'),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Show this QR code when boarding.', style: textTheme.bodyMedium),
          const SizedBox(height: 12),
          Center(
            child: SizedBox(
              height: 220,
              width: 220,
              child: _QrWidget(data: receipt.qrPayload),
            ),
          ),
          const SizedBox(height: 12),
          Text('Pickup: ${receipt.pickupStop}'),
          Text('Destination: ${receipt.destinationStop}'),
        ],
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Done'),
        ),
      ],
    );
  }
}

class _QrWidget extends StatelessWidget {
  const _QrWidget({required this.data});

  final String data;

  @override
  Widget build(BuildContext context) {
    return QrImageView(data: data, version: QrVersions.auto, gapless: false);
  }
}
