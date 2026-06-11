// Live tracking. Polls /api/incidents/:id on load + subscribes to
// WS /ws/incidents/:id. Renders status stepper, flutter_map with two pins
// (you = red, provider = orange), and a provider card with tap-to-call.

import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:latlong2/latlong.dart';
import 'package:url_launcher/url_launcher.dart';

import '../models/models.dart';
import '../services/providers.dart';
import '../services/ws_service.dart';
import '../theme/colors.dart';

class IncidentStatusScreen extends ConsumerStatefulWidget {
  const IncidentStatusScreen({super.key, required this.incidentId});
  final String incidentId;

  @override
  ConsumerState<IncidentStatusScreen> createState() => _IncidentStatusScreenState();
}

class _IncidentStatusScreenState extends ConsumerState<IncidentStatusScreen> {
  Incident? _incident;
  String? _error;
  IncidentWsHandle? _ws;
  Timer? _pollTimer;
  bool _cancelling = false;

  static const _cancellableStatuses = {'REPORTED', 'ANALYZING', 'NO_PROVIDER'};
  static const _terminalStatuses = {'COMPLETED', 'CLOSED'};

  @override
  void initState() {
    super.initState();
    _bootstrap();
  }

  @override
  void dispose() {
    _ws?.close();
    _pollTimer?.cancel();
    super.dispose();
  }

  Future<void> _bootstrap() async {
    try {
      final inc = await ref.read(incidentsServiceProvider).getOne(widget.incidentId);
      if (!mounted) return;
      setState(() => _incident = inc);
      await _connectWs();
      _startPolling();
    } catch (_) {
      setState(() => _error = 'Could not load this incident.');
    }
  }

  void _startPolling() {
    _pollTimer = Timer.periodic(const Duration(seconds: 15), (_) async {
      if (!mounted) return;
      final current = _incident;
      if (current != null && _terminalStatuses.contains(current.status)) {
        _pollTimer?.cancel();
        return;
      }
      try {
        final inc = await ref.read(incidentsServiceProvider).getOne(widget.incidentId);
        if (mounted) setState(() => _incident = inc);
      } catch (_) {}
    });
  }

  Future<void> _cancelIncident() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        title: const Text('Cancel request?'),
        content: const Text('Are you sure you want to cancel this assistance request?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Keep')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            style: TextButton.styleFrom(foregroundColor: RsColors.emergency),
            child: const Text('Cancel request'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    setState(() => _cancelling = true);
    try {
      await ref.read(incidentsServiceProvider).cancel(widget.incidentId);
      if (!mounted) return;
      context.pop();
    } catch (_) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not cancel. Please try again.')),
      );
    } finally {
      if (mounted) setState(() => _cancelling = false);
    }
  }

  Future<void> _connectWs() async {
    final api = ref.read(apiClientProvider);
    final token = await api.getAccessToken();
    if (token == null) return;
    final handle = WsService.subscribeIncident(
      incidentId: widget.incidentId,
      accessToken: token,
    );
    _ws = handle;
    handle.stream.listen((msg) {
      final inc = msg['incident'];
      if (inc is Map<String, dynamic>) {
        setState(() => _incident = Incident.fromJson(inc));
      }
    }, onError: (_) {/* WS dropped — page still works via initial fetch */});
  }

  @override
  Widget build(BuildContext context) {
    if (_error != null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Live tracking')),
        body: Center(child: Text(_error!)),
      );
    }
    final inc = _incident;
    if (inc == null) {
      return Scaffold(
        appBar: AppBar(title: const Text('Live tracking')),
        body: const Center(child: CircularProgressIndicator()),
      );
    }

    final center = LatLng(inc.lat, inc.lng);
    final markers = <Marker>[
      Marker(
        point: center,
        width: 36,
        height: 36,
        child: const _Pin(color: RsColors.emergency, label: 'You'),
      ),
      if (inc.provider?.lastLat != null && inc.provider?.lastLng != null)
        Marker(
          point: LatLng(inc.provider!.lastLat!, inc.provider!.lastLng!),
          width: 36,
          height: 36,
          child: _Pin(
              color: RsColors.warning,
              label: inc.provider?.name?.split(' ').first ?? 'Pro'),
        ),
    ];

    return Scaffold(
      appBar: AppBar(title: const Text('Live tracking')),
      body: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _Stepper(status: inc.status),
          const SizedBox(height: 16),
          ClipRRect(
            borderRadius: BorderRadius.circular(16),
            child: SizedBox(
              height: 240,
              child: FlutterMap(
                options: MapOptions(initialCenter: center, initialZoom: 14),
                children: [
                  TileLayer(
                    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'com.roadsideagent.mobile',
                  ),
                  MarkerLayer(markers: markers),
                ],
              ),
            ),
          ),
          const SizedBox(height: 16),
          if (inc.provider != null)
            _ProviderCard(provider: inc.provider!)
          else
            _SearchingCard(),
          const SizedBox(height: 16),
          _DetailsCard(incident: inc),
          if (_cancellableStatuses.contains(inc.status)) ...[
            const SizedBox(height: 8),
            OutlinedButton(
              onPressed: _cancelling ? null : _cancelIncident,
              style: OutlinedButton.styleFrom(
                foregroundColor: RsColors.emergency,
                side: const BorderSide(color: RsColors.emergency),
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              child: _cancelling
                  ? const SizedBox(
                      height: 18,
                      width: 18,
                      child: CircularProgressIndicator(strokeWidth: 2, color: RsColors.emergency),
                    )
                  : const Text('Cancel Request'),
            ),
          ],
        ],
      ),
    );
  }
}

