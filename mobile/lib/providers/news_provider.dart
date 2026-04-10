import 'package:flutter/material.dart';
import '../models/news_model.dart';
import '../services/api_service.dart';

class NewsProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();
  
  List<NewsModel> news = [];
  List<String> categories = ['all'];
  String activeCategory = 'all';
  String _language = 'en'; // Default
  bool isLoading = false;
  bool isFirstRun = true; // For language selection overlay

  String get language => _language;

  Future<void> fetchCategories() async {
    try {
      final response = await _apiService.getCategories();
      if (response != null && response['success']) {
        categories = List<String>.from(response['data']);
        notifyListeners();
      }
    } catch (e) {
      debugPrint('Error fetching categories: $e');
    }
  }

  Future<void> fetchNews({bool reset = false}) async {
    if (reset) {
      news.clear();
      notifyListeners();
    }
    
    isLoading = true;
    notifyListeners();

    try {
      final response = await _apiService.getNews(
        category: activeCategory,
        language: _language,
        offset: reset ? 0 : news.length,
      );

      if (response != null && response['success']) {
        final List newArticles = response['data'];
        news.addAll(newArticles.map((json) => NewsModel.fromJson(json)).toList());
        isFirstRun = false;
      }
    } catch (e) {
      debugPrint('Error fetching news: $e');
    } finally {
      isLoading = false;
      notifyListeners();
    }
  }

  void setCategory(String category) {
    activeCategory = category;
    fetchNews(reset: true);
  }

  void setLanguage(String code) {
    if (_language != code) {
      _language = code;
      news.clear(); // HARD PURGE
      notifyListeners();
      fetchNews(reset: true);
    }
  }

  void triggerSync() async {
    await _apiService.triggerSync();
    fetchNews(reset: true);
  }
}
