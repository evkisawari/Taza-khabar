import 'package:flutter/material.dart';
import '../models/article.dart';
import '../services/api_service.dart';

class NewsProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();
  
  List<Article> news = [];
  List<String> categories = ['all'];
  String activeCategory = 'all';
  String _language = 'en'; // Default
  bool isLoading = false;
  bool isFirstRun = true;

  String get language => _language;

  Future<void> fetchCategories() async {
    try {
      final categoryList = await _apiService.getCategories();
      categories = categoryList;
      notifyListeners();
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
      final fetchedNews = await _apiService.getNews(
        category: activeCategory,
        language: _language,
        offset: reset ? 0 : news.length,
      );

      if (fetchedNews.isNotEmpty) {
        news.addAll(fetchedNews);
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
      news.clear(); // Total flush to prevent leaking
      notifyListeners();
      fetchNews(reset: true);
    }
  }

  void triggerSync() async {
    await _apiService.triggerSync();
    fetchNews(reset: true);
  }
}

