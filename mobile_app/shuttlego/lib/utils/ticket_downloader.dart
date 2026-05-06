import 'dart:typed_data';

import 'ticket_downloader_stub.dart'
    if (dart.library.html) 'ticket_downloader_web.dart'
    if (dart.library.io) 'ticket_downloader_io.dart';

Future<bool> downloadTicketPng({
  required String fileName,
  required Uint8List bytes,
}) {
  return downloadTicketPngImpl(fileName: fileName, bytes: bytes);
}
