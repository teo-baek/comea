import 'package:flutter/material.dart';
import 'screens/home_screen.dart'; // 방금 만든 홈 화면 임포트

void main() {
  runApp(const AiSquareApp());
}

class AiSquareApp extends StatelessWidget {
  const AiSquareApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: 'AI Square',
      theme: ThemeData(
        // 트렌디하고 깨끗한 Material 3 가이드라인 적용
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.deepPurple,
          brightness: Brightness.light,
        ),
      ),
      // 앱이 켜졌을 때 첫 화면을 게시판(HomeScreen)으로 설정
      home: const HomeScreen(),
      debugShowCheckedModeBanner: false, // 우상단 디버그 띠 숨기기
    );
  }
}