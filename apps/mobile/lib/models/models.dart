// Plain Dart models that mirror @roadside/types. Hand-rolled, no codegen.

class AuthUser {
  AuthUser({
    required this.id,
    required this.phone,
    required this.name,
    required this.role,
    required this.isPhoneVerified,
  });

  final String id;
  final String phone;
  final String? name;
  final String role;
  final bool isPhoneVerified;

  factory AuthUser.fromJson(Map<String, dynamic> j) => AuthUser(
        id: j['id'] as String,
        phone: j['phone'] as String,
        name: j['name'] as String?,
        role: j['role'] as String,
        isPhoneVerified: j['is_phone_verified'] as bool? ?? false,
      );
}

class IncidentProviderSummary {
  IncidentProviderSummary({
    required this.id,
    required this.name,
    required this.phone,
    required this.rating,
    required this.vehicleInfo,
    required this.lastLat,
    required this.lastLng,
  });

  final String id;
  final String? name;
  final String phone;
  final double? rating;
  final String? vehicleInfo;
  final double? lastLat;
  final double? lastLng;

  factory IncidentProviderSummary.fromJson(Map<String, dynamic> j) =>
      IncidentProviderSummary(
        id: j['id'] as String,
        name: j['name'] as String?,
        phone: j['phone'] as String? ?? '',
        rating: (j['rating'] as num?)?.toDouble(),
        vehicleInfo: j['vehicle_info'] as String?,
        lastLat: (j['last_lat'] as num?)?.toDouble(),
        lastLng: (j['last_lng'] as num?)?.toDouble(),
      );
}

class Incident {
  Incident({
    required this.id,
    required this.status,
    required this.lat,
    required this.lng,
    required this.address,
    required this.description,
    required this.diagnosis,
    required this.serviceType,
    required this.imageUrl,
    required this.createdAt,
    required this.provider,
  });

  final String id;
  final String status;
  final double lat;
  final double lng;
  final String? address;
  final String? description;
  final String? diagnosis;
  final String? serviceType;
  final String? imageUrl;
  final DateTime createdAt;
  final IncidentProviderSummary? provider;

  factory Incident.fromJson(Map<String, dynamic> j) => Incident(
        id: j['id'] as String,
        status: j['status'] as String,
        lat: (j['lat'] as num).toDouble(),
        lng: (j['lng'] as num).toDouble(),
        address: j['address'] as String?,
        description: j['description'] as String?,
        diagnosis: j['diagnosis'] as String?,
        serviceType: j['service_type'] as String?,
        imageUrl: j['image_url'] as String?,
        createdAt: DateTime.parse(j['created_at'] as String),
        provider: j['provider'] == null
            ? null
            : IncidentProviderSummary.fromJson(j['provider'] as Map<String, dynamic>),
      );
}
