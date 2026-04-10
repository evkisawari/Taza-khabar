import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import '../providers/news_provider.dart';
import '../widgets/swipeable_news_card.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  final PageController _pageController = PageController();

  @override
  void initState() {
    super.initState();
    Future.microtask(() {
      final provider = Provider.of<NewsProvider>(context, listen: false);
      provider.fetchCategories();
      provider.fetchNews();
    });

    _pageController.addListener(() {
      if (_pageController.position.pixels >= _pageController.position.maxScrollExtent - 200) {
        Provider.of<NewsProvider>(context, listen: false).fetchNews();
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        elevation: 0,
        centerTitle: true,
        leading: IconButton(
          icon: const Icon(Icons.menu, color: Colors.white, size: 22),
          onPressed: () => _showCategoryPicker(context),
        ),
        title: Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.refresh, color: Colors.white24, size: 16),
            const SizedBox(width: 8),
            Text(
              'My Feed',
              style: GoogleFonts.roboto(
                color: Colors.white,
                fontSize: 14,
                fontWeight: FontWeight.w600,
                letterSpacing: 0.5,
              ),
            ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.share_outlined, color: Colors.white54, size: 20),
            onPressed: () {},
          ),
        ],
      ),
      body: Consumer<NewsProvider>(
        builder: (context, provider, child) {
          return Stack(
            children: [
              // Main Feed
              if (provider.news.isEmpty && provider.isLoading)
                const Center(child: CircularProgressIndicator(color: Colors.redAccent, strokeWidth: 2))
              else if (provider.news.isEmpty)
                const Center(child: Text('No news found', style: TextStyle(color: Colors.white38)))
              else
                RefreshIndicator(
                  onRefresh: () async {
                    await provider.fetchNews(reset: true);
                  },
                  backgroundColor: const Color(0xFF1E1E1E),
                  color: Colors.redAccent,
                  child: PageView.builder(
                    controller: _pageController,
                    scrollDirection: Axis.vertical,
                    itemCount: provider.news.length,
                    physics: const AlwaysScrollableScrollPhysics(
                      parent: BouncingScrollPhysics(),
                    ),
                    itemBuilder: (context, index) {
                      return AnimatedBuilder(
                        animation: _pageController,
                        builder: (context, child) {
                          double value = 1.0;
                          if (_pageController.position.haveDimensions) {
                            value = (_pageController.page ?? 0) - index;
                            value = (1 - (value.abs() * 0.25)).clamp(0.0, 1.0);
                          }
                          return Center(
                            child: Transform.scale(
                              scale: value,
                              child: Opacity(
                                opacity: value,
                                child: SwipeableNewsCard(article: provider.news[index]),
                              ),
                            ),
                          );
                        },
                      );
                    },
                  ),
                ),

              // 100% Copy: First Install Language Selection Overlay
              if (provider.isFirstRun)
                Container(
                  color: Colors.black.withOpacity(0.95),
                  child: Center(
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.language, color: Colors.redAccent, size: 60),
                        const SizedBox(height: 24),
                        Text(
                          'Choose Your Language',
                          style: GoogleFonts.roboto(color: Colors.white, fontSize: 24, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 8),
                        Text(
                          'समाचार की भाषा चुनें',
                          style: GoogleFonts.roboto(color: Colors.white54, fontSize: 16),
                        ),
                        const SizedBox(height: 48),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.center,
                          children: [
                            _languageCard(context, provider, 'English', 'en'),
                            const SizedBox(width: 20),
                            _languageCard(context, provider, 'हिंदी', 'hi'),
                          ],
                        ),
                      ],
                    ),
                  ),
                ),
            ],
          );
        },
      ),
    );
  }

  Widget _languageCard(BuildContext context, NewsProvider provider, String title, String code) {
    return GestureDetector(
      onTap: () => provider.setLanguage(code),
      child: Container(
        width: 140,
        height: 100,
        decoration: BoxDecoration(
          color: const Color(0xFF1E1E1E),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.white10),
        ),
        child: Center(
          child: Text(
            title,
            style: GoogleFonts.roboto(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
          ),
        ),
      ),
    );
  }

  void _showCategoryPicker(BuildContext context) {
    final provider = Provider.of<NewsProvider>(context, listen: false);
    final categories = provider.categories.map((c) => {'id': c, 'name': c == 'all' ? 'All News' : c}).toList();

    showModalBottomSheet(
      context: context,
      backgroundColor: const Color(0xFF121212),
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (context) {
        return Container(
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Container(
                width: 40,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.white12,
                  borderRadius: BorderRadius.circular(10),
                ),
              ),
              const SizedBox(height: 20),
              Text(
                'CATEGORIES',
                style: GoogleFonts.roboto(
                  color: Colors.white38,
                  fontSize: 11,
                  fontWeight: FontWeight.w900,
                  letterSpacing: 2,
                ),
              ),
              const SizedBox(height: 24),
              Flexible(
                child: GridView.builder(
                  shrinkWrap: true,
                  physics: const BouncingScrollPhysics(),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 3,
                    crossAxisSpacing: 10,
                    mainAxisSpacing: 10,
                    childAspectRatio: 2.2,
                  ),
                  itemCount: categories.length,
                  itemBuilder: (context, index) {
                    final cat = categories[index];
                    final isActive = provider.activeCategory == cat['id'];
                    
                    return GestureDetector(
                      onTap: () {
                        provider.setCategory(cat['id']!);
                        Navigator.pop(context);
                      },
                      child: Container(
                        decoration: BoxDecoration(
                          color: isActive ? Colors.redAccent.withOpacity(0.1) : Colors.white.withOpacity(0.03),
                          borderRadius: BorderRadius.circular(4),
                          border: Border.all(
                            color: isActive ? Colors.redAccent.withOpacity(0.5) : Colors.white10,
                          ),
                        ),
                        alignment: Alignment.center,
                        child: Text(
                          cat['name']!.toUpperCase(),
                          style: TextStyle(
                            color: isActive ? Colors.redAccent : Colors.white70,
                            fontSize: 10,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                      ),
                    );
                  },
                ),
              ),
              const SizedBox(height: 20),
              const Divider(color: Colors.white10),
              const SizedBox(height: 10),
              
              // Language Switcher Section
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    'LANGUAGE',
                    style: GoogleFonts.roboto(
                      color: Colors.white38,
                      fontSize: 11,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 2,
                    ),
                  ),
                  Row(
                    children: [
                      _langChip(context, provider, 'EN', 'en'),
                      const SizedBox(width: 8),
                      _langChip(context, provider, 'हि', 'hi'),
                    ],
                  ),
                ],
              ),
              const SizedBox(height: 20),
              
              // Sync Action
              ListTile(
                leading: const Icon(Icons.sync, color: Colors.white54),
                title: const Text('Refresh Content', style: TextStyle(color: Colors.white70, fontSize: 13)),
                onTap: () {
                  provider.triggerSync();
                  Navigator.pop(context);
                },
              ),
            ],
          ),
        );
      },
    );
  }

  Widget _langChip(BuildContext context, NewsProvider provider, String label, String code) {
    final bool isActive = provider.language == code;
    return GestureDetector(
      onTap: () {
        provider.setLanguage(code);
        Navigator.pop(context); // Close menu after change
      },
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 6),
        decoration: BoxDecoration(
          color: isActive ? Colors.redAccent : Colors.white10,
          borderRadius: BorderRadius.circular(20),
        ),
        child: Text(
          label,
          style: TextStyle(
            color: isActive ? Colors.white : Colors.white54,
            fontSize: 12,
            fontWeight: FontWeight.bold,
          ),
        ),
      ),
    );
  }
}
