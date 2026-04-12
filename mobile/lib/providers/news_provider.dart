import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/article.dart';
import '../services/api_service.dart';

class NewsProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();
  
  List<Article> news = [];
  List<String> categories = ['all'];
  String activeCategory = 'all';
  String _language = 'en'; // Default
  bool isLoading = false;
  bool _isFirstRunFetched = false;
  bool _isInitialized = false;

  NewsProvider() {
    _init();
  }

  Future<void> _init() async {
    await _loadSettings();
    _isInitialized = true;
    notifyListeners();
    // fetchNews is already called inside _loadSettings
  }

  Future<void> _loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    _language = prefs.getString('language') ?? 'en';
    // If language was previously saved, we shouldn't show the first run overlay
    if (prefs.containsKey('language')) {
      _isFirstRunFetched = true;
    }
    notifyListeners();
    await fetchNews(reset: true);
  }

  String get language => _language;
  bool get isFirstRun => _isInitialized && !_isFirstRunFetched && news.isEmpty;

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
    if (isLoading) return; // Prevent concurrent calls
    if (!_isInitialized && !reset) return; // Wait for settings unless it's the internal init call
    
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
        _isFirstRunFetched = true;
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

  void setLanguage(String code) async {
    if (_language != code) {
      _language = code;
      
      // Persist the setting
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('language', code);
      
      _isFirstRunFetched = true;
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

