import 'package:dio/dio.dart';
import '../models/article.dart';

class ApiService {
  final Dio _dio = Dio(BaseOptions(
    // AWS Global Production Server
    baseUrl: 'http://13.48.1.16:8000',
    connectTimeout: const Duration(seconds: 15),
    receiveTimeout: const Duration(seconds: 15),
  ));

  Future<List<Article>> getNews({String category = 'all', String language = 'en', int limit = 10, int offset = 0}) async {
    int retryCount = 0;
    const int maxRetries = 3;

    while (retryCount < maxRetries) {
      try {
        final response = await _dio.get('/api/news', queryParameters: {
          'category': category,
          'language': language,
          'limit': limit,
          'offset': offset,
        });

        if (response.statusCode == 200 && response.data['success'] == true) {
          List data = response.data['data'];
          return data.map((json) => Article.fromJson(json)).toList();
        }
        return [];
      } catch (e) {
        retryCount++;
        print('API Attempt $retryCount failed: $e');
        if (retryCount >= maxRetries) return [];
        await Future.delayed(const Duration(seconds: 2));
      }
    }
    return [];
  }

  Future<List<String>> getCategories() async {
    try {
      final response = await _dio.get('/api/categories');
      if (response.statusCode == 200 && response.data['success'] == true) {
        return List<String>.from(response.data['data']);
      }
      return ['all'];
    } catch (e) {
      print('API Categories Error: $e');
      return ['all'];
    }
  }

  Future<void> triggerSync() async {
    try {
      await _dio.post('/api/sync');
    } catch (e) {
      print('API Sync Trigger Error: $e');
    }
  }
}

