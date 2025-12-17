"""YouTubeタイトル・説明文生成モジュール"""
import json
import re
from typing import Optional, Dict

import google.generativeai as genai

from app.config import config
from app.logging_utils import log_info, log_warning, log_error


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
            return _generate_with_gemini(transcript_text, source_url)
        except Exception as e:
            log_warning(f"Gemini API failed, using fallback: {e}")

    # フォールバック: ルールベースで生成
    return _generate_fallback(transcript_text, source_url, fallback_title)


def _generate_with_gemini(transcript_text: str, source_url: Optional[str]) -> Dict[str, str]:
    """Gemini APIでタイトルと説明文を生成"""

    log_info("Generating title and description with Gemini API")

    genai.configure(api_key=config.GEMINI_API_KEY)
    model = genai.GenerativeModel(config.GEMINI_MODEL)

    # プロンプト作成（タイトル8文字以内・ポイント10文字以内を明示）
    prompt = f"""以下の文字起こしから、YouTube Shorts用のタイトルと説明文を生成してください。

【文字起こし】
{transcript_text[:1000]}

【要件】
- タイトル: 日本語で8文字以内。短く強い言葉で目を引くこと（例:「最強の裏技」「5秒で即答」）。記号乱用は避ける。
- 説明文: 1行目にショート部分のポイントを10文字以内で書く。2行目以降で簡潔な補足とハッシュタグ（#Shorts含む）。
- JSON形式で回答: {{"title": "タイトル", "description": "説明文"}}

JSON形式のみで回答してください。"""

    response = model.generate_content(
        prompt,
        generation_config={
            "temperature": 0.7,
            "max_output_tokens": 300,
        }
    )

    content = response.text.strip()
    log_info(f"Gemini response: {content[:100]}...")

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

    # JSON抽出
    json_match = re.search(r'\{.*\}', content, re.DOTALL)
    if json_match:
        result = json.loads(json_match.group())
        title = result.get("title", "").strip()
        description = result.get("description", "").strip()

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

    raise ValueError("Failed to parse JSON from Gemini response")


def _generate_fallback(
    transcript_text: str,
    source_url: Optional[str],
    fallback_title: str
) -> Dict[str, str]:
    """ルールベースでタイトルと説明文を生成（フォールバック）"""

    log_info("Generating title and description with rule-based fallback")

    # 先頭文を抽出
    sentences = re.split(r"[。？！\?]", transcript_text.strip()) if transcript_text else []
    first_sentence = (sentences[0].strip() if sentences and sentences[0].strip() else fallback_title).replace("\n", " ")

    def _hookify(text: str, limit: int) -> str:
        t = text.strip()
        if t.endswith("けど"):
            t = t[:-2] + "？"
        if t.endswith("けど、"):
            t = t[:-3] + "？"
        if len(t) > limit:
            t = t[: limit - 1] + "…"
        return t or fallback_title

    # タイトル: 12文字以内に強制
    title = _hookify(first_sentence, 12)

    # 説明文: 先頭行に18文字のポイントを置く
    point = _hookify(first_sentence, 18)
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
