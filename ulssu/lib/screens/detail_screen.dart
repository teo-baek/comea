import 'package:flutter/material.dart';

import '../services/api.dart';

class DetailScreen extends StatefulWidget {
  final int postId;
  final String postContent;
  final int score;
  final List<Map<String, dynamic>> realComments; // 서버에서 받아온 초기 댓글들
  final ApiService api;

  DetailScreen({
    super.key,
    required this.postId,
    required this.postContent,
    required this.score,
    required this.realComments,
    ApiService? api,
  }) : api = api ?? ApiService();

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  late List<Map<String, dynamic>> _allComments; // 지금까지 알려진 전체 댓글
  final List<Map<String, dynamic>> _visibleComments = []; // 등장 완료된 댓글
  bool _isAiTyping = false;
  String _currentTypingAi = "";
  bool _isReacting = false;

  @override
  void initState() {
    super.initState();
    _allComments = List<Map<String, dynamic>>.from(widget.realComments);
    _revealNewComments();
  }

  // 아직 등장하지 않은(_visibleComments 이후) 댓글만 순차적으로 등장시킨다.
  Future<void> _revealNewComments() async {
    for (int i = _visibleComments.length; i < _allComments.length; i++) {
      await Future.delayed(const Duration(milliseconds: 800));
      if (!mounted) return;
      setState(() {
        _isAiTyping = true;
        _currentTypingAi = _allComments[i]["name"] as String;
      });

      await Future.delayed(const Duration(milliseconds: 1500));
      if (!mounted) return;
      setState(() {
        _visibleComments.add(_allComments[i]);
        _isAiTyping = false;
      });
    }
  }

  // 좋아요/싫어요 반응 → 갱신된 댓글로 교체 → 늘어난 만큼만 이어서 등장.
  Future<void> _react(String reaction) async {
    if (_isReacting) return; // 처리 중 연타 차단 (FR-7)
    setState(() => _isReacting = true);
    try {
      final post = await widget.api.reactToPost(widget.postId, reaction);
      _allComments = List<Map<String, dynamic>>.from(post["comments"]);
      await _revealNewComments();
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('반응을 전송하지 못했습니다.'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } finally {
      if (mounted) setState(() => _isReacting = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final isHot = widget.score >= 90;

    return Scaffold(
      appBar: AppBar(
        title: Text(isHot ? '🔥 인기 글' : '💬 글'),
        backgroundColor: isHot ? Colors.red.shade50 : Colors.blue.shade50,
      ),
      body: Column(
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(20),
            color: isHot ? Colors.red.shade50 : Colors.blue.shade50,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(widget.postContent, style: const TextStyle(fontSize: 16, fontWeight: FontWeight.w600, height: 1.4)),
                const SizedBox(height: 12),
                Text('AI 시민 ${_visibleComments.length}명이 댓글을 남겼어요', style: const TextStyle(color: Colors.grey)),
              ],
            ),
          ),
          const Divider(height: 1),

          // 반응 버튼 줄 (수치 비노출 — 개수 표시 없음, FR-3)
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
            child: Row(
              children: [
                TextButton.icon(
                  key: const Key('like-button'),
                  onPressed: _isReacting ? null : () => _react('like'),
                  icon: const Icon(Icons.thumb_up_alt_outlined),
                  label: const Text('좋아요'),
                ),
                const SizedBox(width: 8),
                TextButton.icon(
                  key: const Key('dislike-button'),
                  onPressed: _isReacting ? null : () => _react('dislike'),
                  icon: const Icon(Icons.thumb_down_alt_outlined),
                  label: const Text('싫어요'),
                ),
                const Spacer(),
                if (_isReacting)
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.deepPurple),
                  ),
              ],
            ),
          ),
          const Divider(height: 1),

          Expanded(
            child: _visibleComments.isEmpty && !_isAiTyping
                ? const Center(child: Text('아직 댓글이 없어요. 잠시 후 AI 시민들이 댓글을 남깁니다.', style: TextStyle(color: Colors.grey)))
                : ListView.builder(
                    itemCount: _visibleComments.length,
                    itemBuilder: (context, index) {
                      final comment = _visibleComments[index];
                      return Padding(
                        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            CircleAvatar(
                              backgroundColor: Colors.deepPurple.shade100,
                              child: Text((comment["name"] as String)[0]),
                            ),
                            const SizedBox(width: 12),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(comment["name"] as String, style: const TextStyle(fontWeight: FontWeight.bold)),
                                  const SizedBox(height: 4),
                                  Container(
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(color: Colors.grey.shade100, borderRadius: BorderRadius.circular(12)),
                                    child: Text(comment["comment"] as String, style: const TextStyle(fontSize: 14, height: 1.3)),
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      );
                    },
                  ),
          ),

          if (_isAiTyping)
            Container(
              padding: const EdgeInsets.all(12),
              color: Colors.grey.shade50,
              child: Row(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2, color: Colors.deepPurple),
                  ),
                  const SizedBox(width: 12),
                  Text('$_currentTypingAi 님이 댓글을 작성 중...', style: const TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.w500)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}
