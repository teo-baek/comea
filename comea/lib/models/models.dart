/// Comea API 응답 모델 — docs/stage2-backend-spec.md §8 과 1:1.
library;

class ScoreBreakdown {
  const ScoreBreakdown({
    required this.emotion,
    required this.controversy,
    required this.clarity,
    required this.novelty,
  });

  final int emotion; // 정서적 깊이 1~5
  final int controversy; // 논쟁 유발성 1~5
  final int clarity; // 주제 명확성 1~5
  final int novelty; // 신규성 1~5

  factory ScoreBreakdown.fromJson(Map<String, dynamic> json) => ScoreBreakdown(
        emotion: (json['emotion'] as num?)?.toInt() ?? 3,
        controversy: (json['controversy'] as num?)?.toInt() ?? 3,
        clarity: (json['clarity'] as num?)?.toInt() ?? 3,
        novelty: (json['novelty'] as num?)?.toInt() ?? 3,
      );
}

class CommentItem {
  const CommentItem({
    required this.id,
    required this.faction,
    required this.personaName,
    required this.content,
    required this.turnIndex,
    required this.likes,
    required this.dislikes,
    this.myReaction,
    this.createdAt,
  });

  final int id;
  final String faction; // "ally" | "challenger" | "moderator"
  final String personaName;
  final String content;
  final int turnIndex;
  final int likes;
  final int dislikes;
  final String? myReaction; // "like" | "dislike" | null
  final DateTime? createdAt;

  factory CommentItem.fromJson(Map<String, dynamic> json) => CommentItem(
        id: (json['id'] as num).toInt(),
        faction: json['faction'] as String? ?? 'ally',
        personaName: json['persona_name'] as String? ?? 'AI 논객',
        content: json['content'] as String? ?? '',
        turnIndex: (json['turn_index'] as num?)?.toInt() ?? 0,
        likes: (json['likes'] as num?)?.toInt() ?? 0,
        dislikes: (json['dislikes'] as num?)?.toInt() ?? 0,
        myReaction: json['my_reaction'] as String?,
        createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
      );
}

class Post {
  const Post({
    required this.id,
    required this.content,
    required this.status,
    required this.likes,
    required this.dislikes,
    required this.netReaction,
    required this.commentCount,
    this.score,
    this.baseLimit,
    this.finalLimit,
    this.verdict,
    this.createdAt,
    this.authorName,
    this.isMine = false,
    this.myReaction,
    this.scoreBreakdown,
    this.coreClaim,
    this.comments = const [],
  });

  final int id;
  final String content;
  final String status; // "grading" | "debating" | "concluded"
  final int likes;
  final int dislikes;
  final int netReaction;
  final int commentCount;
  final int? score;
  final int? baseLimit;
  final int? finalLimit;
  final String? verdict; // "ally" | "challenger" | "tie" | null
  final DateTime? createdAt;
  final String? authorName;
  final bool isMine;
  final String? myReaction;
  final ScoreBreakdown? scoreBreakdown;
  final String? coreClaim;
  final List<CommentItem> comments;

  factory Post.fromJson(Map<String, dynamic> json) => Post(
        id: (json['id'] as num).toInt(),
        content: json['content'] as String? ?? '',
        status: json['status'] as String? ?? 'grading',
        likes: (json['likes'] as num?)?.toInt() ?? 0,
        dislikes: (json['dislikes'] as num?)?.toInt() ?? 0,
        netReaction: (json['net_reaction'] as num?)?.toInt() ?? 0,
        commentCount: (json['comment_count'] as num?)?.toInt() ?? 0,
        score: (json['score'] as num?)?.toInt(),
        baseLimit: (json['base_limit'] as num?)?.toInt(),
        finalLimit: (json['final_limit'] as num?)?.toInt(),
        verdict: json['verdict'] as String?,
        createdAt: DateTime.tryParse(json['created_at'] as String? ?? ''),
        authorName: json['author_name'] as String?,
        isMine: json['is_mine'] as bool? ?? false,
        myReaction: json['my_reaction'] as String?,
        scoreBreakdown: json['score_breakdown'] is Map<String, dynamic>
            ? ScoreBreakdown.fromJson(json['score_breakdown'] as Map<String, dynamic>)
            : null,
        coreClaim: json['core_claim'] as String?,
        comments: (json['comments'] as List<dynamic>? ?? [])
            .whereType<Map<String, dynamic>>()
            .map(CommentItem.fromJson)
            .toList(),
      );

  /// 토론이 아직 흘러가는 중인가 (폴링 필요 여부)
  bool get isLive => status == 'grading' || status == 'debating';
}
