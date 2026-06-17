import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/home_screen.dart';
import 'screens/login_screen.dart';
import 'services/api.dart';

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
        useMaterial3: true,
        colorScheme: ColorScheme.fromSeed(
          seedColor: Colors.deepPurple,
          brightness: Brightness.light,
        ),
      ),
      home: const AuthGate(),
      debugShowCheckedModeBanner: false,
    );
  }
}

/// 토큰 유무로 로그인/홈을 분기하고, 토큰을 SharedPreferences에 영속화한다.
class AuthGate extends StatefulWidget {
  const AuthGate({super.key});

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  final ApiService _api = ApiService();
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _restore();
  }

  Future<void> _restore() async {
    final prefs = await SharedPreferences.getInstance();
    _api.token = prefs.getString('token');
    if (mounted) setState(() => _loading = false);
  }

  Future<void> _onAuthed() async {
    final prefs = await SharedPreferences.getInstance();
    if (_api.token != null) await prefs.setString('token', _api.token!);
    if (mounted) setState(() {});
  }

  Future<void> _onLogout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('token');
    _api.logout();
    if (mounted) setState(() {});
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) {
      return const Scaffold(body: Center(child: CircularProgressIndicator()));
    }
    if (_api.token == null) {
      return LoginScreen(api: _api, onAuthed: _onAuthed);
    }
    return HomeScreen(api: _api, onLogout: _onLogout);
  }
}