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

// Shared date helper for multiple widgets to format display date.
String _formatDate(DateTime d) {
  final month = _monthName(d.month);
  return '$month ${d.day}, ${d.year}';
}

String _monthName(int m) {
  const names = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ];
  return names[m - 1];
}

class MyBookingsScreen extends StatefulWidget {
  const MyBookingsScreen({super.key, this.service});

  final BookingService? service;

  @override
  State<MyBookingsScreen> createState() => _MyBookingsScreenState();
}

class _MyBookingsScreenState extends State<MyBookingsScreen> {
  late final BookingService _service = widget.service ?? BookingService();

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
          // Request a fresh stream on every build so UI reflects recent
          // changes (e.g. cancellations) immediately after returning.
          stream: _service.watchUserBookings(userUid: user.uid),
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

            final active = bookings.where((b) => b.isActive).toList();
            final past = bookings.where((b) => !b.isActive).toList();

            return ListView(
              padding: const EdgeInsets.fromLTRB(16, 12, 16, 20),
              children: [
                if (active.isNotEmpty) ...[
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: scheme.primary.withOpacity(0.06),
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(
                        color: scheme.primary.withOpacity(0.12),
                      ),
                    ),
                    child: Row(
                      children: [
                        Icon(Icons.school, color: scheme.primary),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            'You can only have one active booking. Make a new booking after your current trip.',
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: scheme.onSurfaceVariant),
                          ),
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Text(
                    'Active Booking',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 8),
                  for (final booking in active)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _BookingTile(
                        booking: booking,
                        onOpen: () => _openDetails(booking),
                        onShowQr: () => _showQr(booking),
                        onCancel: booking.isActive
                            ? () => _cancelBooking(booking)
                            : null,
                      ),
                    ),
                ],

