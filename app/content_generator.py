"""YouTubeタイトル・説明文生成モジュール"""
import json
import re
from typing import Optional, Dict

import google.generativeai as genai

from app.config import config
from app.logging_utils import log_info, log_warning, log_error


def _extract_json_from_content(content: str) -> Dict:
    """
    Geminiレスポンスから堅牢にJSONを抽出してパース

    Args:
        content: Geminiレスポンステキスト

    Returns:
        パースされたJSONオブジェクト

    Raises:
        json.JSONDecodeError: JSON抽出・パースに失敗した場合
        ValueError: 有効なJSONが見つからない場合
    """
    original_content = content

    # 1. マークダウンコードブロックを除去
    if "```json" in content:
        parts = content.split("```json")
        if len(parts) > 1:
            content = parts[1].split("```")[0].strip()
    elif "```" in content:
        parts = content.split("```")
        if len(parts) > 1:
            content = parts[1].split("```")[0].strip()

    # 2. JSONオブジェクトを正規表現で抽出
    # まず完全なオブジェクトを探す
    complete_obj_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', content, re.DOTALL)
    if complete_obj_match:
        content = complete_obj_match.group()
    else:
        # 不完全なオブジェクトも探す
        incomplete_obj_match = re.search(r'\{.*', content, re.DOTALL)
        if incomplete_obj_match:
            content = incomplete_obj_match.group()
            # オブジェクトを強制的に閉じる
            if not content.rstrip().endswith('}'):
                content = content.rstrip().rstrip(',') + '}'
        else:
            raise ValueError(f"No JSON object found in response. Content: {original_content[:200]}")

    # 3. よくある問題を修正
    # - 末尾のカンマを削除
    content = re.sub(r',\s*}', '}', content)
    content = re.sub(r',\s*\]', ']', content)
    # - 不完全な文字列を閉じる (例: "title": "裏方で金持ちは無理} -> "title": "裏方で金持ちは無理"})
    content = re.sub(r':\s*"([^"]*?)([}\]])' , r': "\1"\2', content)
    # - 不完全なキー:値のペアを修正（値がない場合）
    content = re.sub(r':\s*([,}])', r': ""\1', content)

    try:
        parsed = json.loads(content)
        log_info(f"Successfully parsed JSON: {list(parsed.keys())}")
        return parsed
    except json.JSONDecodeError as e:
        # デバッグ用に問題箇所を表示
        error_line = content.split('\n')[e.lineno - 1] if e.lineno <= len(content.split('\n')) else ""
        log_error(
            f"JSON parse failed at line {e.lineno}, col {e.colno}: {e.msg}\n"
            f"Error line: {error_line[:100]}\n"
            f"Full JSON content:\n{content}"
        )
        raise


def generate_title_and_description(
    transcript_text: str,
    source_url: Optional[str] = None,
    fallback_title: str = "ショート動画"
) -> Dict[str, str]:
    """
    Gemini APIを使ってタイトルと説明文を生成

    Args:
        transcript_text: セグメントの文字起こしテキスト
        source_url: 元動画のURL（オプション）
        fallback_title: APIが使えない場合のフォールバックタイトル

    Returns:
        {"title": "タイトル", "description": "説明文"}
    """

    # Gemini APIが使える場合はAI生成
    if config.GEMINI_API_KEY:
        try:
            return _generate_with_gemini(transcript_text, source_url, fallback_title)
        except Exception as e:
            log_warning(f"Gemini API failed, using fallback: {e}")

    # フォールバック: ルールベースで生成
    return _generate_fallback(transcript_text, source_url, fallback_title)


