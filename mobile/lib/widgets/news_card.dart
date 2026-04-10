import 'package:flutter/material.dart';
import 'package:cached_network_image/cached_network_image.dart';
import 'package:google_fonts/google_fonts.dart';
import 'package:intl/intl.dart';
import '../models/article.dart';

class NewsCard extends StatelessWidget {
  final Article article;

  const NewsCard({super.key, required this.article});

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;
    final bool isHindi = article.language == 'hi';
    final textStyle = isHindi ? GoogleFonts.notoSansDevanagari : GoogleFonts.roboto;

    return Container(
      color: Colors.black,
      child: Column(
        children: [
          Expanded(
            child: Container(
              color: const Color(0xFF121212),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Stack(
                    children: [
                      CachedNetworkImage(
                        imageUrl: article.imageUrl,
                        width: double.infinity,
                        height: size.height * 0.40, 
                        fit: BoxFit.cover,
                        placeholder: (context, url) => Container(
                          color: const Color(0xFF1A1A1A),
                          child: const Center(child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white24)),
                        ),
                      ),
                      Positioned(
                        top: 20,
                        left: 0,
                        child: Container(
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                          decoration: const BoxDecoration(
                            color: Colors.black54,
                            borderRadius: BorderRadius.only(
                              topRight: Radius.circular(4),
                              bottomRight: Radius.circular(4),
                            ),
                          ),
                          child: Text(
                            article.sourceName.toUpperCase(),
                            style: textStyle(
                              color: Colors.white,
                              fontSize: 10,
                              fontWeight: FontWeight.w900,
                              letterSpacing: 1.5,
                            ),
                          ),
                        ),
                      ),
                    ],
                  ),
                  Expanded(
                    child: SingleChildScrollView(
                      physics: const BouncingScrollPhysics(),
                      padding: const EdgeInsets.fromLTRB(20, 15, 20, 10),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            article.title,
                            style: textStyle(
                              color: Colors.white.withOpacity(0.95),
                              fontSize: isHindi ? 21 : 19,
                              fontWeight: FontWeight.w700,
                              height: 1.3,
                            ),
                          ),
                          const SizedBox(height: 12),
                          Text(
                            article.content,
                            style: textStyle(
                              color: const Color(0xFFBDBDBD),
                              fontSize: isHindi ? 16 : 15,
                              fontWeight: FontWeight.w400,
                              height: 1.6,
                            ),
                          ),
                          const SizedBox(height: 15),
                          Text(
                            'short by ${article.author} / ${_getTimeAgo(article.createdAt, isHindi)}',
                            style: textStyle(
                              color: Colors.white24,
                              fontSize: 11,
                              fontWeight: FontWeight.w500,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(vertical: 14, horizontal: 20),
            decoration: const BoxDecoration(
              color: Color(0xFF212121),
              border: Border(top: BorderSide(color: Colors.white10, width: 0.5)),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Text(
                    isHindi 
                      ? 'पूरे समाचार के लिए बाएं स्वाइप करें - ${article.sourceName}'
                      : 'Swipe left for more details at ${article.sourceName}',
                    style: textStyle(
                      color: Colors.white54,
                      fontSize: 10,
                    ),
                    overflow: TextOverflow.ellipsis,
                  ),
                ),
                const Icon(Icons.arrow_forward_ios, color: Colors.white24, size: 10),
              ],
            ),
          ),
        ],
      ),
    );
  }

  String _getTimeAgo(DateTime dateTime, bool isHindi) {
    Duration diff = DateTime.now().difference(dateTime);
    if (diff.inDays >= 1) {
      if (isHindi) {
        return '${diff.inDays} दिन पहले';
      }
      return '${diff.inDays}d ago';
    } else if (diff.inHours >= 1) {
      if (isHindi) {
        return '${diff.inHours} घंटे पहले';
      }
      return '${diff.inHours}h ago';
    } else if (diff.inMinutes >= 1) {
      if (isHindi) {
        return '${diff.inMinutes} मिनट पहले';
      }
      return '${diff.inMinutes}m ago';
    } else {
      if (isHindi) {
        return 'अभी-अभी';
      }
      return 'just now';
    }
  }
}
