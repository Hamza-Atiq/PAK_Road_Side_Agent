// Incidents API client (multipart upload aware).

import 'dart:io';

import 'package:dio/dio.dart';

import '../models/models.dart';
import 'api_client.dart';

class IncidentsService {
  IncidentsService(this._api);
  final ApiClient _api;

  /// POST /api/incidents (multipart). Returns server incident id.
  Future<String> create({
    required double lat,
    required double lng,
    String? description,
    String? address,
    String? serviceType,
    File? image,
  }) async {
    final form = FormData.fromMap({
      'lat': lat.toString(),
      'lng': lng.toString(),
      if (description != null) 'description': description,
      if (address != null) 'address': address,
      if (serviceType != null) 'service_type': serviceType,
      if (image != null)
        'image': await MultipartFile.fromFile(image.path, filename: 'incident.jpg'),
    });
    final r = await _api.dio.post('/api/incidents', data: form);
    return r.data['id'] as String;
  }

  Future<Incident> getOne(String id) async {
    final r = await _api.dio.get('/api/incidents/$id');
    return Incident.fromJson(r.data as Map<String, dynamic>);
  }

  Future<List<Incident>> listMine({int limit = 20}) async {
    final r = await _api.dio
        .get('/api/incidents/my', queryParameters: {'limit': limit});
    final items = (r.data['items'] as List).cast<Map<String, dynamic>>();
    return items.map(Incident.fromJson).toList();
  }
}
