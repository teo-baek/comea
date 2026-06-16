import 'package:flutter/material.dart';

class DetailScreen extends StatefulWidget {
  final String postContent;
  final int score;
  final List<Map<String, dynamic>> realComments; // [수정] 서버에서 받아온 진짜 댓글들

  const DetailScreen({
    super.key,
    required this.postContent,
    required this.score,
    required this.realComments,
  });

  @override
  State<DetailScreen> createState() => _DetailScreenState();
}

class _DetailScreenState extends State<DetailScreen> {
  final List<Map<String, dynamic>> _visibleComments = [];
  bool _isAiTyping = false;
  String _currentTypingAi = "";

  @override
  void initState() {
    super.initState();
    // 화면이 켜지면 서버에서 받아온 실제 AI 댓글들로 순차적 등장 연출 가동
    _simulateAiDispute();
  }

  void _simulateAiDispute() async {
    // 서버가 준 댓글 개수만큼만 루프 돌기 (점수가 낮으면 알아서 0개 혹은 적은 개수가 됨)
    for (int i = 0; i < widget.realComments.length; i++) {
      await Future.delayed(const Duration(milliseconds: 800)); // 생각 시간
      
      if (!mounted) return;
      setState(() {
        _isAiTyping = true;
        _currentTypingAi = widget.realComments[i]["name"] as String;
      });

      await Future.delayed(const Duration(milliseconds: 1500)); // 키보드 두드리는 시간

      if (!mounted) return;
      setState(() {
        _visibleComments.add(widget.realComments[i]);
        _isAiTyping = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final isHot = widget.score >= 90;

    return Scaffold(
      appBar: AppBar(
        title: Text(isHot ? '🚨 실시간 끝장 토론' : '💬 대화 광장'),
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
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text('채점 점수: ${widget.score}점', style: TextStyle(fontWeight: FontWeight.bold, color: isHot ? Colors.red : Colors.blue)),
                    Text('참여 완료: ${_visibleComments.length}/${widget.realComments.length}명', style: const TextStyle(color: Colors.grey)),
                  ],
                ),
              ],
            ),
          ),
          const Divider(height: 1),

          Expanded(
            child: _visibleComments.isEmpty && !_isAiTyping
                ? const Center(child: Text('이 글에는 AI 시민들이 조용히 침묵을 지키고 있습니다.', style: TextStyle(color: Colors.grey)))
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
                  Text('⚡ $_currentTypingAi이(가) 키보드 배틀 참여를 준비 중입니다...', style: const TextStyle(color: Colors.deepPurple, fontWeight: FontWeight.w500)),
                ],
              ),
            ),
        ],
      ),
    );
  }
}