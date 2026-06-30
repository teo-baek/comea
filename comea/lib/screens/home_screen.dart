import 'package:flutter/material.dart';
import 'detail_screen.dart';
import '../services/api.dart';

class HomeScreen extends StatefulWidget {
  final ApiService api;
  final VoidCallback? onLogout;

  HomeScreen({super.key, ApiService? api, this.onLogout}) : api = api ?? ApiService();

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  ApiService get _api => widget.api;
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
      final posts = await _api.getPosts();
      setState(() {
        _posts = posts;
      });
    } catch (e) {
      _showErrorSnackBar("데이터를 불러오는 중 오류가 발생했습니다.");
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
      final post = await _api.createPost(content);
      setState(() {
        // 서버가 반환한 영구 저장된 객체를 리스트 맨 앞에 즉시 주입 (id 포함 — 반응 호출에 필요)
        _posts.insert(0, {
          "id": post["id"],
          "content": post["content"],
          "score": post["score"],
          "is_locked": post["is_locked"],
          "comments": List<Map<String, dynamic>>.from(post["comments"]),
        });
      });
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
        title: const Text('🤖 AI 광장 (comea)', style: TextStyle(fontWeight: FontWeight.bold)),
        centerTitle: true,
        actions: [
          // 새로고침 버튼 추가
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _isLoading ? null : _fetchPostsFromDatabase,
          ),
          if (widget.onLogout != null)
            IconButton(
              icon: const Icon(Icons.logout),
              onPressed: widget.onLogout,
            ),
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
                                postId: post["id"] as int,
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