                if (past.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    'Past Bookings',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                  const SizedBox(height: 8),
                  for (final booking in past)
                    Padding(
                      padding: const EdgeInsets.only(bottom: 10),
                      child: _BookingTile(
                        booking: booking,
                        onOpen: () => _openDetails(booking),
                        onShowQr: () => _showQr(booking),
                        onCancel: () => _deleteBooking(booking),
                      ),
                    ),
                ],
              ],
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

  Future<void> _deleteBooking(BookingRecord booking) async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete booking'),
        content: const Text('Delete this past booking? This cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (!mounted || confirm != true) return;

    try {
      await _service.deleteBooking(booking: booking);
      if (!mounted) return;
      _showSnack('Booking deleted.');
    } catch (e) {
      if (!mounted) return;
      _showSnack('Delete failed. ${e.toString()}');
    }
  }

  void _showSnack(String message) {
    showDialog<void>(
      context: context,
      builder: (context) => AlertDialog(
        content: Text(
          message,
          textAlign: TextAlign.center,
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('OK'),
          ),
        ],
      ),
    );
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
    final statusLower = booking.status.toLowerCase();
    final statusColor = statusLower == 'reserved'
      ? scheme.primary
      : statusLower == 'active'
        ? const Color(0xFFFFA726)
        : scheme.error;
    final created = booking.createdAt != null
        ? DateTime.fromMillisecondsSinceEpoch(booking.createdAt!).toLocal()
        : null;
    final dateText = created != null ? '${_formatDate(created)}' : '';
    final timeText = created != null ? '${_formatTime(created, context)}' : '';

    // Map status to display label and colors to match the design
    final statusLabel = (statusLower == 'reserved' || statusLower == 'active')
      ? 'ACTIVE'
      : statusLower == 'completed'
        ? 'COMPLETED'
        : booking.status.toUpperCase();

    Color tileIconColor;
    Color tileBgColor;
    Color statusChipBg;
    Color statusChipText;

    if (statusLower == 'reserved') {
      tileIconColor = const Color(0xFF1E8E3E);
      tileBgColor = const Color(0xFFE9F6ED);
      statusChipBg = const Color(0xFFECF8F0);
      statusChipText = const Color(0xFF1E8E3E);
    } else if (statusLower == 'active') {
      tileIconColor = const Color(0xFFFF8A00);
      tileBgColor = const Color(0xFFFFF3E0);
      statusChipBg = const Color(0xFFFFF7ED);
      statusChipText = const Color(0xFFFF8A00);
    } else if (statusLower == 'completed') {
      tileIconColor = const Color(0xFF6B7280);
      tileBgColor = const Color(0xFFF3F4F6);
      statusChipBg = const Color(0xFFF8FAFC);
      statusChipText = const Color(0xFF6B7280);
    } else {
      // cancelled or other
      tileIconColor = const Color(0xFFBF3B3B);
      tileBgColor = const Color(0xFFFFF4F4);
      statusChipBg = const Color(0xFFFFF1F2);
      statusChipText = const Color(0xFFBF3B3B);
    }

    return Container(
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(12),
        boxShadow: [
          BoxShadow(
            color: Colors.black.withOpacity(0.02),
            blurRadius: 6,
            offset: const Offset(0, 2),
          ),
        ],
        border: Border.all(color: scheme.outlineVariant.withOpacity(0.06)),
      ),
      child: Column(
        children: [
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 14),
            child: Row(
              children: [
                Container(
                  width: 48,
                  height: 48,
                  decoration: BoxDecoration(
                    color: tileBgColor,
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(
                    Icons.directions_bus_filled,
                    color: tileIconColor,
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text(
                              '${booking.pickupStop.toUpperCase()}  →  ${booking.destinationStop.toUpperCase()}',
                              style: Theme.of(context).textTheme.titleSmall
                                  ?.copyWith(fontWeight: FontWeight.w800),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Container(
                            padding: const EdgeInsets.symmetric(
                              horizontal: 8,
                              vertical: 4,
                            ),
                            decoration: BoxDecoration(
                              color: statusChipBg,
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Text(
                              statusLabel,
                              style: Theme.of(context).textTheme.labelSmall
                                  ?.copyWith(
                                    color: statusChipText,
                                    fontWeight: FontWeight.w700,
                                  ),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          Icon(
                            Icons.calendar_month_outlined,
                            size: 16,
                            color: scheme.onSurfaceVariant,
                          ),
                          const SizedBox(width: 8),
                          Text(
                            dateText,
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: scheme.onSurfaceVariant),
                          ),
                          const SizedBox(width: 12),
                          Icon(
                            Icons.access_time,
                            size: 16,
                            color: scheme.onSurfaceVariant,
                          ),
                          const SizedBox(width: 8),
                          Text(
                            timeText,
                            style: Theme.of(context).textTheme.bodySmall
                                ?.copyWith(color: scheme.onSurfaceVariant),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                if (!booking.isActive && onCancel != null)
                  IconButton(
                    onPressed: onCancel,
                    icon: Icon(Icons.delete_outline, color: scheme.error),
                    tooltip: 'Delete booking',
                  ),
              ],
            ),
          ),
          const Divider(height: 1),
          InkWell(
            onTap: onOpen,
            child: Padding(
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 12),
              child: Row(
                children: [
                  Text(
                    'View Details',
                    style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                      color: const Color(0xFF0F9D58),
                    ),
                  ),
                  const Spacer(),
                  Icon(Icons.chevron_right, color: scheme.onSurfaceVariant),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _formatTime(DateTime d, BuildContext context) {
    final t = TimeOfDay.fromDateTime(d);
    return t.format(context);
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
  bool _isDeleting = false;
  bool _isDownloading = false;

  BookingRecord get booking => widget.booking;

  @override
  Widget build(BuildContext context) {
    try {
        final scheme = Theme.of(context).colorScheme;
        final receipt = _receiptFromBooking(booking);
        final statusLower = booking.status.toLowerCase();
        final statusColor = statusLower == 'reserved'
          ? scheme.primary
          : statusLower == 'active'
            ? const Color(0xFFFFA726)
            : scheme.error;

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
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 20),
          children: [
            Center(
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 10,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: statusColor.withOpacity(0.12),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text(
                  booking.status.toUpperCase(),
                  style: Theme.of(context).textTheme.labelSmall?.copyWith(
                    color: statusColor,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
            ),
            const SizedBox(height: 12),
            Container(
              padding: const EdgeInsets.all(18),
              decoration: BoxDecoration(
                color: scheme.surface,
                borderRadius: BorderRadius.circular(14),
                border: Border.all(
                  color: scheme.outlineVariant.withOpacity(0.12),
                ),
              ),
              child: Column(
                children: [
                  SizedBox(
                    height: 220,
                    width: 220,
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
                  // Codes row (e.g. CEDAT -> COCIS)
                  Text(
                    '${booking.pickupStop.toUpperCase()}  →  ${booking.destinationStop.toUpperCase()}',
                    style: Theme.of(context).textTheme.titleMedium?.copyWith(
                      fontWeight: FontWeight.w800,
                    ),
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(
                        Icons.calendar_month_outlined,
                        size: 16,
                        color: scheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        booking.createdAt != null
                            ? _formatDate(
                                DateTime.fromMillisecondsSinceEpoch(
                                  booking.createdAt!,
                                ).toLocal(),
                              )
                            : '',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                      const SizedBox(width: 12),
                      Icon(
                        Icons.access_time,
                        size: 16,
                        color: scheme.onSurfaceVariant,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        booking.createdAt != null
                            ? TimeOfDay.fromDateTime(
                                DateTime.fromMillisecondsSinceEpoch(
                                  booking.createdAt!,
                                ).toLocal(),
                              ).format(context)
                            : '',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                          color: scheme.onSurfaceVariant,
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    child: OutlinedButton.icon(
                      onPressed: _isDownloading ? null : _downloadTicket,
                      icon: _isDownloading
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.download_outlined),
                      label: const Text('Download'),
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            Card(
              elevation: 0,
              shape: RoundedRectangleBorder(
                borderRadius: BorderRadius.circular(12),
              ),
              child: Padding(
                padding: const EdgeInsets.all(12),
                child: Column(
                  children: [
                    _InfoRow(
                      icon: Icons.location_on_outlined,
                      label: 'Pickup',
                      value: booking.pickupStop,
                    ),
                    _InfoRow(
                      icon: Icons.location_on,
                      label: 'Destination',
                      value: booking.destinationStop,
                    ),
                    _InfoRow(
                      icon: Icons.event,
                      label: 'Shuttle Date',
                      value: booking.createdAt != null
                          ? DateTime.fromMillisecondsSinceEpoch(
                              booking.createdAt!,
                            ).toLocal().toIso8601String().split('T').first
                          : '',
                    ),
                    _InfoRow(
                      icon: Icons.access_time,
                      label: 'Time',
                      value: booking.createdAt != null
                          ? TimeOfDay.fromDateTime(
                              DateTime.fromMillisecondsSinceEpoch(
                                booking.createdAt!,
                              ).toLocal(),
                            ).format(context)
                          : '',
                    ),
                    _InfoRow(
                      icon: Icons.confirmation_number_outlined,
                      label: 'Ticket ID',
                      value: booking.bookingId,
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 18),
            // Action buttons: Download already provided above. Show cancel for
            // active bookings and delete for past bookings.
            SizedBox(
              width: double.infinity,
              height: 54,
              child: booking.isActive
                  ? FilledButton.icon(
                      onPressed: _isCancelling ? null : _cancelBooking,
                      icon: _isCancelling
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.delete_outline),
                      label: const Text('Cancel Booking'),
                      style: FilledButton.styleFrom(
                        backgroundColor: scheme.error,
                        foregroundColor: scheme.onError,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
                    )
                  : FilledButton.icon(
                      onPressed: _isDeleting ? null : _deleteBooking,
                      icon: _isDeleting
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2),
                            )
                          : const Icon(Icons.delete_forever),
                      label: const Text('Delete Booking'),
                      style: FilledButton.styleFrom(
                        backgroundColor: scheme.error,
                        foregroundColor: scheme.onError,
                        shape: RoundedRectangleBorder(
                          borderRadius: BorderRadius.circular(12),
                        ),
                      ),
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

  Future<void> _downloadTicket() async {
    setState(() => _isDownloading = true);
    try {
      final painter = QrPainter(
        data: _receiptFromBooking(booking).qrPayload,
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
      if (bytes == null) throw StateError('Could not render QR code.');

      final downloaded = await downloadTicketPng(
        fileName: 'shuttlego-ticket-${booking.bookingId}.png',
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
                  : 'Download is available on web only.',
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

  Future<void> _deleteBooking() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete booking'),
        content: const Text('Delete this booking permanently?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (!mounted || confirm != true) return;

    setState(() => _isDeleting = true);
    try {
      await widget.service.deleteBooking(booking: booking);
      if (!mounted) return;
      ScaffoldMessenger.of(context)
        ..clearSnackBars()
        ..showSnackBar(const SnackBar(content: Text('Booking deleted.')));
      Navigator.of(context).pop();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context)
        ..clearSnackBars()
        ..showSnackBar(SnackBar(content: Text('Delete failed. $e')));
    } finally {
      if (mounted) setState(() => _isDeleting = false);
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

class _InfoRow extends StatelessWidget {
  const _InfoRow({
    required this.icon,
    required this.label,
    required this.value,
  });

  final IconData icon;
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    final scheme = Theme.of(context).colorScheme;
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 8),
      child: Row(
        children: [
          Icon(icon, size: 18, color: scheme.onSurfaceVariant),
          const SizedBox(width: 12),
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
              style: Theme.of(
                context,
              ).textTheme.bodyMedium?.copyWith(fontWeight: FontWeight.w600),
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
