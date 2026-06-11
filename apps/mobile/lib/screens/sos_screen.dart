// SOS report flow. Issue picker → location confirm → optional photo → submit.

import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';
import 'package:image_picker/image_picker.dart';

import '../services/location_service.dart';
import '../services/providers.dart';
import '../theme/colors.dart';

class SosScreen extends ConsumerStatefulWidget {
  const SosScreen({super.key});

  @override
  ConsumerState<SosScreen> createState() => _SosScreenState();
}

class _SosScreenState extends ConsumerState<SosScreen> {
  String? _serviceType;
  double? _lat;
  double? _lng;
  String? _locationLabel;
  File? _image;
  final _description = TextEditingController();
  bool _gettingLocation = false;
  bool _submitting = false;
  String? _error;

  static const _issues = [
    ('🚛', 'tow', 'Tow', "Vehicle won't move"),
    ('🔋', 'battery', 'Battery', 'Jump start needed'),
    ('🛞', 'tire', 'Flat tire', 'Change or repair'),
    ('⛽', 'fuel', 'Fuel', 'Out of gas'),
    ('🔑', 'lockout', 'Lockout', 'Keys locked in'),
    ('🔧', 'other', 'Other', 'Describe the issue'),
  ];

  @override
  void initState() {
    super.initState();
    _captureLocation();
  }

  @override
  void dispose() {
    _description.dispose();
    super.dispose();
  }

  Future<void> _captureLocation() async {
    setState(() => _gettingLocation = true);
    try {
      final pos = await LocationService.currentPosition();
      setState(() {
        _lat = pos.latitude;
        _lng = pos.longitude;
        _locationLabel =
            '${pos.latitude.toStringAsFixed(5)}, ${pos.longitude.toStringAsFixed(5)}';
      });
    } catch (e) {
      setState(() => _error = e.toString().replaceFirst('Bad state: ', ''));
    } finally {
      if (mounted) setState(() => _gettingLocation = false);
    }
  }

  Future<void> _pickImage() async {
    final picker = ImagePicker();
    final src = await showModalBottomSheet<ImageSource>(
      context: context,
      builder: (_) => SafeArea(
        child: Wrap(children: [
          ListTile(
            leading: const Icon(Icons.camera_alt_outlined),
            title: const Text('Take a photo'),
            onTap: () => Navigator.pop(context, ImageSource.camera),
          ),
          ListTile(
            leading: const Icon(Icons.photo_outlined),
            title: const Text('Choose from gallery'),
            onTap: () => Navigator.pop(context, ImageSource.gallery),
          ),
        ]),
      ),
    );
    if (src == null) return;
    final picked = await picker.pickImage(source: src, maxWidth: 1600, imageQuality: 80);
    if (picked != null) setState(() => _image = File(picked.path));
  }

  bool get _canSubmit =>
      _serviceType != null && _lat != null && _lng != null && !_submitting;

  Future<void> _submit() async {
    if (!_canSubmit) return;
    setState(() {
      _submitting = true;
      _error = null;
    });
    try {
      final id = await ref.read(incidentsServiceProvider).create(
            lat: _lat!,
            lng: _lng!,
            serviceType: _serviceType,
            description: _description.text.trim().isEmpty
                ? null
                : _description.text.trim(),
            image: _image,
          );
      if (!mounted) return;
      context.push('/incidents/$id');
    } catch (_) {
      setState(() => _error =
          'Couldn\'t send your report. Check your connection and try again.');
    } finally {
      if (mounted) setState(() => _submitting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Request Assistance')),
      body: SafeArea(
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            const Text('What happened?',
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700)),
            const SizedBox(height: 10),
            GridView.count(
              crossAxisCount: 2,
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              childAspectRatio: 1.15,
              children: _issues
                  .map((it) => _IssueTile(
                        emoji: it.$1,
                        title: it.$3,
                        subtitle: it.$4,
                        selected: _serviceType == it.$2,
                        onTap: () => setState(() => _serviceType = it.$2),
                      ))
                  .toList(),
            ),
            const SizedBox(height: 16),
            _Card(
              title: 'Your location',
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      _gettingLocation
                          ? 'Getting GPS…'
                          : (_locationLabel ?? 'Location unavailable'),
                      style: const TextStyle(fontSize: 14),
                    ),
                  ),
                  TextButton.icon(
                    onPressed: _gettingLocation ? null : _captureLocation,
                    icon: const Icon(Icons.refresh, size: 18),
                    label: const Text('Refresh'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            _Card(
              title: 'Photo (optional)',
              child: Row(
                children: [
                  if (_image != null)
                    Padding(
                      padding: const EdgeInsets.only(right: 12),
                      child: ClipRRect(
                        borderRadius: BorderRadius.circular(8),
                        child: Image.file(_image!, width: 64, height: 64, fit: BoxFit.cover),
                      ),
                    ),
                  Expanded(
                    child: Text(
                      _image == null
                          ? 'Add a photo to help diagnose faster.'
                          : 'Photo attached.',
                      style: const TextStyle(color: RsColors.textMuted, fontSize: 13),
                    ),
                  ),
                  TextButton(
                    onPressed: _pickImage,
                    child: Text(_image == null ? 'Add' : 'Change'),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            _Card(
              title: 'Anything else? (optional)',
              child: TextField(
                controller: _description,
                maxLines: 3,
                decoration: const InputDecoration(
                  hintText: 'e.g. front-left tire blown, near exit 23',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: 12),
              Text(_error!,
                  style: const TextStyle(color: RsColors.emergency, fontSize: 13)),
            ],
            const SizedBox(height: 20),
            ElevatedButton(
              onPressed: _canSubmit ? _submit : null,
              style: ElevatedButton.styleFrom(
                backgroundColor: RsColors.emergency,
                padding: const EdgeInsets.symmetric(vertical: 18),
              ),
              child: _submitting
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : const Text(
                      'Request Help',
                      style: TextStyle(fontSize: 18, fontWeight: FontWeight.w700),
                    ),
            ),
          ],
        ),
      ),
    );
  }
}

class _IssueTile extends StatelessWidget {
  const _IssueTile({
    required this.emoji,
    required this.title,
    required this.subtitle,
    required this.selected,
    required this.onTap,
  });
  final String emoji;
  final String title;
  final String subtitle;
  final bool selected;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: Colors.white,
          border: Border.all(
            color: selected ? RsColors.brandPrimary : const Color(0xFFE2E8F0),
            width: selected ? 2.5 : 1.5,
          ),
          borderRadius: BorderRadius.circular(18),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(emoji, style: const TextStyle(fontSize: 30)),
            const Spacer(),
            Text(title,
                style: const TextStyle(
                    fontSize: 16, fontWeight: FontWeight.w700, color: RsColors.textPrimary)),
            Text(subtitle,
                style: const TextStyle(fontSize: 11, color: RsColors.textMuted)),
          ],
        ),
      ),
    );
  }
}

class _Card extends StatelessWidget {
  const _Card({required this.title, required this.child});
  final String title;
  final Widget child;

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
          Text(title,
              style: const TextStyle(
                  fontSize: 13, fontWeight: FontWeight.w700, color: RsColors.textPrimary)),
          const SizedBox(height: 8),
          child,
        ],
      ),
    );
  }
}
