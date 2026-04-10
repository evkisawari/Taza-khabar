import 'package:flutter/material.dart';
import 'package:webview_flutter/webview_flutter.dart';
import '../models/article.dart';
import './news_card.dart';

class SwipeableNewsCard extends StatefulWidget {
  final Article article;

  const SwipeableNewsCard({super.key, required this.article});

  @override
  State<SwipeableNewsCard> createState() => _SwipeableNewsCardState();
}

class _SwipeableNewsCardState extends State<SwipeableNewsCard> {
  final PageController _horizontalController = PageController();
  late WebViewController _webController;
  bool _isWebViewLoaded = false;
  bool _hasStartedLoading = false; // Performance: Track if load has happened

  @override
  void initState() {
    super.initState();
    _webController = WebViewController()
      ..setJavaScriptMode(JavaScriptMode.unrestricted)
      ..setBackgroundColor(Colors.black)
      ..setNavigationDelegate(
        NavigationDelegate(
          onPageFinished: (String url) {
            if (mounted) setState(() => _isWebViewLoaded = true);
          },
        ),
      );

    // Listen to horizontal swipe to lazy-load the WebView
    _horizontalController.addListener(() {
      if (_horizontalController.page! > 0.1 && !_hasStartedLoading) {
        setState(() => _hasStartedLoading = true);
        _webController.loadRequest(Uri.parse(widget.article.sourceUrl));
      }
    });
  }

  @override
  void dispose() {
    _horizontalController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return PageView(
      controller: _horizontalController,
      scrollDirection: Axis.horizontal,
      physics: const BouncingScrollPhysics(),
      children: [
        // Page 0: The News Card (Always rendered)
        NewsCard(article: widget.article),
        
        // Page 1: The Internal Browser (Lazy loaded)
        Scaffold(
          backgroundColor: Colors.black,
          appBar: AppBar(
            backgroundColor: const Color(0xFF121212),
            title: Text(
              widget.article.sourceName,
              style: const TextStyle(fontSize: 13, color: Colors.white70),
            ),
            centerTitle: true,
            leading: IconButton(
              icon: const Icon(Icons.close, color: Colors.white, size: 20),
              onPressed: () => _horizontalController.animateToPage(0, duration: const Duration(milliseconds: 300), curve: Curves.ease),
            ),
            elevation: 0,
            bottom: PreferredSize(
              preferredSize: const Size.fromHeight(1.0),
              child: (_hasStartedLoading && !_isWebViewLoaded)
                ? const LinearProgressIndicator(minHeight: 2, color: Colors.redAccent, backgroundColor: Colors.black) 
                : const Divider(height: 1, color: Colors.white10),
            ),
          ),
          body: _hasStartedLoading 
            ? WebViewWidget(controller: _webController)
            : const Center(child: CircularProgressIndicator(color: Colors.redAccent, strokeWidth: 2)),
        ),
      ],
    );
  }
}