def _generate_with_gemini(transcript_text: str, source_url: Optional[str], fallback_title: str) -> Dict[str, str]:
    """Gemini APIでタイトルと説明文を生成"""

    log_info("Generating title and description with Gemini API")

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL)

    # プロンプト作成（タイトル20文字以内・ポイント20文字以内を明示）
    prompt = f"""以下の文字起こしから、YouTube Shorts用のタイトルと説明文を生成してください。

【文字起こし】
{transcript_text[:1000]}

【要件】
- タイトル: 日本語で20文字以内。動画のテーマや問題提起をする短いフック。
  * 例: 「理想のライブハウス」「バンドマンが企業で失敗する理由」「ギターVSベース」
  * 疑問形や対比形式も効果的
  記号の乱用は避け、自然で読みやすい日本語にすること。

- 説明文: 1行目に動画の具体的な内容や気になる答えを20文字以内で書く。タイトルとは異なる内容にすること。
  * タイトルに対する答えや具体的な内容を書く
  * 例: 「店長が◯●を切っている」「エロいから」「それぞれに向いている人間性は？」「裏技【カラオケ編】」
  * 視聴者が「え？どういうこと？」と気になる表現を使う
  * 結論を完全には明かさず、期待を高める
  2行目以降で簡潔な補足とハッシュタグ（#Shorts含む）。

重要: タイトルと説明文の1行目は必ず異なる内容にしてください。上下で動画の内容を紹介する形にしてください。

- JSON形式で回答: {{"title": "タイトル", "description": "説明文"}}

JSON形式のみで回答してください。"""

    safety_settings = [
        {
            "category": "HARM_CATEGORY_HARASSMENT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_HATE_SPEECH",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
            "threshold": "BLOCK_NONE"
        },
        {
            "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
            "threshold": "BLOCK_NONE"
        }
    ]

    response = model.generate_content(
        prompt,
        safety_settings=safety_settings,
        generation_config={
            "temperature": 0.7,
            "max_output_tokens": 500,  # 300から500に増やす
        }
    )

    content = response.text.strip()
    log_info(f"Gemini response: {content[:100]}...")

    # レスポンスが短すぎる場合は詳細をログ出力
    if len(content) < 100:
        log_warning(f"Response too short ({len(content)} chars). Full content: {content}")
        log_warning(f"Response candidates: {response.candidates if hasattr(response, 'candidates') else 'N/A'}")
        if hasattr(response, 'prompt_feedback'):
            log_warning(f"Prompt feedback: {response.prompt_feedback}")

    # トークン使用量とコストを計算
    usage = response.usage_metadata
    input_tokens = usage.prompt_token_count if usage else 0
    output_tokens = usage.candidates_token_count if usage else 0
    total_tokens = input_tokens + output_tokens

    # Gemini 1.5 Flash の料金（2024年10月時点）
    # Input: $0.075 / 1M tokens, Output: $0.30 / 1M tokens
    # 1ドル = 150円と仮定
    INPUT_COST_PER_1M = 0.075 * 150  # 11.25円
    OUTPUT_COST_PER_1M = 0.30 * 150  # 45円

    input_cost_jpy = (input_tokens / 1_000_000) * INPUT_COST_PER_1M
    output_cost_jpy = (output_tokens / 1_000_000) * OUTPUT_COST_PER_1M
    total_cost_jpy = input_cost_jpy + output_cost_jpy

    log_info(f"Token usage: {input_tokens} input + {output_tokens} output = {total_tokens} total")
    log_info(f"Cost: ¥{total_cost_jpy:.4f} (input: ¥{input_cost_jpy:.4f}, output: ¥{output_cost_jpy:.4f})")

    # JSON抽出 - より堅牢な方法を使用
    try:
        result = _extract_json_from_content(content)
        title = result.get("title", "").strip()
        description = result.get("description", "").strip()

        # titleまたはdescriptionが空の場合はフォールバックを使用
        if not title or not description:
            log_warning(f"Incomplete Gemini response (title: {bool(title)}, description: {bool(description)}), using fallback")
            fallback_result = _generate_fallback(transcript_text, source_url, fallback_title)

            # 空のフィールドをフォールバックで補完
            if not title:
                title = fallback_result["title"]
            if not description:
                description = fallback_result["description"]
        else:
            # 元動画URLを追加
            if source_url:
                description += f"\n\n📌 元動画: {source_url}"

            description += "\n\n#Shorts"

        log_info(f"Generated title: {title}")
        return {
            "title": title,
            "description": description,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "total_tokens": total_tokens,
            "cost_jpy": total_cost_jpy
        }
    except Exception as e:
        log_error(f"JSON parsing failed: {e}")
        log_info(f"Full response content: {content}")
        raise ValueError(f"Failed to parse JSON from Gemini response: {e}") from e


