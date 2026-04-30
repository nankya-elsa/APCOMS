import 'package:firebase_auth/firebase_auth.dart';
import 'package:flutter/material.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../models/booking_receipt.dart';
import '../models/shuttle_route.dart';
import '../services/booking_service.dart';
import '../widgets/shuttle_location_map.dart';

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
      ),
      body: StreamBuilder(
        stream: _service.watchAvailability(
          shuttleKey: widget.trackedShuttleKey,
        ),
        builder: (context, snapshot) {
          final availability = snapshot.data;
          final canBook = availability?.canBook ?? false;
          final hasValidStops =
              _pickupIndex != null && _destinationIndex != null;
          final canSubmit = canBook && hasValidStops && !_isSubmitting;

          return Stack(
            children: [
              ShuttleLocationMap(
                shuttleKey: widget.trackedShuttleKey,
                height: 380,
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
                        Row(
                          children: [
                            Expanded(
                              child: _LabeledField(
                                label: 'Pick Up',
                                controller: _pickupController,
                                hintText: 'Select pick up stop',
                                readOnly: true,
                                onTap: _isSubmitting
                                    ? null
                                    : () async {
                                        final selected = await _pickStop(
                                          context,
                                          stops: ShuttleRoute.stops,
                                        );
                                        if (!mounted || selected == null) {
                                          return;
                                        }

                                        setState(() {
                                          _pickupIndex = selected;
                                          _pickupController.text =
                                              ShuttleRoute.stops[selected];

                                          final destinationIndex =
                                              _destinationIndex;
                                          if (destinationIndex != null &&
                                              destinationIndex <= selected) {
                                            _destinationIndex = null;
                                            _destinationController.clear();
                                          }
                                        });
                                      },
                              ),
                            ),
                          ],
                        ),
                        const SizedBox(height: 10),
                        Row(
                          children: [
                            Expanded(
                              child: _LabeledField(
                                label: 'Where To',
                                controller: _destinationController,
                                hintText: 'Select destination stop',
                                readOnly: true,
                                onTap: _isSubmitting
                                    ? null
                                    : () async {
                                        final pickupIndex = _pickupIndex;
                                        if (pickupIndex == null) {
                                          _showSnack(
                                            context,
                                            'Select a pickup stop first.',
                                          );
                                          return;
                                        }

                                        final selected = await _pickStop(
                                          context,
                                          stops:
                                              ShuttleRoute.destinationChoicesForPickup(
                                                pickupIndex,
                                              ),
                                        );
                                        if (!mounted || selected == null) {
                                          return;
                                        }

                                        final resolvedIndex =
                                            pickupIndex + 1 + selected;
                                        setState(() {
                                          _destinationIndex = resolvedIndex;
                                          _destinationController.text =
                                              ShuttleRoute.stops[resolvedIndex];
                                        });
                                      },
                              ),
                            ),
                          ],
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
                                    canBook
                                        ? 'Book Now'
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
      _showSnack(context, 'Destination must come after pickup.');
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

  static void _showSnack(BuildContext context, String message) {
    ScaffoldMessenger.of(context)
      ..clearSnackBars()
      ..showSnackBar(SnackBar(content: Text(message)));
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
