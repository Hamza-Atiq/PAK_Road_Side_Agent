// Dio-based HTTP client mirroring @roadside/api-client (TS).
//
// Single-flight JWT refresh; refresh token lives in HttpOnly cookie on web —
// on mobile we store it in flutter_secure_storage (set via /api/auth/login).

import 'package:dio/dio.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

const _kAccessTokenKey = 'roadside_access_token';
const _kRefreshTokenKey = 'roadside_refresh_token';

class ApiClient {
  ApiClient({required this.baseUrl})
      : dio = Dio(BaseOptions(
          baseUrl: baseUrl,
          connectTimeout: const Duration(seconds: 12),
          receiveTimeout: const Duration(seconds: 30),
        )) {
    dio.interceptors.add(InterceptorsWrapper(
      onRequest: _onRequest,
      onError: _onError,
    ));
  }

  final String baseUrl;
  final Dio dio;
  final _storage = const FlutterSecureStorage();

  Future<String?> getAccessToken() => _storage.read(key: _kAccessTokenKey);
  Future<void> setSession({required String accessToken, String? refreshToken}) async {
    await _storage.write(key: _kAccessTokenKey, value: accessToken);
    if (refreshToken != null) {
      await _storage.write(key: _kRefreshTokenKey, value: refreshToken);
    }
  }

  Future<void> clear() async {
    await _storage.delete(key: _kAccessTokenKey);
    await _storage.delete(key: _kRefreshTokenKey);
  }

  Future<void> _onRequest(RequestOptions opts, RequestInterceptorHandler handler) async {
    final token = await getAccessToken();
    if (token != null && token.isNotEmpty) {
      opts.headers['Authorization'] = 'Bearer $token';
    }
    handler.next(opts);
  }

  bool _refreshing = false;

  Future<void> _onError(DioException err, ErrorInterceptorHandler handler) async {
    final response = err.response;
    final req = err.requestOptions;

    final shouldRefresh = response?.statusCode == 401 &&
        !req.extra.containsKey('retried') &&
        !req.path.endsWith('/api/auth/refresh') &&
        !req.path.endsWith('/api/auth/login');

    if (!shouldRefresh) {
      handler.next(err);
      return;
    }

    if (_refreshing) {
      handler.next(err);
      return;
    }

    _refreshing = true;
    try {
      final refresh = await _storage.read(key: _kRefreshTokenKey);
      if (refresh == null) {
        await clear();
        handler.next(err);
        return;
      }
      final r = await Dio().post(
        '$baseUrl/api/auth/refresh',
        options: Options(headers: {'Authorization': 'Bearer $refresh'}),
      );
      final newToken = r.data['access_token'] as String?;
      if (newToken == null) {
        await clear();
        handler.next(err);
        return;
      }
      await setSession(accessToken: newToken);
      req.extra['retried'] = true;
      req.headers['Authorization'] = 'Bearer $newToken';
      final retry = await dio.fetch(req);
      handler.resolve(retry);
    } catch (_) {
      await clear();
      handler.next(err);
    } finally {
      _refreshing = false;
    }
  }
}
