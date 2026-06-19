// Mobile / IO implementation: save file to app documents directory.
import 'dart:typed_data';
import 'dart:io';
import 'package:path/path.dart' as p;
import 'package:path_provider/path_provider.dart';

Future<bool> downloadTicketPngImpl({
  required String fileName,
  required Uint8List bytes,
}) async {
  try {
    // Try to save to a public Downloads folder on Android first so the user
    // can access the file easily. Fall back to app documents directory.
    if (Platform.isAndroid) {
      try {
        final publicDownload = Directory('/storage/emulated/0/Download');
        if (await publicDownload.exists()) {
          final out = File(p.join(publicDownload.path, fileName));
          await out.writeAsBytes(bytes);
          return true;
        }
      } catch (_) {
        // ignore and fall back
      }
    }

    final dir = await getApplicationDocumentsDirectory();
    final downloadsDir = Directory(p.join(dir.path, 'Downloads'));
    if (!await downloadsDir.exists()) {
      await downloadsDir.create(recursive: true);
    }
    final file = File(p.join(downloadsDir.path, fileName));
    await file.writeAsBytes(bytes);
    return true;
  } catch (_) {
    return false;
  }
}
