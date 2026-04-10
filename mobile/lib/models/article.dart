class Article {
  final String id;
  final String title;
  final String content;
  final String author;
  final String imageUrl;
  final String sourceName;
  final String sourceUrl;
  final String category;
  final String language;
  final DateTime createdAt;
  final bool isTrending;

  Article({
    required this.id,
    required this.title,
    required this.content,
    required this.author,
    required this.imageUrl,
    required this.sourceName,
    required this.sourceUrl,
    required this.category,
    required this.language,
    required this.createdAt,
    this.isTrending = false,
  });

  factory Article.fromJson(Map<String, dynamic> json) {
    return Article(
      id: json['id']?.toString() ?? '',
      title: json['title'] ?? '',
      content: json['content'] ?? '',
      author: json['author'] ?? 'Shorts Editor',
      imageUrl: json['image_url'] ?? 'https://images.unsplash.com/photo-1504711434969-e33886168f5c',
      sourceName: json['source_name'] ?? 'Unknown Source',
      sourceUrl: json['source_url'] ?? '',
      category: json['category'] ?? 'all',
      language: json['language'] ?? 'en',
      createdAt: json['created_at'] != null 
          ? DateTime.parse(json['created_at']) 
          : DateTime.now(),
      isTrending: json['is_trending'] ?? false,
    );
  }
}
