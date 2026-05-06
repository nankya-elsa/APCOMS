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
