import 'dart:async';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:firebase_database/firebase_database.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../models/booking_receipt.dart';
import '../models/booking_record.dart';
import '../services/booking_service.dart';
import '../utils/ticket_downloader.dart';

BookingReceipt _receiptFromBooking(BookingRecord booking) {
  return BookingReceipt(
    bookingId: booking.bookingId,
    shuttleKey: booking.shuttleKey,
    userUid: booking.userUid,
    pickupStop: booking.pickupStop,
    pickupIndex: booking.pickupIndex,
    destinationStop: booking.destinationStop,
    destinationIndex: booking.destinationIndex,
    createdAt: booking.createdAt,
    qrPayload: booking.qrPayload,
  );
}

class MyBookingsScreen extends StatefulWidget {
  const MyBookingsScreen({super.key, this.service});

  final BookingService? service;

  @override
  State<MyBookingsScreen> createState() => _MyBookingsScreenState();
}

class _MyBookingsScreenState extends State<MyBookingsScreen> {
  late final BookingService _service = widget.service ?? BookingService();
  Stream<List<BookingRecord>>? _bookingsStream;

  @override
  void initState() {
    super.initState();
    // Stream will be created lazily and reused by the StreamBuilder.
  }

  // Removed temporary one-shot debug and debug listener.

  @override
  Widget build(BuildContext context) {
    try {
      final user = FirebaseAuth.instance.currentUser;
      final scheme = Theme.of(context).colorScheme;

      if (user == null) {
        return const Scaffold(
          backgroundColor: Colors.white,
          body: Center(child: Text('Please sign in to view bookings.')),
        );
      }

      return Scaffold(
        backgroundColor: Colors.white,
        appBar: AppBar(
          title: const Text('My Bookings'),
          backgroundColor: Colors.white,
          foregroundColor: scheme.onSurface,
          elevation: 0,
          surfaceTintColor: Colors.white,
        ),
        body: StreamBuilder<List<BookingRecord>>(
          stream: _bookingsStream ??= _service.watchUserBookings(
            userUid: user.uid,
          ),
          initialData: const <BookingRecord>[],
          builder: (context, snapshot) {
            final bookings = snapshot.data ?? const <BookingRecord>[];

            if (snapshot.connectionState == ConnectionState.waiting &&
                bookings.isEmpty) {
              return const Center(child: CircularProgressIndicator());
            }

            if (snapshot.hasError) {
              return Padding(
                padding: const EdgeInsets.all(16),
                child: Text(
                  'Could not load bookings.\n${snapshot.error}',
                  style: Theme.of(context).textTheme.bodyMedium,
                ),
              );
            }

            if (bookings.isEmpty) return _BookingsEmptyState(uid: user.uid);

            return ListView.separated(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 16),
              itemCount: bookings.length,
              separatorBuilder: (context, index) => const SizedBox(height: 10),
              itemBuilder: (context, index) {
                final booking = bookings[index];
                return _BookingTile(
                  booking: booking,
                  onOpen: () => _openDetails(booking),
                  onShowQr: () => _showQr(booking),
                  onCancel:
                      booking.isActive ? () => _cancelBooking(booking) : null,
                );
              },
            );
          },
        ),
      );
    } catch (e, st) {
      return Scaffold(
        backgroundColor: Colors.white,
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.error_outline, size: 48, color: Colors.red),
                const SizedBox(height: 12),
                Text(
                  'An error occurred while rendering My Bookings:',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Text(
                  e.toString(),
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: Colors.red),
                ),
                const SizedBox(height: 8),
                SelectableText(st.toString()),
              ],
            ),
          ),
        ),
      );
    }
  }

  Future<void> _openDetails(BookingRecord booking) async {
    await Navigator.of(context).push(
      MaterialPageRoute(
        builder: (context) =>
            BookingDetailsScreen(booking: booking, service: _service),
      ),
    );
  }

  void _showQr(BookingRecord booking) {
    showDialog<void>(
      context: context,
      builder: (context) =>
          _BookingQrDialog(receipt: _receiptFromBooking(booking)),
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
      _showSnack('Booking cancelled.');
    } catch (e) {
      if (!mounted) return;
      _showSnack('Cancel failed. ${e.toString()}');
    }
  }

  void _showSnack(String message) {
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text(message)));
  }

  @override
  void dispose() {
    super.dispose();
  }
}

class _BookingsEmptyState extends StatelessWidget {
  const _BookingsEmptyState({required this.uid});