def _generate_fallback(
    transcript_text: str,
    source_url: Optional[str],
    fallback_title: str
) -> Dict[str, str]:
    """ルールベースでタイトルと説明文を生成（フォールバック）"""

    log_info("Generating title and description with rule-based fallback")

    # 複数の文を抽出
    sentences = re.split(r"[。？！\?]", transcript_text.strip()) if transcript_text else []
    sentences = [s.strip() for s in sentences if s.strip()]

    def _hookify(text: str, limit: int) -> str:
        t = text.strip()
        if t.endswith("けど"):
            t = t[:-2] + "？"
        if t.endswith("けど、"):
            t = t[:-3] + "？"
        # 2行表示に対応するため、limitを超えても「…」を付けない
        if len(t) > limit:
            t = t[:limit]
        return t or fallback_title

    def _create_teaser_point(text: str, limit: int = 20) -> str:
        """動画のポイントを「●●でいること」のような伏せ字形式で作成"""
        t = text.strip()

        # 「...」や「…」を除去してクリーンアップ
        t_clean = t.replace('...', '').replace('…', '').strip()

        # 文末が「いること」「すること」「なること」などの場合、重要部分を伏せ字に
        patterns = [
            (r'(.+)(でいること|にいること)$', r'●●\2'),  # 「〇〇でいること」→「●●でいること」
            (r'(.+)(ですること|にすること|をすること)$', r'●●\2'),  # 「〇〇すること」→「●●すること」
            (r'(.+)(になること)$', r'●●\2'),  # 「〇〇になること」→「●●になること」
            (r'(.+)(が重要|が大事|がポイント)$', r'●●\2'),  # 「〇〇が重要」→「●●が重要」
            (r'(.+)(であること|であること)$', r'●●\2'),  # 「〇〇であること」→「●●であること」
        ]

        for pattern, replacement in patterns:
            match = re.search(pattern, t_clean)
            if match:
                result = re.sub(pattern, replacement, t_clean)
                # 長さ調整
                if len(result) > limit:
                    # 末尾から逆算してlimit文字に収める
                    result = '●●' + result[-(limit-2):]
                return result + '！'

        # パターンにマッチしない場合は通常のhookify
        return _hookify(t, limit)

    # タイトル: 最初の文をテーマとして使用（20文字以内）
    first_sentence = sentences[0] if sentences else fallback_title
    title = _hookify(first_sentence.replace("\n", " "), 20)

    # ポイント: 2番目の文または最初の文の続きを使用（タイトルと異なる内容にする）
    if len(sentences) > 1:
        second_sentence = sentences[1]
        point = _create_teaser_point(second_sentence.replace("\n", " "), 20)
    else:
        # 1文しかない場合は、文の後半部分を使う
        words = first_sentence.split()
        if len(words) > 3:
            point = _create_teaser_point(" ".join(words[len(words)//2:]).replace("\n", " "), 20)
        else:
            point = _hookify("続きをチェック！", 20)
    description = point

    if source_url:
        description += f"\n\n📌 元動画: {source_url}"

    description += "\n\n#Shorts"

    return {
        "title": title,
        "description": description,
        "input_tokens": 0,
        "output_tokens": 0,
        "total_tokens": 0,
        "cost_jpy": 0.0
    }
