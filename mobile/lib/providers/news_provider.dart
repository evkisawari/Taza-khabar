import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/article.dart';
import '../services/api_service.dart';

class NewsProvider with ChangeNotifier {
  final ApiService _apiService = ApiService();
  List<Article> _news = [];
  List<String> _categories = ['all'];
  bool _isLoading = false;
  String _activeCategory = 'all';
  String _language = 'en';
  int _offset = 0;
  bool _isFirstRun = true;

  List<Article> get news => _news;
  List<String> get categories => _categories;
  bool get isLoading => _isLoading;
  String get activeCategory => _activeCategory;
  String get language => _language;
  bool get isFirstRun => _isFirstRun;

  NewsProvider() {
    _initPreferences();
  }

  Future<void> _initPreferences() async {
    final prefs = await SharedPreferences.getInstance();
    _language = prefs.getString('language') ?? 'en';
    _isFirstRun = prefs.getBool('isFirstRun') ?? true;
    notifyListeners();
    fetchNews();
  }

  Future<void> setLanguage(String lang) async {
    _language = lang;
    _isFirstRun = false;
    _news = []; 
    _isLoading = true;
    notifyListeners();
    
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('language', lang);
    await prefs.setBool('isFirstRun', false);
    
    await fetchCategories();
    await fetchNews(reset: true);
  }

  Future<void> fetchCategories() async {
    // Priority Categories for Taza Khabar
    _categories = ['All', 'Iran War', 'National', 'Politics', 'Technology', 'Sports', 'Entertainment', 'Business', 'International', 'Lifestyle'];
    notifyListeners();
  }

  Future<void> triggerSync() async {
    try {
      await _apiService.triggerSync();
    } catch (e) {
      print('Sync Trigger Error: $e');
    }
  }

  Future<void> fetchNews({bool reset = false}) async {
    if (_isLoading && !reset) return;
    
    if (reset) {
      _offset = 0;
      _news = [];
    }

    _isLoading = true;
    notifyListeners();

    try {
      final newArticles = await _apiService.getNews(
        category: _activeCategory,
        language: _language,
        offset: _offset,
      );
      
      _news.addAll(newArticles);
      _offset += newArticles.length;
    } catch (e) {
      print('Provider Error: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  void setCategory(String category) {
    _activeCategory = category;
    fetchNews(reset: true);
  }
}
鼓
