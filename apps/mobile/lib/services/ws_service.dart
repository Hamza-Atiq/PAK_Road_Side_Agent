// WebSocket subscription for live incident updates with auto-reconnect.
//
// Bearer token is passed as query param `?token=...` because WS spec doesn't
// allow custom headers. Reconnects with exponential backoff (1s, 2s, 4s, 8s…
// up to 30s) whenever the connection drops unexpectedly.

import 'dart:async';
import 'dart:convert';

import 'package:web_socket_channel/web_socket_channel.dart';

import '../config.dart';

class IncidentWsHandle {
  IncidentWsHandle._(this._controller);
  final StreamController<Map<String, dynamic>> _controller;
  bool _closed = false;

  Stream<Map<String, dynamic>> get stream => _controller.stream;

  Future<void> close() async {
    _closed = true;
    await _controller.close();
  }

  bool get isClosed => _closed;
}

class WsService {
  static IncidentWsHandle subscribeIncident({
    required String incidentId,
    required String accessToken,
  }) {
    final controller = StreamController<Map<String, dynamic>>.broadcast();
    final handle = IncidentWsHandle._(controller);
    _connect(incidentId, accessToken, handle, controller, 1);
    return handle;
  }

  static void _connect(
    String incidentId,
    String accessToken,
    IncidentWsHandle handle,
    StreamController<Map<String, dynamic>> controller,
    int delaySecs,
  ) {
    if (handle.isClosed) return;

    final uri = Uri.parse(
        '${RsConfig.wsBaseUrl}/ws/incidents/$incidentId?token=$accessToken');
    WebSocketChannel? channel;
    try {
      channel = WebSocketChannel.connect(uri);
    } catch (_) {
      _scheduleReconnect(incidentId, accessToken, handle, controller, delaySecs);
      return;
    }

    channel.stream.listen(
      (raw) {
        if (handle.isClosed) return;
        try {
          final msg = raw is String
              ? jsonDecode(raw) as Map<String, dynamic>
              : <String, dynamic>{'raw': raw.toString()};
          controller.add(msg);
        } catch (_) {}
      },
      onError: (_) {
        _scheduleReconnect(incidentId, accessToken, handle, controller, delaySecs);
      },
      onDone: () {
        // Reconnect unless the handle was deliberately closed
        if (!handle.isClosed) {
          _scheduleReconnect(incidentId, accessToken, handle, controller, delaySecs);
        }
      },
      cancelOnError: true,
    );
  }

  static void _scheduleReconnect(
    String incidentId,
    String accessToken,
    IncidentWsHandle handle,
    StreamController<Map<String, dynamic>> controller,
    int delaySecs,
  ) {
    if (handle.isClosed) return;
    final next = delaySecs > 30 ? 30 : delaySecs;
    Future.delayed(Duration(seconds: next), () {
      _connect(incidentId, accessToken, handle, controller, next * 2);
    });
  }
}
