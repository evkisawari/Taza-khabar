import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:google_fonts/google_fonts.dart';
import './providers/news_provider.dart';
import './screens/home_screen.dart';

void main() {
  runApp(const NewsLensApp());
}

class NewsLensApp extends StatelessWidget {
  const NewsLensApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => NewsProvider()),
      ],
      child: MaterialApp(
        title: 'NewsLens',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          brightness: Brightness.dark,
          primaryColor: const Color(0xFF6366F1),
          scaffoldBackgroundColor: Colors.black,
          textTheme: GoogleFonts.interTextTheme(
            Theme.of(context).textTheme,
          ).apply(
            bodyColor: Colors.white,
            displayColor: Colors.white,
          ),
          colorScheme: const ColorScheme.dark(
            primary: Color(0xFF6366F1),
            secondary: Color(0xFF818CF8),
            surface: Color(0xFF0F0F12),
          ),
        ),
        home: const HomeScreen(),
      ),
    );
  }
}