class _Stepper extends StatelessWidget {
  const _Stepper({required this.status});
  final String status;

  static const _steps = ['REPORTED', 'ASSIGNED', 'EN_ROUTE', 'ARRIVED', 'COMPLETED'];

  @override
  Widget build(BuildContext context) {
    final idx = _steps.indexOf(status);
    return Row(
      children: List.generate(_steps.length, (i) {
        final active = i <= idx && idx >= 0;
        return Expanded(
          child: Row(
            children: [
              Container(
                width: 18,
                height: 18,
                decoration: BoxDecoration(
                  color: active ? RsColors.brandPrimary : Colors.white,
                  shape: BoxShape.circle,
                  border: Border.all(
                      color: active ? RsColors.brandPrimary : const Color(0xFFCBD5E1),
                      width: 2),
                ),
                child: active
                    ? const Icon(Icons.check, size: 12, color: Colors.white)
                    : null,
              ),
              if (i < _steps.length - 1)
                Expanded(
                  child: Container(
                    height: 2,
                    color: i < idx ? RsColors.brandPrimary : const Color(0xFFCBD5E1),
                  ),
                ),
            ],
          ),
        );
      }),
    );
  }
}

class _Pin extends StatelessWidget {
  const _Pin({required this.color, required this.label});
  final Color color;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: color,
        shape: BoxShape.circle,
        border: Border.all(color: Colors.white, width: 3),
        boxShadow: [BoxShadow(color: color.withOpacity(0.6), blurRadius: 6)],
      ),
      alignment: Alignment.center,
      child: Text(label.substring(0, label.length > 2 ? 2 : label.length).toUpperCase(),
          style: const TextStyle(
              color: Colors.white, fontSize: 10, fontWeight: FontWeight.w800)),
    );
  }
}

class _ProviderCard extends StatelessWidget {
  const _ProviderCard({required this.provider});
  final IncidentProviderSummary provider;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: const Color(0xFFE2E8F0)),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          const CircleAvatar(
            radius: 24,
            backgroundColor: Color(0xFFE0F2FE),
            child: Text('🔧', style: TextStyle(fontSize: 22)),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(provider.name ?? 'Verified provider',
                    style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
                if (provider.vehicleInfo != null)
                  Text(provider.vehicleInfo!,
                      style:
                          const TextStyle(color: RsColors.textMuted, fontSize: 12)),
                if (provider.rating != null)
                  Text('★ ${provider.rating!.toStringAsFixed(1)}',
                      style: const TextStyle(fontSize: 12)),
              ],
            ),
          ),
          if (provider.phone.isNotEmpty)
            ElevatedButton(
              onPressed: () => launchUrl(Uri.parse('tel:${provider.phone}')),
              child: const Text('Call'),
            ),
        ],
      ),
    );
  }
}

class _SearchingCard extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: const Color(0xFFE2E8F0)),
        borderRadius: BorderRadius.circular(14),
      ),
      child: const Column(children: [
        Text('🛰️', style: TextStyle(fontSize: 28)),
        SizedBox(height: 6),
        Text('Finding the closest help',
            style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        SizedBox(height: 4),
        Text('Usually under 30 seconds.',
            style: TextStyle(color: RsColors.textMuted, fontSize: 12)),
      ]),
    );
  }
}

class _DetailsCard extends StatelessWidget {
  const _DetailsCard({required this.incident});
  final Incident incident;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: Colors.white,
        border: Border.all(color: const Color(0xFFE2E8F0)),
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text('Incident details',
              style: TextStyle(fontWeight: FontWeight.w700)),
          const SizedBox(height: 8),
          _row('Reported', incident.createdAt.toLocal().toString().substring(0, 16)),
          if (incident.serviceType != null) _row('Issue', incident.serviceType!),
          if (incident.diagnosis != null) _row('Diagnosis', incident.diagnosis!),
          if (incident.address != null) _row('Address', incident.address!),
        ],
      ),
    );
  }

  Widget _row(String k, String v) => Padding(
        padding: const EdgeInsets.symmetric(vertical: 3),
        child: Row(children: [
          Text('$k  ', style: const TextStyle(color: RsColors.textMuted, fontSize: 13)),
          Expanded(
              child: Text(v,
                  style: const TextStyle(fontSize: 13), textAlign: TextAlign.right)),
        ]),
      );
}
