// WebSocket subscription for live incident updates.
//
// Backend protocol mirrors @roadside/api-client connectWS: bearer token sent
// as query param `?token=...` because WS spec doesn't allow custom headers in
// browsers. Mobile follows the same convention for parity.

import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';

class IncidentWsHandle {
  IncidentWsHandle._(this._channel, this.stream);
  final WebSocketChannel _channel;
  final Stream<Map<String, dynamic>> stream;

  Future<void> close() async => _channel.sink.close();
}

class WsService {
  static IncidentWsHandle subscribeIncident({
    required String incidentId,
    required String accessToken,
  }) {
    final uri = Uri.parse(
        '${RsConfig.wsBaseUrl}/ws/incidents/$incidentId?token=$accessToken');
    final channel = WebSocketChannel.connect(uri);
    final stream = channel.stream.map((raw) {
      if (raw is String) {
        try {
          return jsonDecode(raw) as Map<String, dynamic>;
        } catch (_) {
          return <String, dynamic>{'raw': raw};
        }
      }
      return <String, dynamic>{'raw': raw.toString()};
    }).asBroadcastStream();
    return IncidentWsHandle._(channel, stream);
  }
}