  final String uid;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(
              Icons.confirmation_number_outlined,
              size: 42,
              color: scheme.onSurfaceVariant,
            ),
            const SizedBox(height: 10),
            Text(
              'No bookings found',
              style: Theme.of(
                context,
              ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 6),
            Text(
              'This page shows bookings where user_uid matches your signed-in account.',
              textAlign: TextAlign.center,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
            const SizedBox(height: 10),
            SelectableText(
              'Current uid: $uid',
              textAlign: TextAlign.center,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ],
        ),
      ),
    );
  }
}

class _BookingTile extends StatelessWidget {
  const _BookingTile({
    required this.booking,
    required this.onOpen,
    required this.onShowQr,
    required this.onCancel,
  });

  final BookingRecord booking;
  final VoidCallback onOpen;
  final VoidCallback onShowQr;
  final VoidCallback? onCancel;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    final statusColor = booking.isActive ? scheme.primary : scheme.error;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        onTap: onOpen,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white,
            borderRadius: BorderRadius.circular(12),
            border: Border.all(
              color: scheme.outlineVariant.withValues(alpha: 0.4),
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Expanded(
                    child: Text(
                      '${booking.pickupStop} → ${booking.destinationStop}',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                  Text(
                    booking.status,
                    style: Theme.of(context).textTheme.labelMedium?.copyWith(
                      color: statusColor,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(width: 4),
                  Icon(
                    Icons.chevron_right,
                    color: scheme.onSurfaceVariant,
                    size: 20,
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
              const SizedBox(height: 6),
              Text(
                'Shuttle: ${booking.shuttleKey} • Pickup #${booking.pickupIndex} • Destination #${booking.destinationIndex}',
                style: Theme.of(
                  context,
                ).textTheme.bodySmall?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class BookingDetailsScreen extends StatefulWidget {
  const BookingDetailsScreen({
    super.key,
    required this.booking,
    required this.service,
  });

  final BookingRecord booking;
  final BookingService service;

  @override
  State<BookingDetailsScreen> createState() => _BookingDetailsScreenState();
}

class _BookingDetailsScreenState extends State<BookingDetailsScreen> {
  bool _isCancelling = false;

  BookingRecord get booking => widget.booking;

  @override
  Widget build(BuildContext context) {
    try {
      final scheme = Theme.of(context).colorScheme;
      final receipt = _receiptFromBooking(booking);
      final statusColor = booking.isActive ? scheme.primary : scheme.error;

      return Scaffold(
        backgroundColor: Colors.white,
        appBar: AppBar(
          title: const Text('Booking Details'),
          backgroundColor: Colors.white,
          foregroundColor: scheme.onSurface,
          elevation: 0,
          surfaceTintColor: Colors.white,
        ),
        body: ListView(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 16),
          children: [
            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: scheme.outlineVariant.withValues(alpha: 0.4),
                ),
              ),
              child: Column(
                children: [
                  SizedBox(
                    height: 230,
                    width: 230,
                    child: QrImageView(
                      data: receipt.qrPayload,
                      version: QrVersions.auto,
                      gapless: false,
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Show this QR code when boarding.',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: scheme.onSurfaceVariant,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: () => _showQr(receipt),
                      icon: const Icon(Icons.download),
                      label: const Text('View or Download Ticket'),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 14),
            _DetailRow(
              label: 'Status',
              value: booking.status,
              color: statusColor,
            ),
            _DetailRow(label: 'Pickup', value: booking.pickupStop),
            _DetailRow(label: 'Destination', value: booking.destinationStop),
            _DetailRow(label: 'Shuttle', value: booking.shuttleKey),
            _DetailRow(label: 'Ticket ID', value: booking.bookingId),
            if ((booking.cancelReason ?? '').isNotEmpty)
              _DetailRow(
                label: 'Cancel reason',
                value: booking.cancelReason ?? '',
              ),
            const SizedBox(height: 16),
            if (booking.isActive)
              SizedBox(
                width: double.infinity,
                height: 46,
                child: FilledButton(
                  onPressed: _isCancelling ? null : _cancelBooking,
                  style: FilledButton.styleFrom(
                    backgroundColor: scheme.error,
                    foregroundColor: scheme.onError,
                  ),
                  child: _isCancelling
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Text('Cancel Reservation'),
                ),
              ),
          ],
        ),
      );
    } catch (e, st) {
      // Show the error so it's visible in the UI instead of crashing to white screen
      debugPrint('BookingDetails build error: $e\n$st');
      return Scaffold(
        appBar: AppBar(title: const Text('Booking Details')),
        body: Padding(
          padding: const EdgeInsets.all(16),
          child: SingleChildScrollView(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(Icons.error_outline, size: 48, color: Colors.red),
                const SizedBox(height: 12),
                Text(
                  'An error occurred while rendering booking details:',
                  style: Theme.of(context).textTheme.titleMedium,
                ),
                const SizedBox(height: 8),
                Text(
                  e.toString(),
                  style: Theme.of(
                    context,
                  ).textTheme.bodySmall?.copyWith(color: Colors.red),
                ),
                const SizedBox(height: 8),
                SelectableText(
                  st.toString(),
                  style: Theme.of(context).textTheme.bodySmall,
                ),
              ],
            ),
          ),
        ),
      );
    }
  }

  void _showQr(BookingReceipt receipt) {
    showDialog<void>(
      context: context,
      builder: (context) => _BookingQrDialog(receipt: receipt),
    );
  }

  Future<void> _cancelBooking() async {
    final reason = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (context) => const _CancelReasonSheet(),
    );
    if (!mounted || reason == null || reason.trim().isEmpty) return;

    setState(() => _isCancelling = true);
    try {
      await widget.service.cancelBooking(booking: booking, reason: reason);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
        ..clearSnackBars()
        ..showSnackBar(const SnackBar(content: Text('Booking cancelled.')));
      Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
        ..clearSnackBars()
        ..showSnackBar(SnackBar(content: Text('Cancel failed. $e')));
    } finally {
      if (mounted) setState(() => _isCancelling = false);
    }
  }
}

class _DetailRow extends StatelessWidget {
  const _DetailRow({required this.label, required this.value, this.color});

  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 7),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 104,
            child: Text(
              label,
              style: Theme.of(
                context,
              ).textTheme.bodySmall?.copyWith(color: scheme.onSurfaceVariant),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: color ?? scheme.onSurface,
                fontWeight: FontWeight.w600,
              ),
            ),
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

class _BookingQrDialog extends StatefulWidget {
  const _BookingQrDialog({required this.receipt});

  final BookingReceipt receipt;

  @override
  State<_BookingQrDialog> createState() => _BookingQrDialogState();
}

class _BookingQrDialogState extends State<_BookingQrDialog> {
  bool _isDownloading = false;

  Future<void> _downloadQr() async {
    setState(() => _isDownloading = true);
    try {
      final painter = QrPainter(
        data: widget.receipt.qrPayload,
        version: QrVersions.auto,
        gapless: false,
        eyeStyle: const QrEyeStyle(
          eyeShape: QrEyeShape.square,
          color: Colors.black,
        ),
        dataModuleStyle: const QrDataModuleStyle(
          dataModuleShape: QrDataModuleShape.square,
          color: Colors.black,
        ),
      );
      final imageData = await painter.toImageData(720);
      final bytes = imageData?.buffer.asUint8List();
      if (bytes == null) {
        throw StateError('Could not render QR code.');
      }

      final downloaded = await downloadTicketPng(
        fileName: 'shuttlego-ticket-${widget.receipt.bookingId}.png',
        bytes: bytes,
      );
      if (!mounted) return;

      ScaffoldMessenger.of(context)
        ..clearSnackBars()
        ..showSnackBar(
          SnackBar(
            content: Text(
              downloaded
                  ? 'Ticket downloaded.'
                  : 'Download is currently available on web only.',
            ),
          ),
        );
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
        ..clearSnackBars()
        ..showSnackBar(SnackBar(content: Text('Download failed. $e')));
    } finally {
      if (mounted) setState(() => _isDownloading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final textTheme = Theme.of(context).textTheme;
    return AlertDialog(
      title: const Text('Booking Ticket'),
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
              child: QrImageView(
                data: widget.receipt.qrPayload,
                version: QrVersions.auto,
                gapless: false,
              ),
            ),
          ),
          const SizedBox(height: 12),
          Text('Pickup: ${widget.receipt.pickupStop}'),
          Text('Destination: ${widget.receipt.destinationStop}'),
        ],
      ),
      actions: [
        TextButton.icon(
          onPressed: _isDownloading ? null : _downloadQr,
          icon: _isDownloading
              ? const SizedBox(
                  width: 16,
                  height: 16,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.download),
          label: const Text('Download'),
        ),
        TextButton(
          onPressed: () => Navigator.of(context).pop(),
          child: const Text('Done'),
        ),
      ],
    );
  }
}
