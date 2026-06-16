import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'detail_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  List<Map<String, dynamic>> _posts = [];
  final TextEditingController _textController = TextEditingController();
  bool _isLoading = false;

  @override
  void initState() {
    super.initState();
    // 📌 앱이 켜지자마자 데이터베이스에 저장된 모든 글을 긁어옴
    _fetchPostsFromDatabase();
  }

  // 📌 1. [NEW] 백엔드 PostgreSQL DB에서 과거 글 목록을 조회해오는 함수 (GET)
  Future<void> _fetchPostsFromDatabase() async {
    setState(() {
      _isLoading = true;
    });

    try {
      final url = Uri.parse('http://172.28.0.1:8000/api/posts');
      final response = await http.get(url);

      if (response.statusCode == 200) {
        final List<dynamic> decodedData = jsonDecode(utf8.decode(response.bodyBytes));
        setState(() {
          _posts = List<Map<String, dynamic>>.from(decodedData);
        });
      } else {
        _showErrorSnackBar("데이터를 불러오는 중 오류가 발생했습니다.");
      }
    } catch (e) {
      _showErrorSnackBar("백엔드 서버와 통신할 수 없습니다.");
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  // 📌 2. 새로운 고민을 등록하고 결과를 DB에 저장하는 함수 (POST)
  Future<void> _submitPostToServer(String content) async {
    setState(() {
      _isLoading = true;
    });

    try {
      final url = Uri.parse('http://172.28.0.1:8000/api/posts');
      final response = await http.post(
        url,
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({"content": content}),
      );

      if (response.statusCode == 200) {
        final dynamic decodedData = jsonDecode(utf8.decode(response.bodyBytes));
        
        setState(() {
          // 서버가 반환한 영구 저장된 객체를 리스트 맨 앞에 즉시 주입
          _posts.insert(0, {
            "content": decodedData["content"],
            "score": decodedData["score"],
            "comments": List<Map<String, dynamic>>.from(decodedData["comments"]),
          });
        });
      } else {
        _showErrorSnackBar("서버 응답 오류가 발생했습니다.");
      }
    } catch (e) {
      _showErrorSnackBar("서버와 통신할 수 없습니다.");
    } finally {
      setState(() {
        _isLoading = false;
      });
    }
  }

  void _showErrorSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(message), backgroundColor: Colors.red),
    );
  }

  void _showWriteDialog() {
    showDialog(
      context: context,
      barrierDismissible: !_isLoading,
      builder: (context) => AlertDialog(
        title: const Text('📝 새로운 고민 던지기'),
        content: TextField(
          controller: _textController,
          maxLines: 4,
          decoration: const InputDecoration(
            hintText: 'AI 시민들을 흔들어놓을 고민을 입력하세요...',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('취소'),
          ),
          ElevatedButton(
            onPressed: () async {
              final text = _textController.text.trim();
              if (text.isNotEmpty) {
                Navigator.pop(context);
                await _submitPostToServer(text);
                _textController.clear();
              }
            },
            child: const Text('등록'),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🤖 AI 광장 (ulssu)', style: TextStyle(fontWeight: FontWeight.bold)),
        centerTitle: true,
        actions: [
          // 새로고침 버튼 추가
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _isLoading ? null : _fetchPostsFromDatabase,
          )
        ],
      ),
      body: Stack(
        children: [
          _posts.isEmpty && !_isLoading
              ? const Center(child: Text('광장이 비어 있습니다.\n첫 번째 고민을 던져보세요!', textAlign: TextAlign.center, style: TextStyle(color: Colors.grey, fontSize: 16)))
              : ListView.builder(
                  itemCount: _posts.length,
                  itemBuilder: (context, index) {
                    final post = _posts[index];
                    return Card(
                      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                      child: ListTile(
                        title: Text(post["content"] as String, maxLines: 2, overflow: TextOverflow.ellipsis),
                        trailing: Chip(
                          label: Text('${post["score"]}점'),
                          backgroundColor: (post["score"] as int) >= 90 ? Colors.red.shade100 : Colors.blue.shade100,
                        ),
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (context) => DetailScreen(
                                postContent: post["content"] as String,
                                score: post["score"] as int,
                                realComments: List<Map<String, dynamic>>.from(post["comments"]),
                              ),
                            ),
                          );
                        },
                      ),
                    );
                  },
                ),
          if (_isLoading)
            Container(
              color: Colors.black12,
              child: const Center(child: CircularProgressIndicator(color: Colors.deepPurple)),
            ),
        ],
      ),
      floatingActionButton: FloatingActionButton(
        onPressed: _isLoading ? null : _showWriteDialog,
        child: const Icon(Icons.edit),
      ),
    );
  }
}