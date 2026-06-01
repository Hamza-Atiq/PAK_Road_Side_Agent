// Build-time config. Override at run/build with --dart-define.
//
// Examples:
//   flutter run --dart-define=RS_API_BASE_URL=https://api.roadsideagent.com
//   flutter build apk --release --dart-define=RS_API_BASE_URL=https://api.roadsideagent.com

class RsConfig {
  RsConfig._();

  static const String apiBaseUrl = String.fromEnvironment(
    'RS_API_BASE_URL',
    defaultValue: 'http://10.0.2.2:8000',
  );

  static String get wsBaseUrl {
    final base = apiBaseUrl;
    if (base.startsWith('https://')) return 'wss://${base.substring(8)}';
    if (base.startsWith('http://')) return 'ws://${base.substring(7)}';
    return base;
  }
}
