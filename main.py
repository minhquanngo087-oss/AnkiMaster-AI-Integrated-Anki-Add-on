# -*- coding: utf-8 -*-
from aqt import gui_hooks, mw
from aqt.utils import tooltip, showInfo, showCritical
from aqt.qt import (
    QAction, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QLineEdit, QPushButton, QPlainTextEdit,
    QComboBox, QInputDialog, Qt, QProgressBar,
    QGroupBox, QSpinBox, QCheckBox, QMessageBox,
    QScrollArea, QWidget, QTextEdit, QTextBrowser,
    QTreeWidget, QTreeWidgetItem
)
from aqt.editor import Editor
from aqt.browser import Browser
import requests
import json
import re
import os
import time
import base64
import urllib.parse
from datetime import datetime
import wave
import io


# ========== HUGGING FACE IMAGE GENERATION ==========
# Token lấy từ Cài đặt (config "hf_token"), KHÔNG ghi thẳng vào code.
# Endpoint cũ api-inference.huggingface.co đã bị Hugging Face khai tử (trả 410),
# nên dùng router mới: https://router.huggingface.co/hf-inference/models/<model>
HF_ROUTER_URL = "https://router.huggingface.co/hf-inference/models/"
HF_MODELS_TO_TRY = [
    "black-forest-labs/FLUX.1-dev",              # Chất lượng cao nhất
    "black-forest-labs/FLUX.1-schnell",          # Flux bản nhanh
    "stabilityai/stable-diffusion-xl-base-1.0",  # SDXL dự phòng
]

def generate_image_huggingface(prompt, config=None):
    """
    Tạo ảnh qua Hugging Face Inference (router mới).
    Thử lần lượt các model trong HF_MODELS_TO_TRY, trả về bytes ảnh hoặc None.
    """
    if config is None:
        config = load_config()
    token = str(config.get("hf_token") or "").strip()
    if not token.startswith("hf_"):
        print("⚠️ [HF] Chưa cấu hình Hugging Face Token trong Cài đặt.")
        return None

    headers = {"Authorization": f"Bearer {token}"}

    for model_id in HF_MODELS_TO_TRY:
        payload = {"inputs": prompt}
        if "FLUX" in model_id:
            payload["parameters"] = {"width": 1024, "height": 1024}
        print(f"🚀 [HF] {model_id}: '{prompt[:60]}...'")
        try:
            response = requests.post(HF_ROUTER_URL + model_id, headers=headers, json=payload, timeout=90)
            content_type = response.headers.get("Content-Type", "")
            if response.status_code == 200 and "image" in content_type:
                print(f"✅ [HF] Tạo ảnh thành công bằng {model_id}")
                return response.content
            print(f"⚠️ [HF] {model_id} lỗi {response.status_code}: {response.text[:150]}")
        except Exception as e:
            print(f"❌ [HF] {model_id} lỗi kết nối: {e}")

    return None

# ========== CẤU HÌNH ==========
def load_config():
    config = mw.addonManager.getConfig(__name__)
    defaults = {
        "api_keys": [],  # Nhập key trong Tools → Gemini Editor Settings
        "current_key_index": 0,
        "model": GEMINI_DEFAULT_MODEL,
        "voice_name": "",
        "tts_api_key": "",
        "tts_model": "gemini-2.5-flash-preview-tts",
        "image_api_key": "",
        "image_model": "gemini-2.0-flash",
        "auto_image_gen": True,
        "timeout": 300,
        "hf_token": "",  # Thêm Hugging Face token
        "google_cse_key": "", # Google Custom Search API Key
        "google_cse_cx": "",  # Google Custom Search Engine ID
        "image_engine_priority": "pollinations",  # pollinations, hf, or auto
        "image_quality": "medium",  # low, medium, high
        "text_provider": "gemini",  # gemini or groq
        "groq_api_keys": [],
        "groq_model": "llama-3.1-8b-instant"
    }
    if not config:
        return defaults
    
    # TƯƠNG THÍCH NGƯỢC: chuyển đổi từ api_key cũ sang api_keys mới
    if "api_key" in config and "api_keys" not in config:
        config["api_keys"] = [config["api_key"]]
        del config["api_key"]
    
    # Khi cả api_key và api_keys cùng tồn tại, gộp api_key vào api_keys rồi xóa api_key
    if "api_key" in config and "api_keys" in config and config["api_key"] and config["api_key"].strip():
        old_key = config["api_key"].strip()
        if isinstance(config["api_keys"], list):
            if old_key not in config["api_keys"]:
                config["api_keys"].insert(0, old_key)
        elif isinstance(config["api_keys"], str):
                existing_keys = [k.strip() for k in config["api_keys"].splitlines() if k.strip()]
                if old_key not in existing_keys:
                    existing_keys.insert(0, old_key)
                config["api_keys"] = existing_keys
        del config["api_key"]
    
    # Đảm bảo api_keys là list
    if "api_keys" in config and isinstance(config["api_keys"], str):
        config["api_keys"] = [k.strip() for k in config["api_keys"].splitlines() if k.strip()]
    
    # Đảm bảo groq_api_keys là list
    if "groq_api_keys" in config:
        if isinstance(config["groq_api_keys"], str):
            config["groq_api_keys"] = [k.strip() for k in config["groq_api_keys"].replace(',', '\n').split('\n') if k.strip()]
    
    # Merge defaults
    for key, value in defaults.items():
        if key not in config:
            config[key] = value

    # Model đã bị Google khai tử -> chuyển sang model mặc định mới (các model dự phòng vẫn được thử nếu lỗi)
    if str(config.get("model") or "").strip() in ("", "gemini-2.0-flash", "gemini-2.0-flash-exp", "gemini-1.5-flash", "gemini-1.5-pro"):
        config["model"] = GEMINI_DEFAULT_MODEL

    return config

def save_config(config):
    mw.addonManager.writeConfig(__name__, config)

def clean_field_text(value):
    """Bỏ thẻ HTML, &nbsp; và khoảng trắng thừa mà editor Anki hay chèn vào field."""
    import html
    if not value:
        return ""
    text = re.sub(r'<[^>]+>', ' ', str(value))
    text = html.unescape(text).replace('\xa0', ' ')
    return re.sub(r'\s+', ' ', text).strip()

def _memory_key(word):
    return clean_field_text(word).lower()

def _load_memory(name):
    """Đọc bộ nhớ và chuẩn hóa key (các key cũ có thể còn dính HTML như '<div>settings</div>')."""
    raw = load_config().get(name, {}) or {}
    memory = {}
    for key, value in raw.items():
        clean_key = _memory_key(key)
        if clean_key and (clean_key not in memory or clean_key == key):
            memory[clean_key] = clean_field_text(value)
    return memory

def _save_memory(name, word, value):
    key = _memory_key(word)
    value = clean_field_text(value)
    if not key or not value or value == "None":
        return
    config = load_config()
    memory = config.get(name) or {}
    if memory.get(key) == value:
        return  # Không đổi gì -> khỏi ghi config
    memory[key] = value
    config[name] = memory
    save_config(config)

def load_ipa_memory():
    """Tải bộ nhớ IPA mà người dùng đã chỉnh sửa"""
    return _load_memory("ipa_memory")

def save_ipa_memory(word, ipa):
    """Lưu IPA người dùng đã chỉnh sửa vào bộ nhớ hệ thống"""
    _save_memory("ipa_memory", word, ipa)

def load_definition_vi_memory():
    """Tải bộ nhớ nghĩa tiếng Việt mà người dùng đã chỉnh sửa"""
    return _load_memory("definition_vi_memory")

def save_definition_vi_memory(word, definition_vi):
    """Lưu nghĩa tiếng Việt người dùng đã chỉnh sửa vào bộ nhớ hệ thống.
    Sau này AI sẽ bắt buộc dùng đúng nghĩa này khi tạo ví dụ, synonym, v.v."""
    _save_memory("definition_vi_memory", word, definition_vi)

# ========== PHÁT HIỆN NGÔN NGỮ CHO AUDIO ==========
def detect_language_for_audio(text: str):
    """
    Phát hiện ngôn ngữ từ văn bản để chọn giọng đọc phù hợp
    Trả về: 'en', 'vi', 'zh', 'ja', hoặc 'default'
    """
    if not text or not text.strip():
        return "default"
    
    text_lower = text.lower()
    
    # 1. Kiểm tra tiếng Trung (chữ Hán)
    if re.search(r'[\u4e00-\u9fff]', text):
        return "zh"
    
    # 2. Kiểm tra tiếng Nhật (Hiragana, Katakana, Kanji)
    if re.search(r'[\u3040-\u309f\u30a0-\u30ff\u4e00-\u9fff]', text):
        return "ja"
    
    # 3. Kiểm tra tiếng Việt (ký tự có dấu đặc trưng)
    vietnamese_chars = [
        'á', 'à', 'ả', 'ã', 'ạ', 'ă', 'ắ', 'ằ', 'ẳ', 'ẵ', 'ặ',
        'â', 'ấ', 'ầ', 'ẩ', 'ẫ', 'ậ', 'é', 'è', 'ẻ', 'ẽ', 'ẹ',
        'ê', 'ế', 'ề', 'ể', 'ễ', 'ệ', 'í', 'ì', 'ỉ', 'ĩ', 'ị',
        'ó', 'ò', 'ỏ', 'õ', 'ọ', 'ô', 'ố', 'ồ', 'ổ', 'ỗ', 'ộ',
        'ơ', 'ớ', 'ờ', 'ở', 'ỡ', 'ợ', 'ú', 'ù', 'ủ', 'ũ', 'ụ',
        'ư', 'ứ', 'ừ', 'ử', 'ữ', 'ự', 'ý', 'ỳ', 'ỷ', 'ỹ', 'ỵ',
        'đ', 'Đ'
    ]
    
    if any(char in text_lower for char in vietnamese_chars):
        return "vi"
    
    # 4. Kiểm tra tiếng Hàn
    if re.search(r'[\uac00-\ud7a3]', text):
        return "ko"
    
    # 5. Kiểm tra tiếng Anh (mặc định)
    # Nếu có ký tự Latin và không có ký tự đặc biệt của ngôn ngữ khác
    if re.search(r'[a-zA-Z]', text) and not re.search(r'[äöüßÄÖÜ]', text):
        return "en"
    
    # 6. Kiểm tra tiếng Đức
    if re.search(r'[äöüßÄÖÜ]', text):
        return "de"
    
    # Mặc định
    return "default"

def get_voice_for_language(language_code: str, config: dict):
    """
    Chọn giọng đọc phù hợp dựa trên mã ngôn ngữ
    Trả về tên giọng cho Gemini TTS
    """
    # Ưu tiên giọng từ cấu hình của người dùng
    user_voice = str(str(config.get("voice_name") or "") or '').strip()
    if user_voice:
        return user_voice
    
    # Mapping ngôn ngữ -> giọng đọc mặc định
    # Giọng prebuilt của Gemini TTS đều đọc được nhiều ngôn ngữ; các tên cũ
    # 'Vienne', 'Zhiyuan', 'Izumi' không tồn tại -> API báo lỗi.
    voice_mapping = {
        'en': 'Kore',
        'vi': 'Kore',
        'zh': 'Kore',
        'ja': 'Kore',
        'ko': 'Kore',
        'de': 'Kore',
        'default': 'Kore'
    }

    return voice_mapping.get(language_code, 'Kore')
# ========== HÀM XÁC ĐỊNH ĐƯỜNG DẪN DOWNLOAD ==========
def get_download_path():
    """Xác định đường dẫn download dựa trên platform"""
    import platform
    if platform.system() == "Windows":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    elif platform.system() == "Darwin":  # macOS
        return os.path.join(os.path.expanduser("~"), "Downloads")
    elif platform.system() == "Linux":
        return os.path.join(os.path.expanduser("~"), "Downloads")
    else:
        # Mobile devices - trả về thông báo
        return "thư mục Downloads của thiết bị"

TOPIC_MAPPING = {
    # English topics
    "education": "học tập, giáo dục, trường học, lớp học",
    "technology": "công nghệ, máy tính, phần mềm, kỹ thuật",
    "business": "kinh doanh, thương mại, công ty, doanh nghiệp",
    "medical": "y tế, bệnh viện, sức khỏe, y học",
    "science": "khoa học, nghiên cứu, thí nghiệm",
    "sports": "thể thao, thi đấu, vận động viên",
    "music": "âm nhạc, nhạc cụ, ca sĩ, bài hát",
    "art": "nghệ thuật, hội họa, sáng tạo",
    "travel": "du lịch, du hành, khám phá",
    "food": "ẩm thực, đồ ăn, nấu nướng",
    "finance": "tài chính, ngân hàng, đầu tư",
    "law": "luật pháp, pháp lý, tòa án",
    "environment": "môi trường, thiên nhiên, bảo tồn",
    "politics": "chính trị, chính phủ, chính sách",
    "daily": "cuộc sống hàng ngày, giao tiếp thông thường",
    
    # Vietnamese topics
    "học tập": "học tập, giáo dục, trường học, lớp học",
    "công nghệ": "công nghệ, máy tính, phần mềm, kỹ thuật",
    "kinh doanh": "kinh doanh, thương mại, công ty, doanh nghiệp",
    "y tế": "y tế, bệnh viện, sức khỏe, y học",
    "khoa học": "khoa học, nghiên cứu, thí nghiệm",
    "thể thao": "thể thao, thi đấu, vận động viên",
    "âm nhạc": "âm nhạc, nhạc cụ, ca sĩ, bài hát",
    "nghệ thuật": "nghệ thuật, hội họa, sáng tạo",
    "du lịch": "du lịch, du hành, khám phá",
    "ẩm thực": "ẩm thực, đồ ăn, nấu nướng",
    "tài chính": "tài chính, ngân hàng, đầu tư",
    "luật pháp": "luật pháp, pháp lý, tòa án",
    "môi trường": "môi trường, thiên nhiên, bảo tồn",
    "chính trị": "chính trị, chính phủ, chính sách",
    "đời sống": "cuộc sống hàng ngày, giao tiếp thông thường"
}

def expand_topic_to_context(topic):
    """Chuyển đổi topic đơn giản thành ngữ cảnh chi tiết"""
    topic_lower = topic.strip().lower()
    
    # Kiểm tra xem có phải là topic đã biết không
    if topic_lower in TOPIC_MAPPING:
        return TOPIC_MAPPING[topic_lower]
    else:
        # Nếu không tìm thấy, trả về topic gốc (có thể là câu mô tả chi tiết)
        return topic

def detect_and_expand_context(user_context):
    """Phát hiện và mở rộng context nếu là topic đơn giản"""
    if not user_context or not user_context.strip():
        return ""
    
    context = user_context.strip()
    
    # Nếu context chỉ là 1-2 từ và không có dấu câu, coi như topic
    words = context.split()
    if len(words) <= 2 and not any(char in context for char in ['.', ',', '!', '?', ';', ':']):
        expanded = expand_topic_to_context(context)
        if expanded != context:
            print(f"🔍 Đã nhận diện topic: '{context}' -> '{expanded}'")
            return expanded
    
    # Trả về context gốc nếu là câu mô tả chi tiết
    return context

# ========== TÊN TRƯỜNG DỮ LIỆU ==========
FIELD_MAP = {
    "Word": "keyword", "IPA": "ipa", "PartOfSpeech": "part_of_speech",
    "Definition_EN": "definition_en", "Definition_VI": "definition_vi",
    "Example_EN": "example_en", "Example_VI": "example_vi",
    "Synonyms": "synonyms", "Antonyms": "antonyms", "WordFamily": "word_family",
    "Collocations": "collocations", "PhrasalVerbs": "phrasal_verbs",
    "Idioms": "idioms", "ImageQuery": "image_query", "Image Querry": "image_query", "Recommendation": "recommendation",
    "Language": "language", "GrammarNotes": "grammar_notes",
    "UsagePatterns": "usage_patterns",
    "Etymology": "etymology",
    "Radicals": "radicals",
    "StrokeCount": "stroke_count",
    "StrokeCountChar": "stroke_count_char",
    "Exercises": "exercises",
    "Reading": "reading",
    "TreeDiagram": "tree_diagram",
    # THÊM CÁC TRƯỜNG MỚI
    "Reading_Vocabulary": "reading_vocabulary",
    "Reading_Structures": "reading_structures",
    "OtherMeaning": "other_meaning",
    # LƯU Ý: Trường "Context" KHÔNG có trong FIELD_MAP vì đây là trường do
    # người dùng tự nhập, không bao giờ để AI ghi đè lên.
}
REQUIRED_FIELDS = list(FIELD_MAP.keys())

def log_error(msg):
    # addonFolder() bắt buộc có tham số, gọi thiếu sẽ ném TypeError -> dùng thư mục của file này
    try:
        log_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor_error_log.txt")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}\n")
    except Exception:
        print(f"Gemini Add-on Error: {msg}")

# ========== RÚT GỌN PHẢN HỒI CHO MOBILE ==========
def summarize_feedback_for_mobile(full_feedback, max_length=200):
    """Rút gọn phản hồi cho mobile, giữ ý chính"""
    if not full_feedback:
        return "Không có phản hồi"
    
    # Loại bỏ các phần dài dòng, giữ lại ý chính
    import re
    
    # Giữ lại các phần quan trọng: đánh giá tổng quan, lỗi chính, đề xuất
    important_parts = []
    
    # Tìm các câu quan trọng
    sentences = re.split(r'[.!?]', full_feedback)
    
    keywords = [
        'tốt', 'đúng', 'sai', 'lỗi', 'cần', 'nên', 'không nên', 
        'chính xác', 'tự nhiên', 'ngữ pháp', 'từ vựng', 'cải thiện',
        'sửa', 'đề xuất', 'gợi ý', 'khuyên'
    ]
    
    for sentence in sentences:
        sentence = sentence.strip()
        if any(keyword in sentence.lower() for keyword in keywords) and len(sentence) > 10:
            important_parts.append(sentence)
    
    # Nếu không tìm thấy phần quan trọng, lấy 2 câu đầu
    if not important_parts and len(sentences) >= 2:
        important_parts = sentences[:2]
    
    # Ghép lại và giới hạn độ dài
    if important_parts:
        summary = '. '.join(important_parts) + '.'
        if len(summary) > max_length:
            summary = summary[:max_length] + '...'
        return summary
    else:
        # Fallback: cắt ngắn
        if len(full_feedback) > max_length:
            return full_feedback[:max_length] + '...'
        return full_feedback

def is_mobile_user_agent():
    """Phát hiện user agent mobile từ webview"""
    try:
        # Lấy user agent từ webview của Anki
        user_agent = mw.web._page.profile().httpUserAgent()
        mobile_indicators = ['Mobile', 'Android', 'iPhone', 'iPad', 'iPod', 'BlackBerry', 'IEMobile', 'Opera Mini']
        return any(indicator in user_agent for indicator in mobile_indicators)
    except:
        return False
# ========== CẬP NHẬT HÀM PHÂN TÍCH CONTEXT VỚI LOẠI TỪ ==========
# ========== CẬP NHẬT HÀM PHÂN TÍCH CONTEXT (THÔNG MINH HƠN) ==========
def parse_context_with_pos(context_text):
    """
    Phân tích context để trích xuất ngữ cảnh và loại từ.
    Hỗ trợ viết tắt: [n], (v), business [noun], run (verb)...
    """
    if not context_text or not context_text.strip():
        return ("", "")
    
    context = context_text.strip()
    requested_pos = ""
    
    # Regex tìm loại từ ở cuối câu (chấp nhận [n], (verb), [adj]...)
    pos_pattern = r'[\(\[]\s*(noun|verb|adjective|adverb|n|v|adj|adv)\s*[\)\]]\s*$'
    
    match = re.search(pos_pattern, context, re.IGNORECASE)
    if match:
        raw_pos = match.group(1).lower()
        
        # Chuẩn hóa về dạng đầy đủ
        pos_mapping = {
            'n': 'noun', 'noun': 'noun',
            'v': 'verb', 'verb': 'verb',
            'adj': 'adjective', 'adjective': 'adjective',
            'adv': 'adverb', 'adverb': 'adverb'
        }
        requested_pos = pos_mapping.get(raw_pos, raw_pos)
        
        # Xóa phần loại từ khỏi context để lấy nội dung context sạch
        context = re.sub(pos_pattern, '', context, flags=re.IGNORECASE).strip()
    
    # Mở rộng context nếu nó là một topic đơn (ví dụ: "medical" -> "y tế, bệnh viện...")
    expanded_context = ""
    if context:
        expanded_context = detect_and_expand_context(context)
    
    return (expanded_context, requested_pos)

# ========== KIỂM TRA CHÍNH TẢ (CHỈ BÁO KHI SAI MẶT CHỮ) ==========
# Ký tự vô hình hay dính theo khi copy từ Word/Excel/web (zero-width space, BOM, soft hyphen...)
_INVISIBLE_CHARS_RE = re.compile("[­​-\u200F- ⁠-⁤﻿]")

def normalize_word_for_compare(text):
    """Đưa từ về dạng sạch để so sánh: bỏ HTML, ký tự vô hình, dấu câu/nháy ở hai đầu,
    gộp khoảng trắng, chữ thường. 'Stakeholder​ ' -> 'stakeholder'."""
    import unicodedata
    text = unicodedata.normalize("NFKC", clean_field_text(text))
    text = _INVISIBLE_CHARS_RE.sub("", text)
    text = text.strip(" \t\"'“”‘’.,;:!?()[]{}").lower()
    return re.sub(r"\s+", " ", text)

def _is_inflection_of(a, b):
    """True nếu a và b chỉ khác nhau ở đuôi biến đổi thông dụng
    (số nhiều, quá khứ, -ing, so sánh hơn): stakeholders/stakeholder, allocated/allocate, stopped/stop."""
    def stems(word):
        out = {word}
        for suffix, repl in (("ies", "y"), ("ied", "y"), ("es", ""), ("s", ""), ("ed", ""), ("ed", "e"),
                             ("d", ""), ("ing", ""), ("ing", "e"), ("er", ""), ("est", ""), ("er", "e"), ("est", "e")):
            if word.endswith(suffix) and len(word) - len(suffix) >= 2:
                base = word[:-len(suffix)] + repl
                out.add(base)
                if len(base) > 2 and base[-1] == base[-2]:   # stopped -> stopp -> stop
                    out.add(base[:-1])
        return out
    return bool(stems(a) & stems(b))

def is_real_spelling_error(original, suggestion, ai_flag=None):
    """Chỉ là lỗi chính tả khi từ bị viết sai mặt chữ (ohld/hodl -> hold).
    Khác viết hoa, khoảng trắng, ký tự vô hình hay khác dạng (số nhiều, quá khứ...) đều KHÔNG phải lỗi."""
    o, s = normalize_word_for_compare(original), normalize_word_for_compare(suggestion)
    if not s or o == s or ai_flag is False:
        return False
    return not _is_inflection_of(o, s)


def tidy_main_fields(data):
    """Lưới an toàn khi AI không theo luật trong prompt: loại từ chỉ giữ MỘT giá trị ('verb/noun' -> 'verb')."""
    pos = str(data.get("part_of_speech") or "").strip()
    if pos:
        data["part_of_speech"] = re.split(r"\s*(?:/|,|;|\band\b|\bor\b)\s*", pos)[0].strip() or pos
    return data

# ========== KIỂM TRA CHẤT LƯỢNG NGHĨA (CHẠY TRONG MÁY, KHÔNG TỐN API) ==========
def check_entry_quality(data, vi_given_by_user=False):
    """Trả về danh sách vấn đề (tiếng Việt) của các mục chính; danh sách rỗng = đạt."""
    issues = []
    pos = clean_field_text(data.get("part_of_speech") or "")
    vi = clean_field_text(data.get("definition_vi") or "")
    en = clean_field_text(data.get("definition_en") or "")
    if not pos:
        issues.append("thiếu loại từ")
    elif re.search(r"[/,;]|\band\b|\bor\b", pos):
        issues.append("nhiều loại từ")
    if not vi_given_by_user:
        if not vi:
            issues.append("thiếu nghĩa tiếng Việt")
        else:
            if len(vi.split()) > 12:
                issues.append("nghĩa VI dài như mô tả")
            if re.search(r"(động từ|danh từ|tính từ|trạng từ)\s*:", vi, re.IGNORECASE):
                issues.append("nghĩa VI trộn nhiều loại từ")
    if not en:
        issues.append("thiếu định nghĩa EN")
    elif len(en.split()) > 30:
        issues.append("định nghĩa EN quá dài")
    return issues

# Các mục của thẻ được chấm "có / thiếu" trong bảng báo cáo (khoá trong dữ liệu AI, tên hiển thị)
REPORT_SECTIONS = [("ipa", "IPA"), ("example_en", "Ví dụ"), ("synonyms", "Đồng nghĩa"), ("collocations", "Collocation"),
                   ("word_family", "Họ từ"), ("other_meaning", "Nghĩa khác"), ("etymology", "Gốc từ"),
                   ("reading", "Bài đọc"), ("exercises", "Bài tập"), ("recommendation", "Khuyến nghị")]

def summarize_note_sections(data):
    """{tên mục: True/False} cho biết mục đó có nội dung không. Bài đọc chỉ tạo cho từ tiếng Anh nên bỏ qua với ngôn ngữ khác."""
    def filled(value):
        if isinstance(value, dict):
            return any(filled(v) for v in value.values())
        if isinstance(value, list):
            return len(value) > 0
        return bool(clean_field_text(str(value or "")))
    sections = {}
    for key, label in REPORT_SECTIONS:
        if key == "reading" and data.get("language") not in (None, "English"):
            continue
        sections[label] = filled(data.get(key))
    return sections

# ========== THEO DÕI LƯỢT GỌI GEMINI MỖI NGÀY ==========
# Gói miễn phí giới hạn theo SỐ LƯỢT GỌI MỖI NGÀY (RPD) cho từng model, reset lúc 0:00 giờ Mỹ (Pacific).
# Số mặc định lấy theo bảng Rate Limit trong Google AI Studio; sửa được ở Tools → Add-ons → Config ("gemini_daily_limits").
GEMINI_DAILY_LIMIT_DEFAULTS = {"gemini-3.8-flash": 20, "gemini-2.5-flash": 20,
                               "gemini-3.5-flash-lite": 500, "gemini-flash-lite-latest": 500}
_usage_lock = None

def _pacific_offset_hours(utc_now):
    """Giờ Pacific: UTC-7 khi có giờ mùa hè (Chủ nhật thứ 2 của tháng 3 -> Chủ nhật đầu tháng 11), còn lại UTC-8."""
    from datetime import timedelta
    def nth_sunday(month, n):
        first = datetime(utc_now.year, month, 1)
        return first + timedelta(days=(6 - first.weekday()) % 7 + 7 * (n - 1))
    dst_start = nth_sunday(3, 2) + timedelta(hours=10)   # 2:00 PST = 10:00 UTC
    dst_end = nth_sunday(11, 1) + timedelta(hours=9)     # 2:00 PDT = 9:00 UTC
    return -7 if dst_start <= utc_now < dst_end else -8

def gemini_quota_day_and_reset():
    """(ngày tính quota theo giờ Pacific, giờ reset kế tiếp quy ra giờ Việt Nam dạng 'HH:MM dd/mm')."""
    from datetime import timedelta
    utc_now = datetime.utcnow()
    offset = _pacific_offset_hours(utc_now)
    pacific_now = utc_now + timedelta(hours=offset)
    next_midnight_pacific = datetime(pacific_now.year, pacific_now.month, pacific_now.day) + timedelta(days=1)
    reset_vn = next_midnight_pacific - timedelta(hours=offset) + timedelta(hours=7)
    return pacific_now.strftime("%Y-%m-%d"), reset_vn.strftime("%H:%M %d/%m")

def _gemini_usage_path():
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_files", "gemini_usage.json")

def _gemini_kid(key):
    return key.strip()[-8:]

def load_gemini_usage():
    """{'day', 'used': {'kid|model': n}, 'exhausted': {'kid|model': true}, 'keys': {kid: {'state','at'}}}.
    Sang ngày mới (giờ Pacific) thì xoá số lượt và trạng thái hết lượt, giữ trạng thái key chết."""
    day, _ = gemini_quota_day_and_reset()
    try:
        with open(_gemini_usage_path(), encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        data = {}
    if data.get("day") != day:
        data = {"day": day, "used": {}, "exhausted": {}, "keys": data.get("keys", {})}
    for name in ("used", "exhausted", "keys"):
        data.setdefault(name, {})
    return data

def record_gemini_call(key, model, outcome):
    """outcome: 'ok' (gọi thành công) | 'dead' (key không hợp lệ) | 'exhausted' (hết lượt hôm nay) | 'unavailable' (model không cho key này dùng)."""
    global _usage_lock
    import threading
    if _usage_lock is None:
        _usage_lock = threading.Lock()
    with _usage_lock:
        try:
            data = load_gemini_usage()
            kid, slot = _gemini_kid(key), f"{_gemini_kid(key)}|{model}"
            if outcome == "ok":
                data["used"][slot] = data["used"].get(slot, 0) + 1
                data["keys"][kid] = {"state": "alive", "at": int(time.time())}
            elif outcome == "dead":
                data["keys"][kid] = {"state": "dead", "at": int(time.time())}
            elif outcome in ("exhausted", "unavailable"):
                data["exhausted"][slot] = outcome
            os.makedirs(os.path.dirname(_gemini_usage_path()), exist_ok=True)
            with open(_gemini_usage_path(), "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception as e:
            print(f"[Gemini] Không ghi được thống kê lượt gọi: {e}")

def estimate_gemini_capacity(config, keys=None):
    """Ước tính số từ còn thêm được hôm nay (1 từ ≈ 1 lượt gọi) với các key của add-on."""
    limits = dict(GEMINI_DAILY_LIMIT_DEFAULTS)
    limits.update(config.get("gemini_daily_limits") or {})
    if keys is None:
        keys = get_key_list("\n".join(config.get("api_keys") or []))
    usage = load_gemini_usage()
    _, reset_vn = gemini_quota_day_and_reset()
    per_model = {m: 0 for m in GEMINI_FALLBACK_MODELS if limits.get(m)}
    alive = dead = 0
    for key in keys:
        kid = _gemini_kid(key)
        if usage["keys"].get(kid, {}).get("state") == "dead":
            dead += 1
            continue
        alive += 1
        for model in per_model:
            slot = f"{kid}|{model}"
            if not usage["exhausted"].get(slot):
                per_model[model] += max(0, int(limits[model]) - usage["used"].get(slot, 0))
    flash = sum(n for m, n in per_model.items() if "lite" not in m)
    lite = sum(n for m, n in per_model.items() if "lite" in m)
    return {"alive": alive, "dead": dead, "per_model": per_model, "flash_words": flash,
            "lite_words": lite, "reset_vn": reset_vn, "used": usage["used"]}

def format_capacity_summary(capacity):
    return (f"🔑 Key còn dùng được: {capacity['alive']}" + (f" | 💀 key chết: {capacity['dead']}" if capacity['dead'] else "")
            + f"\n📈 Còn thêm được khoảng: {capacity['flash_words']} từ (model Flash, chất lượng tốt)"
            + f" + {capacity['lite_words']} từ (Flash-Lite)"
            + f"\n🔄 Lượt miễn phí reset lúc: {capacity['reset_vn']} (giờ Việt Nam)"
            + "\nℹ️ Ước tính: các key chung một project dùng chung lượt nên số thật có thể thấp hơn.")

# ========== KHO GỐC: TỪ ĐIỂN ĐÓNG GÓI SẴN TRONG ADD-ON ==========
# File SQLite (cả database nằm trong 1 file: data/en_vi_dictionary.sqlite), gồm 3 nguồn:
#   entries/forms: Wiktionary tiếng Anh (kaikki.org) -> IPA, loại từ, dạng biến đổi (CC BY-SA 4.0)
#   vi_dict:       Từ điển Anh-Việt OVDP (Open Vietnamese Dictionary Project) -> nghĩa tiếng Việt (GPLv2)
#   core:          ~1 vạn từ thông dụng nhất, định nghĩa "(GUIDEWORD) ..." + nghĩa VI ngắn viết sẵn
#                  (Flash-Lite soạn 1 lần lúc đóng gói, dựa theo nghĩa OVDP) -> thẻ nhẹ dùng thẳng, không gọi AI
# Khi phát hành phải ghi nguồn + giấy phép (xem bảng meta trong file).
DICTIONARY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "en_vi_dictionary.sqlite")
LITE_TEXT_MODEL = "gemini-3.5-flash-lite"   # thẻ nhẹ: 500 lượt/ngày, nhanh

def _plain_ovdp_meaning(text):
    """'(thương nghiệp) danh đơn hàng gửi (có giá...)' -> 'danh đơn hàng gửi': bỏ nhãn/giải thích trong ngoặc."""
    return re.sub(r"\s+", " ", re.sub(r"\([^)]*\)", "", text)).strip(" ,;.")

def _inflect_ipa(lemma_ipa, form, lemma):
    """IPA của dạng -s/-es, -ed, -ing suy ra từ IPA từ gốc theo quy tắc phát âm:
    -s: /ɪz/ sau âm gió (s z ʃ ʒ tʃ dʒ), /s/ sau âm vô thanh (p t k f θ), còn lại /z/;
    -ed: /ɪd/ sau t d, /t/ sau âm vô thanh, còn lại /d/; -ing: /ɪŋ/. Không đoán được thì trả ''."""
    core = lemma_ipa.strip().strip("/[]").rstrip(".")
    if not core or not form.startswith(lemma[:max(1, len(lemma) - 2)]):
        return ""
    last = core[-2:] if core[-2:] in ("tʃ", "dʒ") else core[-1]
    if form.endswith("ing"):
        suffix = "ɪŋ"
    elif form.endswith("ed"):
        suffix = "ɪd" if last in ("t", "d") else ("t" if last in ("p", "k", "f", "θ", "s", "ʃ", "tʃ") else "d")
    elif form.endswith("s"):
        suffix = "ɪz" if last in ("s", "z", "ʃ", "ʒ", "tʃ", "dʒ") else ("s" if last in ("p", "t", "k", "f", "θ") else "z")
    else:
        return ""
    return f"/{core}{suffix}/"

_PHRASE_SLOTS = {"sb", "sth", "sb's", "someone", "something", "somebody", "someone's", "somebody's"}
_POSSESSIVES = {"my", "your", "his", "her", "our", "their", "one's"}
# Từ chức năng trong cụm: dùng dạng đọc đầy đủ như từ điển, không lấy dạng đọc nhẹ / phương ngữ của Wiktionary
_FUNCTION_WORD_IPA = {"a": "ə", "an": "æn", "the": "ðə", "to": "tuː", "of": "ɒv", "in": "ɪn", "on": "ɒn", "at": "æt",
                      "for": "fɔː", "from": "frɒm", "with": "wɪð", "by": "baɪ", "up": "ʌp", "out": "aʊt", "off": "ɒf",
                      "down": "daʊn", "over": "ˈəʊvə", "into": "ˈɪntuː", "about": "əˈbaʊt", "and": "ænd", "or": "ɔː",
                      "as": "æz", "one's": "wʌnz", "oneself": "wʌnˈself", "be": "biː", "it": "ɪt", "no": "nəʊ"}

def _phrase_key_candidates(key, con):
    """Cách người dùng gõ một cụm khác với dạng lưu trong kho (lấy từ giáo trình):
    'accuse someone of' -> 'accuse of', 'keep your chin up' -> "keep one's chin up",
    'looked forward to' -> 'look forward to'. Trả về các key để thử lần lượt."""
    words = [w for w in key.split() if w not in _PHRASE_SLOTS]
    words = ["one's" if w in _POSSESSIVES else w for w in words]
    candidates = [" ".join(words)]
    lemma = con.execute("SELECT lemma FROM forms WHERE form_lc = ?", (words[0],)).fetchone() if words else None
    if lemma:
        candidates.append(" ".join([lemma[0].lower()] + words[1:]))
    return [c for c in dict.fromkeys(candidates) if c and c != key]

def lookup_dictionary(word, pos_hint=""):
    """Tra kho gốc. Dạng biến đổi (betrayed) được nối về từ gốc (betray) để lấy nghĩa, nhưng giữ IPA của chính dạng đó.
    Trả về None nếu không có, hoặc dict: pos, ipa, definition_en, definition_vi,
    curated (True = bản soạn sẵn đúng format, dùng thẳng được), vi_hints (nghĩa OVDP để gợi ý cho AI)."""
    import sqlite3
    if not os.path.exists(DICTIONARY_FILE):
        return None
    key = normalize_word_for_compare(word)
    typed = key   # cụm người dùng gõ (looked forward to): IPA ghép theo đúng chữ này, nghĩa lấy theo dạng trong kho
    con = sqlite3.connect(f"file:{DICTIONARY_FILE}?mode=ro", uri=True)
    if " " in key:
        try:
            if not con.execute("SELECT 1 FROM core WHERE word_lc = ?", (key,)).fetchone():
                for candidate in _phrase_key_candidates(key, con):
                    if con.execute("SELECT 1 FROM core WHERE word_lc = ?", (candidate,)).fetchone():
                        key = candidate
                        break
        except sqlite3.OperationalError:
            pass

    def rows(sql, args):
        try:
            return con.execute(sql, args).fetchall()
        except sqlite3.OperationalError:   # kho bản cũ chưa có bảng core / vi_dict
            return []
    try:
        # Ưu tiên bản soạn sẵn: của chính từ đó, rồi của từ gốc (betrayed -> betray), rồi mới tới bản thô
        own = rows("SELECT pos, ipa, gloss_en, vi_json FROM entries WHERE word_lc = ?", (key,))
        form = rows("SELECT lemma, pos, ipa FROM forms WHERE form_lc = ?", (key,))
        lemma, form_pos, form_ipa = key, "", ""
        if not rows("SELECT 1 FROM core WHERE word_lc = ?", (key,)) and form and \
                (rows("SELECT 1 FROM core WHERE word_lc = ?", (form[0][0].lower(),)) or not own):
            lemma, form_pos = form[0][0].lower(), form[0][1]
            # IPA phải là của chính dạng này (không mượn IPA từ gốc); không có thì để trống cho AI điền
            form_ipa = form[0][2] or next((o[1] for o in own if o[1]), "")
        elif not own and not rows("SELECT 1 FROM core WHERE word_lc = ?", (key,)):
            return None
        wiki = rows("SELECT pos, ipa, gloss_en, vi_json FROM entries WHERE word_lc = ?", (lemma,))
        core = rows("SELECT pos, definition_en, definition_vi FROM core WHERE word_lc = ?", (lemma,))
        ovdp = rows("SELECT pos, meanings_json, special_json FROM vi_dict WHERE word_lc = ?", (lemma,))
    finally:
        con.close()
    if not wiki and not core:
        return None

    curated = bool(core) and (not pos_hint or core[0][0] == pos_hint)
    pos = core[0][0] if curated else (pos_hint or form_pos or (wiki[0][0] if wiki else ""))
    same_pos = [w for w in wiki if w[0] == pos] or wiki
    if lemma != key:
        lemma_ipa = next((w[1] for w in same_pos if w[1]), "")
        ipa = form_ipa or _inflect_ipa(lemma_ipa, key, lemma)
    else:
        ipa = next((w[1] for w in same_pos if w[1]), "") or next((w[1] for w in wiki if w[1]), "")
    if not ipa and " " in key:   # cụm từ (take over): ghép IPA của từng từ
        parts = [_FUNCTION_WORD_IPA.get(p) or (lookup_dictionary(p) or {}).get("ipa", "").strip("/[]")
                 for p in typed.split() if p not in _PHRASE_SLOTS]
        ipa = f"/{' '.join(parts)}/" if all(parts) else ""
    ovdp_same = [json.loads(m) for p, m, _ in ovdp if p == pos and m] or [json.loads(m) for _, m, _ in ovdp if m]
    vi_hints = [x for ms in ovdp_same for x in ms][:3]
    business = [x for _, _, s in ovdp for x in json.loads(s or "{}").get("kinh tế", [])][:3]
    if curated:
        definition_en, definition_vi = core[0][1], core[0][2]
    else:
        definition_en = next((w[2] for w in same_pos if w[2]), "")
        plain = [m for m in (_plain_ovdp_meaning(x) for x in vi_hints) if m]
        wiki_vi = [v[0] for w in same_pos for v in json.loads(w[3] or "[]")]
        definition_vi = ", ".join(plain[:2] or wiki_vi[:3])
    return {"word": word, "lemma": lemma if lemma != key else "", "pos": pos, "ipa": ipa,
            "definition_en": definition_en, "definition_vi": definition_vi, "curated": curated,
            "vi_hints": vi_hints + [f"(kinh tế) {b}" for b in business]}

def ask_gemini_lite_fields(word, config, user_context="", hints=None, language="English"):
    """Gọi Gemini Flash-Lite chỉ cho 4 mục cơ bản của thẻ nhẹ (nhanh, ít token)."""
    clean_context, requested_pos = parse_context_with_pos(clean_field_text(user_context))
    ipa_rule = {"Chinese": "Hanyu Pinyin", "Japanese": "Romaji", "Korean": "Romaja"}.get(language, "British IPA")
    prompt = f"""You are a bilingual {language}–Vietnamese learner's dictionary.
Word: "{word}" (language: {language})
{f'Context: {clean_context}' if clean_context else ''}
{f'Required part of speech: {requested_pos}' if requested_pos else ''}
Dictionary hints (may be incomplete or not match the context): {json.dumps(hints or {}, ensure_ascii=False)}

Return JSON only:
{{"is_misspelled": false, "corrected_spelling": "",
 "part_of_speech": "EXACTLY ONE: noun, verb, adjective, adverb, phrasal verb, idiom, preposition, conjunction, pronoun, determiner, interjection, phrase",
 "ipa": "{ipa_rule} of the word exactly as written",
 "definition_en": "(GUIDEWORD) simple Cambridge-style definition of ONE meaning, max 20 easy words",
 "definition_vi": "short Vietnamese equivalent, 1-6 words, no explanation"}}
Rules: keep the word form as given (plurals and past forms are correct words). is_misspelled is true ONLY when the letters are wrong (e.g. "ohld" for "hold").
definition_vi: prefer the wording of vietnamese_dictionary_meanings (OVDP) when it is natural; modernise old-fashioned wording.
Use the meaning that fits the context; without context use the most common meaning."""
    url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{LITE_TEXT_MODEL}:generateContent?key={{key}}"
    payload = {"contents": [{"parts": [{"text": prompt}]}],
               "generationConfig": {"responseMimeType": "application/json", "temperature": 0.3, "maxOutputTokens": 2000}}
    success, result = call_gemini_with_key_rotation(url_template, {"Content-Type": "application/json"}, payload, config, timeout=60)
    if not success:
        return (False, result)
    try:
        parts = result.json()["candidates"][0]["content"]["parts"]
        text = "".join(p.get("text", "") for p in parts if not p.get("thought"))
        data, _ = safe_json_parse(text, word)
        return (True, data)
    except Exception as e:
        return (False, f"Flash-Lite trả dữ liệu lỗi: {e}")

def get_lite_card_data(keyword, config, user_context="", forced_definition_vi=""):
    """Dữ liệu cho THẺ NHẸ: chỉ Word, IPA, PartOfSpeech, Definition_EN, Definition_VI.
    Từ có bản soạn sẵn trong kho gốc (core) -> dùng thẳng, không gọi AI. Chỉ gọi Gemini Flash-Lite khi
    từ chưa có bản soạn sẵn, hoặc người dùng có nhập ngữ cảnh (nghĩa trong kho chưa chắc khớp ngữ cảnh);
    khi đó gửi kèm nghĩa OVDP để nghĩa tiếng Việt khớp từ điển.
    Trả về giống get_gemini_data: (True, data) | ("spelling_correction", gợi ý) | (False, lỗi)."""
    keyword = _INVISIBLE_CHARS_RE.sub("", clean_field_text(keyword)).strip()
    user_context = clean_field_text(user_context)
    language = detect_language(keyword)
    clean_context, requested_pos = parse_context_with_pos(user_context)
    entry = lookup_dictionary(keyword, requested_pos) if language == "English" else None
    data = {"keyword": keyword, "language": language, "lite": True}
    if entry:
        data.update(ipa=entry["ipa"], part_of_speech=entry["pos"], definition_en=entry["definition_en"],
                    definition_vi=entry["definition_vi"])
    locked_vi = clean_field_text(forced_definition_vi) or load_definition_vi_memory().get(keyword.lower(), "")

    if entry and entry["curated"] and entry["ipa"] and not clean_context:
        data["lite_source"] = "kho gốc"
    else:
        hints = {k: data[k] for k in ("part_of_speech", "ipa") if data.get(k)}
        if entry and entry["vi_hints"]:
            hints["vietnamese_dictionary_meanings"] = entry["vi_hints"]
        ok, ai = ask_gemini_lite_fields(keyword, config, user_context, hints, language)
        if not ok:
            if not entry:
                return (False, ai)
            data["lite_source"] = "kho gốc thô (Flash-Lite lỗi)"
        else:
            ai_flag = ai.get("is_misspelled")
            if isinstance(ai_flag, str):
                ai_flag = ai_flag.strip().lower() == "true"
            corrected = str(ai.get("corrected_spelling") or "").strip()
            if not entry and corrected and is_real_spelling_error(keyword, corrected, ai_flag):
                return ("spelling_correction", corrected)
            for field in ("part_of_speech", "definition_en", "definition_vi"):
                if ai.get(field):
                    data[field] = str(ai[field]).strip()
            if not data.get("ipa") and ai.get("ipa"):
                data["ipa"] = str(ai["ipa"]).strip()   # IPA của kho (Wiktionary) đáng tin hơn -> chỉ lấy của AI khi kho không có
            data["lite_source"] = "kho gốc + Flash-Lite" if entry else "Flash-Lite"
    if locked_vi:
        data["definition_vi"] = locked_vi
    tidy_main_fields(data)
    return (True, data)

def get_gemini_data(keyword: str, config: dict, user_context: str = "", forced_definition_vi: str = ""):
    """
    Lấy dữ liệu từ Gemini cho một từ khóa.
    Args:
        forced_definition_vi: Nếu người dùng đã chỉnh sửa nghĩa VN trước đó,
            truyền vào đây để AI bắt buộc dùng đúng nghĩa này khi sinh ví dụ.
    """
    # Field Anki hay dính HTML (<div>, <span style=...>, &nbsp;) và ký tự vô hình khi copy -> làm sạch trước khi gửi AI
    keyword = _INVISIBLE_CHARS_RE.sub("", clean_field_text(keyword)).strip()
    user_context = clean_field_text(user_context)
    forced_definition_vi = clean_field_text(forced_definition_vi)
    language = detect_language(keyword)
    
    # 1. Xử lý Context và POS
    context_section = ""
    pos_section = ""
    other_meaning_instruction = ""
    definition_vi_lock_section = ""
    
    # Kiểm tra bộ nhớ Definition VI nếu không được truyền trực tiếp
    if not forced_definition_vi:
        vi_memory = load_definition_vi_memory()
        forced_definition_vi = vi_memory.get(keyword.lower(), "")
    
    if forced_definition_vi:
        definition_vi_lock_section = f"""
!!! CRITICAL: LOCKED VIETNAMESE DEFINITION !!!
The user has MANUALLY EDITED and APPROVED the Vietnamese meaning for "{keyword}".
You MUST use EXACTLY this Vietnamese definition in ALL fields:
>>> LOCKED definition_vi: "{forced_definition_vi}"

This means:
- "definition_vi" field MUST be exactly: "{forced_definition_vi}"
- All "example_vi", "translation" fields in examples, synonyms, collocations, idioms, etc. MUST be consistent with this meaning.
- Do NOT provide a different Vietnamese meaning. This is non-negotiable.
"""

    # Parse context
    clean_context, requested_pos = parse_context_with_pos(user_context)
        
    # [QUAN TRỌNG] Prompt Context được viết lại để AI bắt buộc phải tuân theo
    if clean_context:
        context_section = f"""
!!! URGENT CONTEXT INSTRUCTION !!!
The user has EXPLICITLY provided the following CONTEXT for the word "{keyword}":
>>> CONTEXT: "{clean_context}"

You MUST interpret the word "{keyword}" STRICTLY WITHIN THIS CONTEXT.
- Ignore common meanings that do not fit this context.
- Examples and definitions MUST relate to "{clean_context}".
- If the context is a specific field (e.g., 'medical'), use terminology from that field.
"""
        
    # Prompt cho POS (Loại từ)
    if requested_pos:
        pos_names = {'noun': 'danh từ', 'verb': 'động từ', 'adjective': 'tính từ', 'adverb': 'trạng từ'}
        pos_name = pos_names.get(requested_pos, requested_pos)
        
        pos_section = f"""
!!! PART OF SPEECH CONSTRAINT !!!
The user specifically requested the word as a **{requested_pos.upper()} ({pos_name})**.
1. Analyze "{keyword}" ONLY as a {requested_pos}.
2. If it has other forms, prioritize the {requested_pos} form completely.
3. "part_of_speech" field MUST be "{requested_pos}".
"""
        other_meaning_instruction = f"""
- Only list meanings where the word functions as a **{requested_pos}**.
"""

    # Tách phần prompt lớn thành các phần nhỏ để dễ quản lý
    radicals_prompt_section = ""
    stroke_count_char_prompt = ""
    has_chinese_char = re.search(r'[\u4e00-\u9fff\u3400-\u4dbf]', keyword)
    
    if language == "Chinese" or has_chinese_char:
        radicals_prompt_section = """
"radicals": [
    {
        "character": "部",
        "name_vi": "tên bộ thủ bằng tiếng Việt",
        "name": "tên bộ thủ gốc",
        "meaning_vi": "ý nghĩa của bộ thủ",
        "meaning": "original meaning",
        "stroke_count": 0,
        "position": "vị trí trong chữ (trái, phải, trên, dưới, giữa, v.v.)",
        "variant": "biến thể nếu có"
    }
],
"components": [
    {
        "component": "thành phần",
        "role": "vai trò (biểu ý, biểu âm, hình thanh, hội ý, v.v.)",
        "pinyin": "pinyin của thành phần",
        "meaning_vi": "ý nghĩa thành phần",
        "explanation": "giải thích chi tiết về vai trò của thành phần"
    }
],
"overall_explanation_vi": "Giải thích tổng quan về cấu tạo chữ và mối quan hệ giữa các bộ thủ.",
"detailed_analysis": "Phân tích chi tiết về cách cấu tạo, nguồn gốc và sự phát triển của chữ.",
"memory_story_vi": "Câu chuyện ghi nhớ giúp liên kết các bộ thủ với ý nghĩa của chữ. Câu chuyện phải sinh động, dễ nhớ và liên quan đến ý nghĩa của chữ.",
"variants": [
    {
        "character": "biến thể",
        "type": "loại biến thể (giản thể, phồn thể, dị thể, v.v.)",
        "meaning": "ý nghĩa nếu khác với chữ gốc"
    }
],
"""
        stroke_count_char_prompt = '"stroke_count_char": [{"character": "", "count": 0}],'

    # Reading prompt (Giữ nguyên)
    reading_prompt_section = ""
    if language == "English":
        reading_prompt_section = '''
    "reading": {
        "title": "A short reading passage related to '{keyword}'",
        "content": "A meaningful short reading passage (100-150 words) that naturally incorporates the word '{keyword}' and related vocabulary. The passage should be engaging and educational for language learners.",
        "translation": "Bản dịch tiếng Việt của bài đọc",
        "questions": [
            {
                "question": "A comprehension question about the passage",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correctAnswer": 0,
                "explanation": "Explanation in English about why this answer is correct"
            },
            {
                "question": "Another comprehension question focusing on vocabulary usage",
                "options": ["Option A", "Option B", "Option C", "Option D"],
                "correctAnswer": 1,
                "explanation": "Explanation in English"
            }
        ]
    },'''

    # Tạo Base Prompt (Đã chèn context_section vào đầu)
    base_prompt = f"""
{context_section}
{pos_section}
{definition_vi_lock_section}
Analyze the word "{keyword}" (language: {language}) for a Vietnamese learner.

**CRITICAL INSTRUCTION FOR PART_OF_SPEECH (ONE ONLY):**
- Choose EXACTLY ONE part of speech: the most common one, or the one required by the user's context/constraint.
- NEVER write "verb/noun" or several parts of speech. Meanings of the word as OTHER parts of speech go into "other_meaning".
- ALL main fields (definition_en, definition_vi, example_en, image_query) describe this ONE part of speech and ONE meaning only.

**CRITICAL INSTRUCTION FOR DEFINITION_EN (CAMBRIDGE DICTIONARY STYLE):**
- Format: "(GUIDEWORD) definition". GUIDEWORD = 1–3 UPPERCASE words naming the meaning, like Cambridge (e.g. dig → "(MOVE SOIL) to break up and move soil using a tool, a machine, or your hands").
- Use only simple, common English words a B1 learner knows. One meaning only. Maximum 20 words.
- Do NOT explain usage, do NOT mention other parts of speech, no visual descriptions.

**CRITICAL INSTRUCTION FOR SPELLING (corrected_spelling / is_misspelled):**
- Inflected forms are CORRECT words, not spelling mistakes: plurals (stakeholders), past tense/participles (allocated, dug), -ing forms, comparatives, capital letters and extra spaces are all fine.
- Set "is_misspelled": true ONLY when "{keyword}" is not a real word form because its letters are wrong (e.g. "ohld" or "hodl" for "hold"); then put the corrected word in "corrected_spelling".
- Otherwise "is_misspelled": false and "corrected_spelling": "" (empty). Never change the user's word form.

**CRITICAL INSTRUCTION FOR IMAGE_QUERY (DETAILED & DEFINITION-BASED):**
- Create a **separate** field called "image_query".
- **GOAL:** Write a highly detailed prompt for AI image generators (Stable Diffusion, Flux, AI Horde).
- **RELATIONSHIP:** The prompt MUST be a visual representation of the specific meaning described in `definition_en`.
- **STRUCTURE:** [Detailed Subject] + [Specific Action/Setting] + [Atmosphere/Lighting] + [Composition] + [Artistic Style] + [Technical Quality Tags].
- **DETAIL LEVEL:** Use descriptive adjectives. Instead of "a dog", use "a fluffy golden retriever puppy playing with a red ball on a sun-drenched green lawn".
- **REQUIRED TAGS:** "hyper-realistic", "8k UHD", "intricate detail", "cinematic composition", "masterpiece", "vivid colors", "professional photography".
- **NEGATIVE:** No text, words, letters, signatures, or watermarks.
- *Example for 'gloomy':* "A lonely, dilapidated wooden house standing in the middle of a foggy, desolate moor under a heavy grey sky, muted colors, cinematic lighting, melancholy atmosphere, hyper-realistic, 8k, highly detailed."


**CRITICAL INSTRUCTION FOR LISTS (Synonyms, Antonyms, Word Family, Collocations, Phrasal Verbs, Idioms):**
- Keep the card light: AT MOST 3 items per list (the most useful ones; fewer or an empty list is fine). Etymology "examples": at most 2.
- YOU MUST provide Vietnamese translations for ALL items in these sections.
- "meaning_vi": The Vietnamese meaning of the word/phrase ITSELF (e.g., "Nhượng lại"). This is NOT a translation of the example sentence.
- "example_vi": The Vietnamese translation of the example sentence (e.g., "Quốc gia buộc phải nhượng lại lãnh thổ").
- Do NOT combine them. Keep them separate.
- EVERY item MUST have both "meaning_vi" AND "example_vi" fields filled.
- For Word Family: Provide Vietnamese meaning for each related word form.
- For Phrasal Verbs: Provide Vietnamese meaning for each phrasal verb phrase.
- For Idioms: Provide Vietnamese meaning for each idiom.
- For Collocations: Provide Vietnamese meaning for each collocation.
- For Synonyms/Antonyms: Provide Vietnamese meaning for each synonym/antonym.

**CRITICAL INSTRUCTION FOR DEFINITION_VI (SHORT EQUIVALENT, NOT A DESCRIPTION):**
- Give the short Vietnamese equivalent(s) of the word in this meaning, like a bilingual dictionary: 1–6 words, separated by commas if needed (e.g. dig → "đào, bới (đất)"; stakeholder → "bên liên quan").
- Do NOT write explanations, full sentences, "Động từ:", "Danh từ:" or several parts of speech.
- Explanations of how/when to use the word go into "recommendation" ("use_context"), NOT here.

Provide a comprehensive breakdown in a strict JSON format.
{other_meaning_instruction}
**CRITICAL INSTRUCTION FOR OTHER_MEANINGS:**
- Meanings of the word as OTHER parts of speech (e.g. dig as a noun: "a remark that criticizes someone") belong HERE, not in the main definition. Start each "meaning" with the part of speech in brackets, e.g. "(noun) lời châm chọc".
- Provide AT MOST 5 other meanings (fewer if the word has fewer distinct meanings). Keep each item short.
- Select the most IMPORTANT, COMMON, and OFFICIALLY RECOGNIZED meanings.
- Order meanings by frequency of usage (most common first).

**SPECIAL INSTRUCTIONS FOR CHINESE CHARACTERS:**
1. For radicals analysis: Identify ALL component radicals that form this character, not just the main radical.
2. For each radical, provide: character, Vietnamese name, meaning, stroke count, and position in the character.
3. For character components: Identify semantic and phonetic components with their roles.
4. Include detailed analysis and memory stories to help with memorization.

**CRITICAL RULE FOR CHINESE:** For any field containing Chinese characters, YOU MUST also provide the corresponding Hanyu Pinyin in parentheses below the characters. This applies to `example_en`, `context_example_en`, `spoken_examples`, `writing_patterns`, and all component/explanation fields. Except for 'word' field.
**EXCEPTION FOR EXERCISES:** In the `exercises` array, DO NOT include Pinyin in the `question` field. Instead, for the `translation_vi` field, first provide the Vietnamese translation, then add a `<br>` tag, and then provide the Pinyin for the original Chinese question, like this: "Translation text<br><i>Pinyin: Nǐ hǎo ma?</i>".

{{
    "is_misspelled": false,
    "corrected_spelling": "Empty string unless is_misspelled is true (see SPELLING rules).",
    "keyword": "If Japanese, return in Hiragana/Katakana. Otherwise, exactly '{keyword}' (keep plural/past forms as given).",
    "ipa": "STRICTLY Pinyin for Chinese (e.g., nǐ hǎo), Romaji for Japanese (e.g., sayōnara), Romaja for Korean (e.g., annyeong), or standard IPA for others. NO PHONETIC SYMBOLS FOR CHINESE.",
    "stroke_count": "Total stroke count for Chinese characters. Return null if not applicable.",
    "part_of_speech": "EXACTLY ONE: noun, verb, adjective, adverb, phrasal verb, idiom, preposition, conjunction, pronoun, determiner, interjection, phrase (or for Chinese: measure word, particle).",
    "image_query": "A highly detailed visual description of the word's meaning for AI image generation (Stable Diffusion/Horde).",
    "definition_en": "(GUIDEWORD) simple Cambridge-style definition of ONE meaning, max 20 easy words.",
    "definition_vi": "Short Vietnamese equivalent(s), 1–6 words, no explanation (e.g. 'đào, bới (đất)').",
    "example_en": "Example sentence in original language using <b>{keyword}</b>. (Follow Pinyin rule if Chinese).",
    "example_vi": "Vietnamese translation of the example.",
    {radicals_prompt_section}
    
    "exercises": [
        {{
            "type": "Word Form (Noun)",
            "question":  "A meaningful fill-in-the-blank sentence with ONLY ONE blank '___' that tests the NOUN form of '{keyword}'. The sentence should make it clear from context that a noun is required. If a noun form doesn't exist, create a general usage question.",
            "answer": "The correct NOUN form of '{keyword}'.",
            "answer_pos": "noun",
            "translation_vi": "Vietnamese translation and if language is Chinese, Pinyin of the question on a new line.",
            "explanation_vi": "Short, easy-to-understand explanation in Vietnamese."
        }},
        {{
            "type": "Word Form (Verb)",
            "question": "A meaningful fill-in-the-blank sentence with ONLY ONE blank '___' that tests the VERB form of '{keyword}'. The sentence should make it clear from context that a verb is required. If a verb form doesn't exist, create another collocation question.",
            "answer": "The correct VERB form'{keyword}'.",
            "answer_pos": "verb",
            "translation_vi": "Vietnamese translation and if language is Chinese, Pinyin of the question on a new line.",
            "explanation_vi": "Short, easy-to-understand explanation in Vietnamese."
        }},
        {{
            "type": "Word Form (Adjective)",
            "question": "A meaningful fill-in-the-blank sentence with ONLY ONE blank '___' that tests the ADJECTIVE form of '{keyword}'. The sentence should make it clear from context that an adjective is required. If an adjective form doesn't exist, create a phrasal verb question.",
            "answer": "The correct ADJECTIVE form'{keyword}'.",
            "answer_pos": "adjective",
            "translation_vi": "Vietnamese translation and if language is Chinese, Pinyin of the question on a new line.",
            "explanation_vi": "Short, easy-to-understand explanation in Vietnamese."
        }},
        {{
            "type": "Word Form (Adverb)",
            "question": "A meaningful fill-in-the-blank sentence with ONLY ONE blank '___' that tests the ADVERB form of '{keyword}'. The sentence should make it clear from context that an adverb is required. If an adverb form doesn't exist, create a general usage question.",
            "answer": "The correct ADVERB form'{keyword}'.",
            "answer_pos": "adverb",
            "translation_vi": "Vietnamese translation and if language is Chinese, Pinyin of the question on a new line.",
            "explanation_vi": "Short, easy-to-understand explanation in Vietnamese."
        }}
    ],
    "usage_patterns": {{
        "spoken_examples": [
            {{ "sentence": "Provide a common, natural sentence for daily conversation.", "translation": "Nghĩa tiếng Việt" }},
            {{ "sentence": "Provide another common sentence.", "translation": "Nghĩa tiếng Việt" }}
        ],
        "writing_patterns": [
            {{ "sentence": "Provide a formal or complex sentence.", "grammar_note": "IN VIETNAMESE: Analysis.", "translation": "Nghĩa tiếng Việt" }},
            {{ "sentence": "Provide another formal sentence.", "grammar_note": "IN VIETNAMESE: Analysis.", "translation": "Nghĩa tiếng Việt" }}
        ]
    }},
    "synonyms": [{{ "word": "synonym", "pos": "pos", "example": "Ex", "meaning_vi": "Short meaning (concise)", "example_vi": "Dịch câu ví dụ" }}],
    "antonyms": [{{ "word": "antonym", "pos": "pos", "example": "Ex", "meaning_vi": "Short meaning (concise)", "example_vi": "Dịch câu ví dụ" }}],
    "word_family": [{{ "word": "related", "pos": "pos", "example": "Ex", "meaning_vi": "Short meaning (concise)", "example_vi": "Dịch câu ví dụ" }}],
    "collocations": [{{ "word": "colloc", "pos": "type", "example": "Ex", "meaning_vi": "Short meaning (concise)", "example_vi": "Dịch câu ví dụ" }}],
    "phrasal_verbs": [{{ "word": "phrasal", "pos": "pv", "example": "Ex", "meaning_vi": "Short meaning (concise)", "example_vi": "Dịch câu ví dụ" }}],
    "idioms": [{{ "word": "idiom", "pos": "idm", "example": "Ex", "meaning_vi": "Short meaning (concise)", "example_vi": "Dịch câu ví dụ" }}],
"""
    # Etymology và Other Meanings (Giữ nguyên phần prompt dài nhưng thêm other_meaning_prompt)
    etymology_prompt = """
    "etymology": {
        "sources": ["Oxford", "Cambridge"],
        "origin": { "period": "Origin", "language": "Lang", "original_form": "Form", "first_attestation": "Date" },
        "structure": {
            "prefix": { "element": "", "meaning": "", "origin": "" },
            "root": { "element": "", "meaning": "", "origin": "" },
            "suffix": { "element": "", "meaning": "", "origin": "" }
        },
        "meaning_development": { "original": "", "evolution": "", "modern": "" },
        "examples": [ { "word": "", "explanation": "Brief explanation", "sentence": "", "translation": "" } ],
        "verification": "Based on sources"
    },"""

    other_meaning_prompt = """
    "other_meaning": [
        {
            "meaning": "Meaning 1", "context_vi": "Context", "example_en": "Ex", "example_vi": "Trans", 
            "usage_note_vi": "Note", "sources": ["Oxford"]
        },
        {
            "meaning": "Meaning 2", "context_vi": "Context", "example_en": "Ex", "example_vi": "Trans", 
            "usage_note_vi": "Note", "sources": ["Oxford"]
        }
        // ... at most 5 meanings
    ],"""

    end_prompt = """
    "grammar_notes": { "classification": "VN", "explanation_vi": "VN" },
    "recommendation": { "use_context": "VN: the fuller explanation of the meaning and when/how to use the word (descriptions go here, not in definition_vi)", "avoid_context": "VN", "context_example_en": "Ex", "context_example_vi": "VN" }
}
"""
    prompt = base_prompt + reading_prompt_section + etymology_prompt + other_meaning_prompt + end_prompt

    provider = config.get("text_provider", "gemini")
    timeout = config.get("timeout", 300)

    if provider == "groq":
        groq_keys = config.get("groq_api_keys", [])
        if isinstance(groq_keys, str):
            groq_keys = [k.strip() for k in groq_keys.replace(',', '\n').split('\n') if k.strip()]
        if groq_keys:
            print(f"[Groq] Dang goi Groq API cho '{keyword}'...")
            try:
                success, result = call_groq_with_key_rotation(prompt, config, timeout)
                if not success:
                    log_error(f"Loi Groq cho '{keyword}': {result}")
                    return (False, result)
                content_text = result
                print(f"[Groq] Received {len(content_text)} chars for '{keyword}'")
            except Exception as e:
                log_error(f"Exception Groq for '{keyword}': {str(e)}")
                return (False, str(e))
        else:
            return (False, "Chua cau hinh Groq API Key. Vao Cai dat de them key.")
    else:
        model = config.get("model", GEMINI_DEFAULT_MODEL)
        print(f"[Gemini] get_gemini_data - model={model}, so key={len(config.get('api_keys') or [])}")
        url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{key}}"
        headers = {"Content-Type": "application/json"}
        # responseMimeType JSON: Gemini trả JSON hợp lệ -> hạn chế lỗi parse.
        # Không gửi responseSchema: với khuôn lớn như thế này Gemini 2.5 Flash hay viết lặp vô tận trong một ô
        # chữ (đã thử: 120-400 nghìn ký tự, JSON hỏng). Format nghĩa được giữ bằng luật trong prompt,
        # tidy_main_fields (chỉ một loại từ) và check_entry_quality (bảng báo cáo).
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                # Trần chi phí: một từ bình thường ~6-9 nghìn token; chặn trường hợp AI viết lặp vô tận
                "maxOutputTokens": 24000,
                # Thấp hơn mặc định (1.0) để bớt lan man/lặp, vẫn đủ đa dạng cho ví dụ
                "temperature": 0.6,
            }
        }
        
        try:
            success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout)
            if not success and "400" in str(result):
                # Một số model không hỗ trợ JSON mode/schema -> thử lại ở chế độ thường
                payload.pop("generationConfig", None)
                success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout)

            if not success:
                log_error(f"Loi Gemini cho '{keyword}': {result}")
                return (False, result)

            response = result
            raw_response = response.json()
            if "candidates" not in raw_response or not raw_response["candidates"]:
                 return (False, "API tra ve phan hoi trong")

            content_text = raw_response["candidates"][0]["content"]["parts"][0]["text"]
        except Exception as e:
            log_error(f"Exception Gemini for '{keyword}': {str(e)}")
            return (False, str(e))

    if not content_text or not content_text.strip():
        log_error(f"Empty content received for '{keyword}' from provider '{provider}'")
        return (False, f"Nhan duoc phan hoi trong tu {provider}. Kiem tra lai Key hoac Model.")

    print(f"[Content Debug] len={len(content_text)}, first 100 chars: {repr(content_text[:100])}")

    try:
        data, methods_used = safe_json_parse(content_text, keyword)
        print(f"JSON parsed successfully for '{keyword}' (provider: {provider})")
    except json.JSONDecodeError as e:
        return (False, f"JSON parse failed: {e}")
    
    # Chỉ báo sai chính tả khi từ bị viết sai mặt chữ (ohld -> hold); khác viết hoa, khoảng trắng,
    # ký tự vô hình, số nhiều/quá khứ... đều không tính
    corrected_spelling = str(data.get("corrected_spelling") or "").strip()
    ai_flag = data.get("is_misspelled")
    if isinstance(ai_flag, str):
        ai_flag = ai_flag.strip().lower() == "true"
    if corrected_spelling and is_real_spelling_error(keyword, corrected_spelling, ai_flag):
        return ("spelling_correction", corrected_spelling)

    # Giữ nguyên đúng từ người dùng nhập (stakeholders, allocated...); tiếng Nhật thì dùng dạng kana AI trả về
    if language != "Japanese" or not str(data.get("keyword") or "").strip():
        data["keyword"] = keyword
    tidy_main_fields(data)
    data["language"] = language
    return (True, data)
# ========== HÀM XỬ LÝ JSON DỰ PHÒNG ==========
def clean_json_string(json_str):
    """Làm sạch chuỗi JSON để tránh lỗi parsing"""
    # Loại bỏ các ký tự control không hợp lệ nhưng giữ lại \n, \t hợp lệ
    cleaned = re.sub(r'[\x00-\x09\x0b-\x0c\x0e-\x1f\x7f-\x9f]', '', json_str)
    # Sửa lỗi dấu ngoặc kép không khớp
    cleaned = re.sub(r'(?<!\\)"(?=\s*:)', '"', cleaned)  # Đảm bảo dấu " trước :
    cleaned = re.sub(r'(?<=:)\s*"(?![^"]*"[^"]*$)', '"', cleaned)  # Đảm bảo dấu " sau :
    return cleaned

def safe_json_parse(content_text, keyword):
    """Phân tích JSON an toàn với nhiều phương pháp dự phòng"""
    methods = []
    
    # Phương pháp 1: Regex tìm JSON object
    try:
        json_match = re.search(r"\{[^{}]*\{.*\}[^{}]*\}|\{.*\}", content_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            data = json.loads(json_str)
            methods.append("regex_object")
            return data, methods
    except Exception as e:
        print(f"❌ Phương pháp 1 thất bại: {e}")
        pass
    
    # Phương pháp 2: Parse toàn bộ content
    try:
        data = json.loads(content_text)
        methods.append("full_content")
        return data, methods
    except Exception as e:
        print(f"❌ Phương pháp 2 thất bại: {e}")
        pass
    
    # Phương pháp 3: Tìm JSON trong code blocks
    try:
        if "```json" in content_text:
            json_str = content_text.split("```json")[1].split("```")[0].strip()
        elif "```" in content_text:
            json_str = content_text.split("```")[1].split("```")[0].strip()
        else:
            json_str = content_text
            
        data = json.loads(json_str)
        methods.append("code_blocks")
        return data, methods
    except Exception as e:
        print(f"❌ Phương pháp 3 thất bại: {e}")
        pass
    
    # Phương pháp 4: Làm sạch và thử lại
    try:
        # Làm sạch JSON string
        json_match = re.search(r"\{.*\}", content_text, re.DOTALL)
        if json_match:
            json_str = clean_json_string(json_match.group(0))
            data = json.loads(json_str)
            methods.append("cleaned_json")
            return data, methods
    except Exception as e:
        print(f"❌ Phương pháp 4 thất bại: {e}")
        pass
    
    # Phương pháp 5: Sửa lỗi Unicode và thử lại
    try:
        json_match = re.search(r"\{.*\}", content_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            # Sửa lỗi Unicode escape sequences
            json_str = json_str.encode('utf-8').decode('unicode-escape')
            data = json.loads(json_str)
            methods.append("unicode_fixed")
            return data, methods
    except Exception as e:
        print(f"❌ Phương pháp 5 thất bại: {e}")
        pass
    
    # Nếu tất cả đều thất bại
    raise json.JSONDecodeError(f"Không thể parse JSON cho từ '{keyword}'", content_text, 0)
 
def call_gemini_for_vocabulary_analysis(keyword: str, reading_text: str, config: dict):
    """Gọi Gemini API để phân tích bài đọc và tạo từ vựng (Đã update Key Rotation)"""
    print(f"🔍 Gọi Gemini với từ khóa: '{keyword}'")
    print(f"📖 Độ dài bài đọc: {len(reading_text)}")    
    
    prompt = f"""
BẠN LÀ TRỢ LÝ GIÁO VIÊN NGÔN NGỮ CHUYÊN NGHIỆP. HÃY PHÂN TÍCH ĐOẠN VĂN SAU VÀ TRÍCH XUẤT:

1. Đúng 5 từ/cụm từ đáng học nhất có trong bài (ưu tiên cụm từ, collocation, nhất là cụm chứa hoặc đi với từ khóa; sau đó mới đến từ đơn khó)
2. Đúng 2 cấu trúc câu đáng chú ý trong bài

TỪ KHÓA CHÍNH: "{keyword}"
Bài đọc:
{reading_text}

YÊU CẦU:
- Sắp xếp từ vựng theo mức độ quan trọng và tần suất xuất hiện
- Với mỗi từ vựng: từ gốc, loại từ, phiên âm, nghĩa tiếng Việt, ví dụ từ bài đọc
- Với mỗi cấu trúc: cấu trúc, giải thích cách dùng dựa theo bài đọc, ví dụ từ bài đọc
- Ưu tiên từ và cấu trúc có liên quan đến từ khóa "{keyword}"
- Tất cả giải thích bằng tiếng Việt
- Tham khảo ở các trang từ điển uy tín nếu cần 

Định dạng JSON:
{{
    "vocabulary": [
        {{
            "word": "từ vựng",
            "base_form": "dạng gốc",
            "pos": "loại từ",
            "pronunciation": "phiên âm",
            "meaning_vi": "nghĩa tiếng Việt",
            "example_from_reading": "ví dụ từ bài đọc",
            "translation": "bản dịch ví dụ"
        }}
    ],
    "structures": [
        {{
            "structure": "cấu trúc câu",
            "explanation_vi": "giải thích cách dùng",
            "example_from_reading": "ví dụ từ bài đọc", 
            "translation": "bản dịch ví dụ"
        }}
    ]
}}

Chỉ tra ve JSON, khong co text nao khac.
""" 
    provider = config.get("text_provider", "gemini")
    timeout = config.get("timeout", 300)
    
    if provider == "groq":
        groq_keys = config.get("groq_api_keys", [])
        if isinstance(groq_keys, str):
            groq_keys = [k.strip() for k in groq_keys.replace(',', '\n').split('\n') if k.strip()]
        if groq_keys:
            print(f"[Groq] Vocab analysis for '{keyword}'...")
            try:
                success, result = call_groq_with_key_rotation(prompt, config, timeout)
                if not success:
                    return (False, f"Loi Groq: {result}")
                content_text = result
                print(f"Nhan Groq response: {len(content_text)} ky tu")
            except Exception as e:
                return (False, f"Loi ket noi Groq: {e}")
        else:
            return (False, "Chua cau hinh Groq API Key.")
    else:
        model = config.get("model", GEMINI_DEFAULT_MODEL)
        url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        
        print(f"Gui request toi Gemini (Model: {model})...")
        
        try:
            success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout)
            
            if success:
                response = result
                print(f"Response status: {response.status_code}")
                
                prompt_tokens = estimate_tokens(prompt)
                raw_response = response.json()
                
                if "candidates" not in raw_response or not raw_response["candidates"]:
                    return (False, "API tra ve phan hoi trong (khong co candidates)")

                content_text = raw_response["candidates"][0]["content"]["parts"][0]["text"]
                response_tokens = estimate_tokens(content_text)
                update_token_usage(prompt_tokens, response_tokens)
                
                print(f"Nhan duoc response tu Gemini: {len(content_text)} ky tu")
            else:
                print(f"Loi API: {result}")
                return (False, f"Loi API: {result}")
        except Exception as e:
            print(f"Loi ket noi den Gemini: {str(e)}")
            return (False, f"Loi ket noi den Gemini: {str(e)}")
    json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        print(f"Da trich xuat JSON: {len(json_str)} ky tu")
        try:
            analysis_data = json.loads(json_str)
            print("Phan tich JSON thanh cong")
            return (True, analysis_data)
        except json.JSONDecodeError as e:
            return (False, f"Loi parse JSON: {e}")
    else:
        print("Khong tim thay JSON trong response")
        return (False, "Khong tim thay du lieu JSON trong phan hoi")

# ========== LƯU TỪ VỰNG BÀI ĐỌC (ĐỊNH DẠNG GỌN CHO TAB ÁP DỤNG) ==========
READING_VOCAB_MAX_WORDS = 5
READING_VOCAB_MAX_STRUCTURES = 2

def build_reading_vocab_data(result):
    """Chuẩn hoá kết quả AI (nhiều kiểu tên khoá khác nhau) về JSON gọn mà tab Áp dụng hiển thị:
    tối đa 5 từ/cụm + 2 cấu trúc, mỗi mục một dòng, bấm vào mới mở ví dụ."""
    def text(item, *names):
        for name in names:
            if item.get(name):
                return str(item[name])
        return ""
    vocabulary = [{
        "term": text(v, "term", "base_form", "word"),
        "in_text": text(v, "in_text", "word"),
        "pos": text(v, "pos"),
        "meaning_vi": text(v, "meaning_vi"),
        "example": text(v, "example", "example_from_reading"),
        "example_vi": text(v, "example_vi", "translation"),
    } for v in (result.get("vocabulary") or []) if isinstance(v, dict)]
    structures = [{
        "pattern": text(s, "pattern", "structure"),
        "in_text": text(s, "in_text"),
        "explain_vi": text(s, "explain_vi", "explanation_vi"),
        "example": text(s, "example", "example_from_reading"),
        "example_vi": text(s, "example_vi", "translation"),
    } for s in (result.get("structures") or []) if isinstance(s, dict)]
    return {
        "v": 1,
        "at": int(time.time() * 1000),
        "vocabulary": vocabulary[:READING_VOCAB_MAX_WORDS],
        "structures": structures[:READING_VOCAB_MAX_STRUCTURES],
    }

def set_reading_vocab_fields(note, result):
    """Ghi từ vựng bài đọc vào Reading_Vocabulary (JSON, escape để nằm an toàn trong HTML của thẻ).
    Cấu trúc nằm chung trong JSON nên Reading_Structures để trống (tránh hiện bản HTML cũ)."""
    import html
    data = result if result.get("v") == 1 else build_reading_vocab_data(result)
    if "Reading_Vocabulary" in note:
        note["Reading_Vocabulary"] = html.escape(json.dumps(data, ensure_ascii=False), quote=False)
    if "Reading_Structures" in note:
        note["Reading_Structures"] = ""

def strip_em_dashes(value):
    """Đổi dấu gạch dài (AI và Wiktionary hay dùng) sang dấu phẩy trong mọi chuỗi của dữ liệu thẻ."""
    if isinstance(value, str):
        return re.sub(r"\s*—\s*", ", ", value).strip(", ") if "—" in value else value
    if isinstance(value, list):
        return [strip_em_dashes(v) for v in value]
    if isinstance(value, dict):
        return {k: strip_em_dashes(v) for k, v in value.items()}
    return value

def fill_note_with_data(note, data):
    data.update(strip_em_dashes(data))   # sửa tại chỗ để bảng báo cáo dùng lại data cũng sạch
    # [BẢO VỆ] Lưu lại giá trị Context người dùng đã nhập TRƯỚC KHI điền dữ liệu.
    # Trường này do người dùng quản lý, AI không được phép ghi đè.
    user_context_backup = ""
    if "Context" in note:
        user_context_backup = (note["Context"] or "").strip()

    # Điền các trường dữ liệu thông thường (bao gồm cả Reading)
    for field_anki, field_json in FIELD_MAP.items():
        if field_anki in note and field_json in data:
            field_data = data[field_json]
            if isinstance(field_data, (list, dict)):
                note[field_anki] = json.dumps(field_data, ensure_ascii=False) if field_data else ""
            else:
                note[field_anki] = str(field_data)

    # [BẢO VỆ] Khôi phục Context gốc của người dùng sau khi vòng lặp chạy xong.
    if "Context" in note:
        note["Context"] = user_context_backup

    user_context = user_context_backup
    
    if "image_query" in data and data["image_query"]:
        image_content = data["image_query"]
        
        # Kiểm tra xem đã có trường ImageQuery/Image Querry chưa. Nếu có rồi thì không điền text vào trường Image nữa.
        has_query_field = any(f in note for f in ["ImageQuery", "Image Querry", "Image_Query"])
        
        if not has_query_field:
            # Danh sách các tên trường ảnh phổ biến có thể người dùng đang dùng
            possible_image_fields = ["Image", "Picture", "Hình ảnh", "Minh họa", "Drawing", "Illustration", "Img"]
            
            # Kiểm tra xem ảnh đã được điền ở bước 1 chưa (nếu trường Image có trong note)
            is_filled = False
            if "Image" in note and "Image" in FIELD_MAP and FIELD_MAP["Image"] == "image_query":
                 if note["Image"]: is_filled = True
            
            # Nếu chưa điền được, thử tìm các trường khác
            if not is_filled:
                for field in possible_image_fields:
                    if field in note:
                        note[field] = image_content
                        print(f"📸 Đã điền prompt vào trường: {field}")
                        break
    # XỬ LÝ ĐẶC BIỆT CHO MEMORY STORY - THÊM VÀO RADICALS
    if "Radicals" in note and "memory_story_vi" in data and data["memory_story_vi"]:
        memory_content = data["memory_story_vi"]
        
        # Kiểm tra xem Radicals hiện tại có dữ liệu không
        current_radicals = (note["Radicals"] or "").strip()
        
        try:
            if current_radicals and current_radicals not in ["", "[]", "{}"]:
                radicals_list = json.loads(current_radicals)
                
                # Đảm bảo radicals_list là list
                if not isinstance(radicals_list, list):
                    radicals_list = []
                
                # Kiểm tra xem đã có memory story chưa
                has_memory_story = any(
                    isinstance(item, dict) and item.get("type") == "memory_story" 
                    for item in radicals_list
                )
                
                if not has_memory_story:
                    # Thêm memory story như một item mới
                    memory_item = {
                        "type": "memory_story", 
                        "content": memory_content
                    }
                    radicals_list.append(memory_item)
                    note["Radicals"] = json.dumps(radicals_list, ensure_ascii=False)
            else:
                # Nếu Radicals trống, tạo mới với memory story
                note["Radicals"] = json.dumps([{
                    "type": "memory_story", 
                    "content": memory_content
                }], ensure_ascii=False)
                
        except (json.JSONDecodeError, TypeError) as e:
            # Nếu parse JSON lỗi, tạo radicals mới với memory story
            print(f"Lỗi parse radicals: {e}")
            note["Radicals"] = json.dumps([{
                "type": "memory_story", 
                "content": memory_content
            }], ensure_ascii=False)

# ========== [HÀM MỚI] GIÚP TÌM TRƯỜNG DỮ LIỆU LINH HOẠT ==========
def persist_editor_note(editor, note):
    """Lưu note đã được điền và làm mới editor.
    - Thẻ đã có trong collection (Browser/Edit): lưu ngay, kể cả khi người dùng đã chuyển
      sang thẻ khác trong lúc chờ AI (trước đây dữ liệu sẽ bị mất).
    - Chỉ loadNote() khi editor vẫn đang hiển thị đúng note này."""
    if getattr(note, "id", 0):
        mw.col.update_note(note)
    if editor is not None and editor.note is note:
        editor.loadNote()

def get_note_field_value(note, possible_names):
    """
    Tìm giá trị trong note dựa trên danh sách tên trường có thể có.
    Không phân biệt hoa thường (ví dụ: 'Context' hay 'context' đều nhận).
    """
    if not note: return ""
    
    # Tạo map từ tên thường sang tên thật trong note
    # Ví dụ: {'context': 'Context', 'word': 'Word'}
    field_map = {k.lower(): k for k in note.keys()}
    
    for name in possible_names:
        name_lower = name.lower()
        if name_lower in field_map:
            real_name = field_map[name_lower]
            val = note[real_name]
            # Chỉ trả về nếu có dữ liệu thực sự (không phải chuỗi rỗng)
            if val and val.strip():
                return val.strip()
    return ""

# ========== CẬP NHẬT HÀM CHẠY EDITOR (FIX LỖI KHÔNG NHẬN CONTEXT) ==========
# ========== CẬP NHẬT HÀM CHẠY EDITOR (TỐI ƯU CHO POLLINATIONS AI) ==========
# ========== DIALOG RETRY ẢNH KHI THẤT BẠI ==========
class ImageRetryDialog(QDialog):
    """
    Hiện khi engine tạo ảnh bị lỗi.
    Engine lỗi = nút cha (đỏ), các engine còn lại = nút con để chọn thử lại.
    """
    ENGINE_INFO = {
        "pollinations":  ("🚀 Pollinations (Flux)",  "Nhanh, cần Pollen key"),
        "horde":         ("🆓 AI Horde",              "Miễn phí hoàn toàn, chậm ~60s"),
        "hf":            ("🤗 Hugging Face",           "Free tier, hay bị giới hạn"),
        "google_search": ("🔍 Google Search",          "Cần CSE Key"),
        "google":        ("🎨 Google Imagen",          "Cần Paid API Key"),
    }

    def __init__(self, parent, failed_engine: str, error_msg: str = ""):
        super().__init__(parent)
        self.setWindowTitle("❌ Tạo ảnh thất bại")
        self.setMinimumWidth(400)
        self.selected_engine = None

        layout = QVBoxLayout(self)

        # --- Header lỗi ---
        engine_label, _ = self.ENGINE_INFO.get(failed_engine, (failed_engine, ""))
        err_title = QLabel(f"<b>❌ Tạo ảnh thất bại với: {engine_label}</b>")
        err_title.setStyleSheet("color: #c0392b; font-size: 13px; margin-bottom: 4px;")
        layout.addWidget(err_title)

        if error_msg:
            err_detail = QLabel(f"<i>Chi tiết: {error_msg[:120]}</i>")
            err_detail.setStyleSheet("color: #888; font-size: 11px;")
            err_detail.setWordWrap(True)
            layout.addWidget(err_detail)

        hint = QLabel("👇 Chọn engine khác để thử lại ngay:")
        hint.setStyleSheet("margin-top: 10px; font-size: 12px; color: #2c3e50;")
        layout.addWidget(hint)

        # --- Tree widget ---
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIndentation(24)
        self.tree.setStyleSheet("""
            QTreeWidget { border: 1px solid #ddd; border-radius: 6px; padding: 4px; }
            QTreeWidget::item { padding: 6px 4px; font-size: 12px; }
            QTreeWidget::item:hover { background: #eaf4ff; }
            QTreeWidget::item:selected { background: #3498db; color: white; }
        """)

        # Nút cha = engine đang lỗi
        parent_label, parent_hint = self.ENGINE_INFO.get(
            failed_engine, (failed_engine, "")
        )
        parent_item = QTreeWidgetItem([f"{parent_label}  ← đang lỗi"])
        parent_item.setForeground(0, Qt.GlobalColor.red)

        # Nút con = các engine còn lại
        for key, (label, hint_text) in self.ENGINE_INFO.items():
            if key != failed_engine:
                child = QTreeWidgetItem([f"{label}  ({hint_text})"])
                child.setData(0, Qt.ItemDataRole.UserRole, key)
                parent_item.addChild(child)

        self.tree.addTopLevelItem(parent_item)
        self.tree.expandAll()
        self.tree.itemClicked.connect(self._on_item_clicked)
        layout.addWidget(self.tree)

        # --- Nút bỏ qua ---
        btn_row = QHBoxLayout()
        skip_btn = QPushButton("Bỏ qua")
        skip_btn.setStyleSheet("padding: 6px 20px; color: #555;")
        skip_btn.clicked.connect(self.reject)
        btn_row.addStretch()
        btn_row.addWidget(skip_btn)
        layout.addLayout(btn_row)

    def _on_item_clicked(self, item, _col):
        engine = item.data(0, Qt.ItemDataRole.UserRole)
        if engine:  # chỉ nút con mới có data
            self.selected_engine = engine
            self.accept()


def run_gemini_fill_for_editor(editor: Editor):
    """
    Hàm xử lý chính khi bấm nút Gemini Fill (✨):
    1. Lấy dữ liệu Text bằng get_gemini_data
    2. Điền vào Note
    3. Tạo ảnh: Dùng image_prompt + Context + Nghĩa Tiếng Việt
    """
    # 1. Kiểm tra đầu vào
    note = editor.note
    if not note: return

    # Lấy Word (bỏ HTML mà editor chèn vào, vd: <div>word</div>, &nbsp;)
    word = clean_field_text(get_note_field_value(note, ["Word", "Từ vựng", "Keyword", "Thuật ngữ", "Expression"]))
    if not word:
        tooltip("⚠️ Vui lòng nhập từ vựng vào trường 'Word'!")
        return

    config = load_config()

    # Tự động tìm Context người dùng nhập (nếu có)
    context_fields = ["Context", "Ngữ cảnh", "Topic", "Chủ đề", "Situation", "Tình huống", "Context/Topic"]
    user_context = clean_field_text(get_note_field_value(note, context_fields))
    
    msg_context = f" (Context: {user_context[:15]}...)" if user_context else ""
    tooltip(f"⚡ Gemini đang phân tích: {word}{msg_context}...")

    # -------------------------------------------------------
    # A. ĐỊNH NGHĨA WORKER ẢNH (Logic vẽ tối ưu)
    # -------------------------------------------------------
    def image_worker(prompt_for_image):
        try:
            keyword_for_filename = word 
            failed_engine = config.get("image_engine_priority", "auto")

            # Kiểm tra prompt
            if not prompt_for_image:
                print(f"⚠️ Không tìm thấy prompt ảnh cho '{word}'.")
                return (None, failed_engine)
            
            # --- [LOGIC MỚI] XÂY DỰNG CONTEXT VẼ ẢNH CHI TIẾT ---
            current_context = user_context
            if not current_context:
                current_context = get_note_field_value(note, ["Example", "Ví dụ", "Sentence"])
            def_vi = get_note_field_value(note, ["Definition_VI", "Definition", "Định nghĩa", "Nghĩa", "Vietnamese Meaning"])
            context_for_drawing_parts = []
            if current_context:
                context_for_drawing_parts.append(f"Context: {current_context}")
            if def_vi:
                context_for_drawing_parts.append(f"Meaning: {def_vi}")
            final_img_context = ". ".join(context_for_drawing_parts)
            
            pos_to_use = get_note_field_value(note, ["POS", "Type", "Loại từ", "Part of speech"])
            print(f"🎨 Auto Image: Prompt='{prompt_for_image[:30]}...', Context='{final_img_context[:30]}...'")

            if 'handle_image_generation_and_save' in globals():
                try:
                    result = handle_image_generation_and_save(
                        keyword=keyword_for_filename,
                        config=config, 
                        definition_en=prompt_for_image,
                        context=final_img_context,
                        pos_type=pos_to_use
                    )
                except TypeError:
                    result = handle_image_generation_and_save(prompt_for_image, config)
                return (result, failed_engine)
            return (None, failed_engine)
        except Exception as e:
            print(f"❌ Lỗi image_worker: {e}")
            return (None, config.get("image_engine_priority", "auto"))

    def _save_img_to_note(img_tag):
        """Điền img_tag vào trường ảnh trong note, trả về True nếu thành công."""
        target_fields = ["Image", "Picture", "Hình ảnh", "Minh họa", "Drawing"]
        field_map = {k.lower(): k for k in note.keys()}
        for tf in target_fields:
            if tf.lower() in field_map:
                note[field_map[tf.lower()]] = img_tag
                persist_editor_note(editor, note)
                return True
        return False

    def on_image_received(future):
        """Callback xử lý khi ảnh đã được tạo xong, hiện dialog retry nếu thất bại."""
        try:
            img_tag, failed_engine = future.result()
            if img_tag:
                if _save_img_to_note(img_tag):
                    tooltip("✅ Hoàn tất: Đã điền chữ & Thêm ảnh minh họa!")
                else:
                    from aqt.qt import QApplication
                    QApplication.clipboard().setText(img_tag)
                    tooltip("✅ Đã tạo ảnh (Copy vào Clipboard)")
            else:
                # --- Hiện dialog retry ---
                dlg = ImageRetryDialog(mw, failed_engine or "auto")
                if dlg.exec() and dlg.selected_engine:
                    chosen = dlg.selected_engine
                    tooltip(f"🔄 Đang thử lại với {chosen}...")
                    retry_config = dict(config)
                    retry_config["image_engine_priority"] = chosen
                    image_prompt_ref = getattr(on_image_received, "_last_prompt", "")

                    def retry_worker():
                        if 'handle_image_generation_and_save' in globals():
                            try:
                                r = handle_image_generation_and_save(
                                    keyword=word,
                                    config=retry_config,
                                    definition_en=image_prompt_ref,
                                    pos_type=get_note_field_value(note, ["POS", "Type", "Loại từ", "Part of speech"])
                                )
                            except TypeError:
                                r = handle_image_generation_and_save(image_prompt_ref, retry_config)
                            return (r, chosen)
                        return (None, chosen)

                    def on_retry_done(f2):
                        try:
                            img2, _ = f2.result()
                            if img2:
                                if _save_img_to_note(img2):
                                    tooltip(f"✅ Tạo ảnh thành công với {chosen}!")
                                else:
                                    from aqt.qt import QApplication
                                    QApplication.clipboard().setText(img2)
                                    tooltip("✅ Đã tạo ảnh (Copy vào Clipboard)")
                            else:
                                tooltip(f"❌ {chosen} cũng thất bại. Thử engine khác trong Settings.")
                        except Exception: pass

                    mw.taskman.run_in_background(retry_worker, on_retry_done)
        except Exception as e:
            print(f"❌ on_image_received error: {e}")

    # -------------------------------------------------------
    # B. ĐỊNH NGHĨA WORKER TEXT
    # -------------------------------------------------------
    def text_worker():
        if 'get_gemini_data' in globals():
            return get_gemini_data(word, config, user_context)
        else:
            return (False, "Lỗi Code: Không tìm thấy hàm get_gemini_data")

    def on_text_received(future):
        try:
            result = future.result()
            if isinstance(result, tuple) and len(result) == 2:
                status, data = result
                
                if status == "spelling_correction":
                    showCritical(f"⚠️ Từ '{word}' có thể sai chính tả.\nGợi ý: {data}")
                    return
                
                if status == True and isinstance(data, dict):
                    # --- LOGIC GHI ĐÈ / LƯU BỘ NHỚ IPA ---
                    ipa_memory = load_ipa_memory()
                    word_lower = word.lower()
                    existing_ipa = get_note_field_value(note, ["IPA", "Phonetic", "Phiên âm"])
                    
                    if existing_ipa:
                        # Nếu người dùng đã tự gõ IPA sẵn ở thẻ -> Lưu vào bộ nhớ và bắt AI dùng nó
                        save_ipa_memory(word_lower, existing_ipa)
                        data['ipa'] = existing_ipa
                        data['IPA'] = existing_ipa
                    elif word_lower in ipa_memory:
                        # Nếu từ này đã từng được sửa IPA trong quá khứ -> Lấy ra ghi đè AI
                        data['ipa'] = ipa_memory[word_lower]
                        data['IPA'] = ipa_memory[word_lower]

                    # --- [MỚI] LOGIC GHI ĐÈ / LƯU BỘ NHỚ DEFINITION VI ---
                    vi_memory = load_definition_vi_memory()
                    existing_def_vi = get_note_field_value(note, ["Definition_VI", "Định nghĩa VN", "Nghĩa", "Vietnamese Meaning"])
                    
                    if existing_def_vi:
                        # Người dùng đã gõ/sửa nghĩa VN sẵn ở thẻ -> Lưu vào bộ nhớ và bắt AI dùng nó
                        save_definition_vi_memory(word_lower, existing_def_vi)
                        data['definition_vi'] = existing_def_vi
                        data['Definition_VI'] = existing_def_vi
                        print(f"🔒 [Editor] Ghi đè Definition VI bằng nghĩa người dùng đã chỉnh sửa: '{existing_def_vi[:40]}'")
                    elif word_lower in vi_memory:
                        # Từ này đã từng được sửa nghĩa VN trong quá khứ -> Lấy ra ghi đè AI
                        data['definition_vi'] = vi_memory[word_lower]
                        data['Definition_VI'] = vi_memory[word_lower]
                        print(f"🔒 [Editor] Khôi phục Definition VI từ bộ nhớ: '{vi_memory[word_lower][:40]}'")

                    fill_note_with_data(note, data)
                    persist_editor_note(editor, note)

                    success_msg = "✅ Đã điền thông tin!"
                    
                    # TRIGGER TẠO ẢNH SAU KHI CÓ TEXT
                    if config.get("auto_image_gen", True):
                        # Lấy image_query từ kết quả trả về
                        image_prompt = data.get("image_query", data.get("definition_en", ""))
                        # Lưu prompt để on_image_received dùng khi retry
                        on_image_received._last_prompt = image_prompt
                            
                        tooltip(f"{success_msg} 🎨 Đang vẽ minh họa...")
                        mw.taskman.run_in_background(lambda: image_worker(image_prompt), on_image_received)
                    else:
                        tooltip(success_msg)
                else:
                    showCritical(f"Lỗi Gemini: {data}")
            else:
                showCritical("Lỗi định dạng dữ liệu trả về.")
        except Exception as e:
            showCritical(f"Lỗi xử lý Text: {e}")

    mw.taskman.run_in_background(text_worker, on_text_received)
class BatchAddDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Thêm hàng loạt từ Gemini")
        self.layout = QVBoxLayout(self)
        self.instructions = QLabel("Dán danh sách từ vựng vào đây (mỗi từ một dòng):")
        self.text_area = QPlainTextEdit()
        self.layout.addWidget(self.instructions)
        self.layout.addWidget(self.text_area)
        self.button_layout = QHBoxLayout()
        self.deck_chooser_label = QLabel("Chọn bộ thẻ để thêm vào:")
        self.deck_chooser = QComboBox()
        self.refresh_deck_list()
        self.new_deck_button = QPushButton("Tạo bộ thẻ mới")
        self.start_button = QPushButton("Bắt đầu tạo thẻ")
        self.start_button.setDefault(True)
        self.layout.addWidget(self.deck_chooser_label)
        self.layout.addWidget(self.deck_chooser)
        self.layout.addLayout(self.button_layout)
        self.button_layout.addWidget(self.new_deck_button)
        self.button_layout.addWidget(self.start_button)
        self.new_deck_button.clicked.connect(self.on_create_new_deck)
        self.start_button.clicked.connect(self.on_start)
        self.resize(500, 600)
    
    def refresh_deck_list(self):
        self.deck_chooser.clear()
        all_decks = sorted(mw.col.decks.all_names())
        self.deck_chooser.addItems(all_decks)
        current_deck_name = mw.col.decks.current()['name']
        self.deck_chooser.setCurrentText(current_deck_name)
    
    def on_create_new_deck(self):
        new_deck_name, ok = QInputDialog.getText(self, "Tạo bộ thẻ mới", "Nhập tên bộ thẻ mới:")
        if ok and new_deck_name: 
            mw.col.decks.id(new_deck_name)
            self.refresh_deck_list()
            self.deck_chooser.setCurrentText(new_deck_name)
    
    def on_start(self): 
        self.words_text = self.text_area.toPlainText()
        self.selected_deck = self.deck_chooser.currentText()
        self.accept()

def show_context_usage_guide():
    """Hiển thị hướng dẫn sử dụng Context"""
    guide_text = """
🎯 <strong>CÁCH SỬ DỤNG CONTEXT NÂNG CAO</strong>

<strong>1. NGỮ CẢNH THÔNG THƯỜNG:</strong>
• business meeting
• medical terminology  
• academic writing

<strong>2. CHỦ ĐỀ TỰ ĐỘNG:</strong>
• technology → tự mở rộng: công nghệ, máy tính, phần mềm
• medical → tự mở rộng: y tế, bệnh viện, sức khỏe
• education → tự mở rộng: học tập, giáo dục, trường học

<strong>3. LOẠI TỪ CỤ THỂ:</strong>
• run [verb] → chỉ phân tích nghĩa động từ của "run"
• light [noun] → chỉ phân tích nghĩa danh từ của "light"  
• fast [adj] → chỉ phân tích nghĩa tính từ của "fast"
• quickly [adv] → chỉ phân tích nghĩa trạng từ của "quickly"

<strong>4. KẾT HỢP:</strong>
• business meeting [noun] → ngữ cảnh + loại từ
• run a business [verb] → cụm từ + loại từ

<strong>CÚ PHÁP LOẠI TỪ:</strong>
• Từ [noun] hoặc Từ (noun)
• Từ [verb] hoặc Từ (verb) 
• Từ [adj] hoặc Từ (adj)
• Từ [adv] hoặc Từ (adv)

<strong>VIẾT TẮT:</strong>
• n hoặc noun → danh từ
• v hoặc verb → động từ
• adj hoặc adjective → tính từ
• adv hoặc adverb → trạng từ

<strong>VÍ DỤ THỰC TẾ:</strong>
1. "apple [noun]" → chỉ lấy nghĩa danh từ (quả táo)
2. "light [adj]" → chỉ lấy nghĩa tính từ (nhẹ, sáng)
3. "run business [verb]" → phân tích "run" như động từ trong ngữ cảnh kinh doanh
4. "fast technology" → phân tích "fast" trong ngữ cảnh công nghệ
"""
    
    dialog = QDialog(mw)
    dialog.setWindowTitle("📚 Hướng dẫn sử dụng Context")
    dialog.resize(500, 600)
    
    layout = QVBoxLayout()
    
    # Scroll area cho nội dung dài
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    
    content_widget = QWidget()
    content_layout = QVBoxLayout(content_widget)
    
    text_label = QLabel(guide_text)
    text_label.setWordWrap(True)
    text_label.setTextFormat(Qt.TextFormat.RichText)
    text_label.setStyleSheet("font-size: 13px; line-height: 1.4; padding: 15px;")
    
    content_layout.addWidget(text_label)
    scroll_area.setWidget(content_widget)
    layout.addWidget(scroll_area)
    
    # Nút đóng
    close_btn = QPushButton("Đóng")
    close_btn.clicked.connect(dialog.close)
    layout.addWidget(close_btn)
    
    dialog.setLayout(layout)
    dialog.exec()
# ========== SETTINGS DIALOG (CẬP NHẬT) ==========
class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("⚙️ Cài đặt Gemini (Hỗ trợ Nhiều Key)")
        self.resize(600, 700)  # Giảm chiều cao xuống 700px
        self.config = load_config()

        # Tạo layout chính
        main_layout = QVBoxLayout(self)
        
        # Tạo scroll area
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        
        # Tạo widget nội dung
        content_widget = QWidget()
        content_layout = QVBoxLayout(content_widget)  # Đây là content_layout
        content_layout.setContentsMargins(10, 10, 10, 10)
        
        # THÊM PHẦN HƯỚNG DẪN SỬ DỤNG CONTEXT VỚI LOẠI TỪ
        context_group = QGroupBox("📝 Hướng dẫn sử dụng Context với Loại từ")
        context_layout = QVBoxLayout()
        
        context_help_text = QTextEdit()
        context_help_text.setReadOnly(True)
        context_help_text.setHtml("""
<h4 style="color: #2c3e50; margin-bottom: 10px;">Cách sử dụng Context nâng cao:</h4>
<ol style="margin-left: 20px; padding-left: 0;">
  <li style="margin-bottom: 8px;"><strong>Ngữ cảnh thông thường:</strong> technology, business meeting</li>
  <li style="margin-bottom: 8px;"><strong>Chủ đề:</strong> medical, education (tự động mở rộng)</li>
  <li style="margin-bottom: 8px;"><strong>Loại từ cụ thể:</strong> technology [noun], run [verb]</li>
  <li style="margin-bottom: 8px;"><strong>Kết hợp:</strong> business meeting [noun]</li>
</ol>

<h4 style="color: #2c3e50; margin: 15px 0 10px 0;">Cú pháp loại từ:</h4>
<ul style="margin-left: 20px; padding-left: 0;">
  <li style="margin-bottom: 5px;">technology [noun] hoặc technology (noun)</li>
  <li style="margin-bottom: 5px;">run [verb] hoặc run (verb)</li>
  <li style="margin-bottom: 5px;">fast [adjective] hoặc fast (adj)</li>
  <li style="margin-bottom: 5px;">quickly [adverb] hoặc quickly (adv)</li>
</ul>

<h4 style="color: #2c3e50; margin: 15px 0 10px 0;">Viết tắt được hỗ trợ:</h4>
<ul style="margin-left: 20px; padding-left: 0;">
  <li style="margin-bottom: 5px;">n, noun → danh từ</li>
  <li style="margin-bottom: 5px;">v, verb → động từ</li>
  <li style="margin-bottom: 5px;">adj, adjective → tính từ</li>
  <li style="margin-bottom: 5px;">adv, adverb → trạng từ</li>
</ul>

<h4 style="color: #2c3e50; margin: 15px 0 10px 0;">Ví dụ:</h4>
<ul style="margin-left: 20px; padding-left: 0;">
  <li style="margin-bottom: 5px;"><code>technology [noun]</code> → phân tích "technology" như danh từ</li>
  <li style="margin-bottom: 5px;"><code>run [verb]</code> → phân tích "run" như động từ</li>
  <li style="margin-bottom: 5px;"><code>light [adj]</code> → phân tích "light" như tính từ</li>
  <li style="margin-bottom: 5px;"><code>medical technology</code> → phân tích trong ngữ cảnh y tế</li>
</ul>
""")
        context_help_text.setMaximumHeight(200)
        context_help_text.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        context_help_text.setStyleSheet("background-color: #f9f9f9; padding: 5px;")
        context_layout.addWidget(context_help_text)
        context_group.setLayout(context_layout)
        content_layout.addWidget(context_group)  # Sửa: content_layout thay vì layout
        
        # API Key
        content_layout.addWidget(QLabel("🔑 Google Gemini API Key (Nhập nhiều key, mỗi dòng 1 key):"))
        self.api_input = QPlainTextEdit()
        # Hiển thị keys từ api_keys (list) hoặc api_key (string cũ)
        keys_text = ""
        if self.config.get("api_keys") and isinstance(self.config["api_keys"], list):
            keys_text = "\n".join(self.config["api_keys"])
        elif self.config.get("api_key"):
            keys_text = self.config["api_key"]
        self.api_input.setPlainText(keys_text)
        self.api_input.setPlaceholderText("Dán danh sách Key vào đây...\nAQ.Ab8...\nAIzaSy...")
        self.api_input.setMinimumHeight(120)
        content_layout.addWidget(self.api_input)
        
        content_layout.addWidget(QLabel("💡 Mẹo: Nhập nhiều key giúp tự động đổi key khi bị hết token (429 Error)."))
        
        content_layout.addWidget(QLabel("🤖 Gemini Model:"))
        self.model_input = QLineEdit(self.config.get("model", GEMINI_DEFAULT_MODEL))
        self.model_input.setPlaceholderText(GEMINI_DEFAULT_MODEL)
        content_layout.addWidget(self.model_input)
        content_layout.addWidget(QLabel("💡 Nên dùng: gemini-3.8-flash (mới nhất). Khi model này lỗi/hết lượt, add-on tự thử: "
                                        + ", ".join(GEMINI_FALLBACK_MODELS[1:])))
        
        content_layout.addWidget(QLabel("⏱️ Timeout (giây):"))
        current_timeout = self.config.get("timeout", 300)
        self.timeout_input = QLineEdit(str(current_timeout))
        content_layout.addWidget(self.timeout_input)

        # Groq Provider (Free alternative)
        group_groq = QGroupBox("🆓 Groq Cloud (FREE - Alternative to Gemini)")
        group_groq.setStyleSheet("QGroupBox { border: 2px solid #FF6D00; border-radius: 5px; margin-top: 10px; padding-top: 10px; } QGroupBox::title { color: #FF6D00; font-weight: bold; }")
        layout_groq = QVBoxLayout()

        layout_groq.addWidget(QLabel("Provider: "))
        self.text_provider_combo = QComboBox()
        self.text_provider_combo.addItems(["gemini", "groq"])
        self.text_provider_combo.setCurrentText(self.config.get("text_provider", "gemini"))
        layout_groq.addWidget(self.text_provider_combo)

        layout_groq.addWidget(QLabel("🔑 Groq API Key (Free at console.groq.com - Nhieu key, moi dong 1 key):"))
        self.groq_key_input = QPlainTextEdit()
        groq_keys_text = ""
        if self.config.get("groq_api_keys") and isinstance(self.config["groq_api_keys"], list):
            groq_keys_text = "\n".join(self.config["groq_api_keys"])
        elif isinstance(self.config.get("groq_api_keys"), str):
            groq_keys_text = self.config["groq_api_keys"]
        self.groq_key_input.setPlainText(groq_keys_text)
        self.groq_key_input.setPlaceholderText("gsk_xxxxxxxxxxxxxxxxxxxxxx")
        self.groq_key_input.setMinimumHeight(80)
        layout_groq.addWidget(self.groq_key_input)

        layout_groq.addWidget(QLabel("🤖 Groq Model:"))
        self.groq_model_input = QLineEdit(self.config.get("groq_model", "llama-3.3-70b-versatile"))
        self.groq_model_input.setPlaceholderText("llama-3.3-70b-versatile, mixtral-8x7b-32768, gemma2-9b-it")
        layout_groq.addWidget(self.groq_model_input)

        groq_help = QLabel("GET FREE KEY: https://console.groq.com/keys\nModels: llama-3.3-70b (best), mixtral-8x7b, llama-3.1-8b")
        groq_help.setStyleSheet("font-size: 11px; color: #FF6D00; margin-top: 5px;")
        layout_groq.addWidget(groq_help)

        group_groq.setLayout(layout_groq)
        content_layout.addWidget(group_groq)

        # Audio Settings
        group_tts = QGroupBox("Cấu hình Audio (Text-to-Speech)")
        layout_tts = QVBoxLayout()
        
        layout_tts.addWidget(QLabel("🔑 TTS API Key (Để trống nếu dùng Key chung):"))
        self.tts_api_input = QLineEdit(self.config.get("tts_api_key", ""))
        self.tts_api_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout_tts.addWidget(self.tts_api_input)

        layout_tts.addWidget(QLabel("🤖 TTS Model:"))
        self.tts_model_input = QLineEdit(self.config.get("tts_model", "gemini-2.5-flash-preview-tts"))
        layout_tts.addWidget(self.tts_model_input)
        
        layout_tts.addWidget(QLabel("🗣️ Giọng đọc (Để trống để tự động phát hiện):"))
        self.voice_input = QLineEdit(self.config.get("voice_name", ""))
        self.voice_input.setPlaceholderText("Kore, Fenrir, Puck, Zephyr...")
        layout_tts.addWidget(self.voice_input)
        
        voice_help = QLabel("• Gợi ý: Kore, Fenrir, Puck, Zephyr, Aoede, Charon")
        voice_help.setStyleSheet("font-size: 11px; color: #666; margin-top: 5px;")
        layout_tts.addWidget(voice_help)
        
        group_tts.setLayout(layout_tts)
        content_layout.addWidget(group_tts)

        # Image Settings - CẬP NHẬT HỖ TRỢ NHIỀU KEY
        group_img = QGroupBox("Cấu hình Ảnh (Pollinations.ai & Khác)")
        layout_img = QVBoxLayout()

        # Checkbox tắt mở chức năng tạo ảnh (Global)
        self.auto_image_cb = QCheckBox("Bật tính năng tự động tạo ảnh")
        self.auto_image_cb.setChecked(self.config.get("auto_image_gen", True))
        self.auto_image_cb.setStyleSheet("font-weight: bold; color: #2E7D32;")
        layout_img.addWidget(self.auto_image_cb)

        # [MỚI] Khung nhập nhiều Pollinations API Key
        layout_img.addWidget(QLabel("🔑 Pollinations API Keys (Nhập nhiều key, mỗi dòng 1 key):"))
        self.pollinations_key_input = QPlainTextEdit()
        # Lấy danh sách key cũ (nếu là list thì join lại, nếu str thì để nguyên)
        pol_keys = self.config.get("pollinations_api_key", "")
        if isinstance(pol_keys, list):
            pol_keys = "\n".join(pol_keys)
        self.pollinations_key_input.setPlainText(str(pol_keys))
        self.pollinations_key_input.setPlaceholderText("Dán danh sách Key vào đây...\nKey_1...\nKey_2...")
        self.pollinations_key_input.setMinimumHeight(80)
        layout_img.addWidget(self.pollinations_key_input)
        
        layout_img.addWidget(QLabel("💡 Hệ thống sẽ tự động đổi key khi gặp lỗi Rate Limit (429)."))

        # Dropdown chọn Engine ưu tiên
        layout_img.addWidget(QLabel("🚀 Chọn Engine tạo ảnh ưu tiên:"))
        self.image_engine_combo = QComboBox()
        self.image_engine_combo.addItems(["auto", "pollinations", "horde", "google_search", "google", "hf"])
        self.image_engine_combo.setCurrentText(self.config.get("image_engine_priority", "auto"))
        layout_img.addWidget(self.image_engine_combo)
        
        # Engine Description
        self.engine_desc_label = QLabel("• Auto: Tự động (Khuyên dùng)\n• Pollinations: Nhanh, Free (Hay lỗi 502)\n• AI Horde: Free, Ổn định (Chờ ~30s)\n• Google: Cần API Key")
        self.engine_desc_label.setStyleSheet("font-size: 11px; color: #555; margin-left: 10px; margin-bottom: 10px;")
        layout_img.addWidget(self.engine_desc_label)

        # Cấu hình Google Search (CSE)
        layout_img.addWidget(QLabel("🔍 Google CSE API Key (Nếu dùng Google Search):"))
        self.cse_key_input = QLineEdit(self.config.get("google_cse_key", ""))
        self.cse_key_input.setEchoMode(QLineEdit.EchoMode.Password)
        layout_img.addWidget(self.cse_key_input)
        
        layout_img.addWidget(QLabel("🔍 Google CSE ID (CX) (Nếu dùng Google Search):"))
        self.cse_cx_input = QLineEdit(self.config.get("google_cse_cx", ""))
        layout_img.addWidget(self.cse_cx_input)

        # Cấu hình Google Imagen
        layout_img.addWidget(QLabel("🎨 Google Imagen Model (Nếu dùng Engine Google):"))
        self.image_model_input = QLineEdit(self.config.get("image_model", "imagen-3.0-generate-001"))
        self.image_model_input.setPlaceholderText("imagen-3.0-generate-001")
        layout_img.addWidget(self.image_model_input)

        # Hugging Face Token (Optional)
        layout_img.addWidget(QLabel("🔑 Hugging Face Token (Nếu dùng Engine HF):"))
        self.hf_token_input = QLineEdit(self.config.get("hf_token", ""))
        self.hf_token_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.hf_token_input.setPlaceholderText("hf_...")
        layout_img.addWidget(self.hf_token_input)

        group_img.setLayout(layout_img)
        content_layout.addWidget(group_img)  # Sửa: content_layout thay vì layout
        
        token_btn = QPushButton("📊 Xem thống kê token")
        token_btn.clicked.connect(show_token_usage_dialog)
        content_layout.addWidget(token_btn)
        
        # Thêm spacer để đẩy nội dung lên trên
        content_layout.addStretch(1)
        
        # Thiết lập widget cho scroll area
        scroll_area.setWidget(content_widget)
        main_layout.addWidget(scroll_area, 1)  # Thêm stretch factor = 1 để scroll area mở rộng
        
        # Nút Lưu cài đặt - ĐẶT NGOÀI SCROLL AREA
        save_btn = QPushButton("💾 Lưu cài đặt")
        save_btn.clicked.connect(self.save_settings)
        save_btn.setStyleSheet("""
            background-color: #2196F3; 
            color: white; 
            font-weight: bold; 
            padding: 12px;
            margin: 5px;
            border-radius: 5px;
            font-size: 14px;
        """)
        main_layout.addWidget(save_btn)
        
        # Thiết lập layout chính
        self.setLayout(main_layout)
    
    def save_settings(self):
        raw_keys = self.api_input.toPlainText().strip()
        # Luôn lưu vào api_keys (list) làm nguồn chính
        if raw_keys:
            self.config["api_keys"] = [k.strip() for k in raw_keys.replace(',', '\n').split('\n') if k.strip()]
        else:
            self.config["api_keys"] = []
        # Xóa api_key cũ để tránh xung đột
        self.config.pop("api_key", None)
        self.config["model"] = self.model_input.text().strip()
        self.config["tts_api_key"] = self.tts_api_input.text().strip()
        self.config["tts_model"] = self.tts_model_input.text().strip()
        self.config["voice_name"] = self.voice_input.text().strip()
        self.config["text_provider"] = self.text_provider_combo.currentText()
        raw_groq_keys = self.groq_key_input.toPlainText().strip()
        if raw_groq_keys:
            self.config["groq_api_keys"] = [k.strip() for k in raw_groq_keys.replace(',', '\n').split('\n') if k.strip()]
        else:
            self.config["groq_api_keys"] = []
        self.config["groq_model"] = self.groq_model_input.text().strip()
        
        # Luu cau hinh anh moi
        self.config["auto_image_gen"] = self.auto_image_cb.isChecked()
        self.config["image_engine_priority"] = self.image_engine_combo.currentText()
        self.config["image_model"] = self.image_model_input.text().strip()
        self.config["hf_token"] = self.hf_token_input.text().strip()
        self.config["google_cse_key"] = self.cse_key_input.text().strip()
        self.config["google_cse_cx"] = self.cse_cx_input.text().strip()
        # [FIX] Lưu Pollinations Keys
        raw_pol_keys = self.pollinations_key_input.toPlainText().strip()
        self.config["pollinations_api_key"] = raw_pol_keys
        
        # Xử lý timeout
        
        try:
            timeout_val = self.timeout_input.text().strip()
            if timeout_val:
                self.config["timeout"] = int(timeout_val)
            else:
                self.config["timeout"] = 300
        except ValueError:
            self.config["timeout"] = 300
            
        save_config(self.config)
        showInfo("✅ Đã lưu cài đặt.")
        self.close()

def show_settings_dialog(): 
    dlg = SettingsDialog(mw)
    dlg.exec()

def categorize_context(context_text):
    """Tự động phân loại context thành các chủ đề cụ thể"""
    context_lower = context_text.lower()
    
    categories = {
        'medical': ['y học', 'bệnh viện', 'bác sĩ', 'sức khỏe', 'y tế'],
        'technology': ['công nghệ', 'máy tính', 'phần mềm', 'lập trình'],
        'business': ['kinh doanh', 'thương mại', 'công ty', 'doanh nghiệp'],
        'academic': ['học thuật', 'trường học', 'giáo dục', 'nghiên cứu'],
        'daily': ['hàng ngày', 'giao tiếp', 'cuộc sống']
    }
    
    for category, keywords in categories.items():
        if any(keyword in context_lower for keyword in keywords):
            return category
    return 'general'

def test_audio_language_detection():
    """Hàm test phát hiện ngôn ngữ cho audio"""
    test_cases = [
        ("Hello world", "en"),
        ("Xin chào", "vi"),
        ("你好", "zh"),
        ("こんにちは", "ja"),
        ("안녕하세요", "ko"),
        ("Hallo Welt", "de"),
        ("12345", "default")
    ]
    
    results = []
    for text, expected in test_cases:
        detected = detect_language_for_audio(text)
        voice = get_voice_for_language(detected, {})
        results.append(f"📝 '{text}' -> {detected} (expected: {expected}) -> Giọng: {voice}")
    
    showInfo("🧪 Kết quả test phát hiện ngôn ngữ:\n\n" + "\n".join(results))

# ========== CẬP NHẬT TEMPLATE ĐỂ HIỂN THỊ TRONG TAB ÁP DỤNG ==========
def update_note_type_template():
    """Cập nhật template của kiểu thẻ hiện tại để hiển thị các trường từ vựng bài đọc trong tab Áp dụng"""
    model = mw.col.models.current()
    if model is None:
        showInfo("Vui lòng mở một thẻ để cập nhật template.")
        return

    # Kiểm tra và thêm các trường nếu chưa có
    fields = mw.col.models.field_names(model)
    if 'Reading_Vocabulary' not in fields:
        mw.col.models.add_field(model, mw.col.models.new_field('Reading_Vocabulary'))
    if 'Reading_Structures' not in fields:
        mw.col.models.add_field(model, mw.col.models.new_field('Reading_Structures'))

    # Duyệt qua tất cả các template của kiểu thẻ
    updated = False
    for template in model['tmpls']:
        current_back_template = template['afmt']

        # Kiểm tra xem đã có trường Reading_Vocabulary và Reading_Structures chưa
        if "{{Reading_Vocabulary}}" not in current_back_template:
            current_back_template += """
<br><br>
{{#Reading_Vocabulary}}
<div class="reading-vocabulary-section" style="margin: 20px 0; padding: 15px; border: 2px solid #4CAF50; border-radius: 10px; background: #f9f9f9;">
    <h3 style="color: #2E7D32; margin-top: 0; border-bottom: 2px solid #4CAF50; padding-bottom: 8px;">📚 Từ vựng từ bài đọc</h3>
    {{Reading_Vocabulary}}
</div>
{{/Reading_Vocabulary}}
"""

        if "{{Reading_Structures}}" not in current_back_template:
            current_back_template += """
{{#Reading_Structures}}
<div class="reading-structures-section" style="margin: 20px 0; padding: 15px; border: 2px solid #2196F3; border-radius: 10px; background: #f9f9f9;">
    <h3 style="color: #1565C0; margin-top: 0; border-bottom: 2px solid #2196F3; padding-bottom: 8px;">🏗️ Cấu trúc từ bài đọc</h3>
    {{Reading_Structures}}
</div>
{{/Reading_Structures}}
"""

        template['afmt'] = current_back_template
        updated = True

    if updated:
        mw.col.models.save(model)
        showInfo("✅ Đã cập nhật template thành công! Các trường từ vựng bài đọc sẽ hiển thị trong tab Áp dụng.")
    else:
        showInfo("ℹ️ Template đã có các trường Reading_Vocabulary và Reading_Structures.")
# ========== QUẢN LÝ TOKEN USAGE ==========
def load_token_usage():
    """Tải thông tin token đã sử dụng"""
    config = load_config()
    if "token_usage" not in config:
        config["token_usage"] = {
            "today": datetime.now().strftime("%Y-%m-%d"),
            "total_tokens": 0,
            "total_requests": 0,
            "daily_reset": True
        }
    return config["token_usage"]

def save_token_usage(token_usage):
    """Lưu thông tin token đã sử dụng"""
    config = load_config()
    config["token_usage"] = token_usage
    save_config(config)

def update_token_usage(prompt_tokens=None, response_tokens=None):
    """Cập nhật token đã sử dụng (ước tính)"""
    try:
        usage = load_token_usage()
        today = datetime.now().strftime("%Y-%m-%d")
        
        # Reset nếu là ngày mới
        if usage["today"] != today and usage.get("daily_reset", True):
            usage["today"] = today
            usage["total_tokens"] = 0
            usage["total_requests"] = 0
        
        # Ước tính token (1 token ≈ 4 ký tự tiếng Anh, 1 token ≈ 2 ký tự tiếng Việt)
        if prompt_tokens:
            usage["total_tokens"] += prompt_tokens
        if response_tokens:
            usage["total_tokens"] += response_tokens
        
        usage["total_requests"] += 1
        save_token_usage(usage)
        return usage
    except Exception as e:
        print(f"❌ Lỗi cập nhật token: {e}")
        return None

def estimate_tokens(text):
    """Ước tính số token từ văn bản"""
    if not text:
        return 0
    
    # Ước tính đơn giản: 1 token ≈ 4 ký tự tiếng Anh, 1 token ≈ 2 ký tự tiếng Việt/tiếng Hoa
    # Kiểm tra xem có ký tự CJK không
    import re
    cjk_chars = len(re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff]', text))
    non_cjk_chars = len(text) - cjk_chars
    
    # Ước tính token
    tokens = (cjk_chars / 2) + (non_cjk_chars / 4)
    return int(tokens)

def get_token_reset_time():
    """Lấy thời gian reset token tiếp theo"""
    usage = load_token_usage()
    today_str = usage.get("today", datetime.now().strftime("%Y-%m-%d"))
    
    try:
        from datetime import timedelta
        today = datetime.strptime(today_str, "%Y-%m-%d")
        tomorrow = today + timedelta(days=1)
        now = datetime.now()
        time_left = tomorrow - now
        
        hours = time_left.seconds // 3600
        minutes = (time_left.seconds % 3600) // 60
        seconds = time_left.seconds % 60
        
        return {
            "reset_time": tomorrow.strftime("%Y-%m-%d %H:%M:%S"),
            "time_left": f"{hours:02d}:{minutes:02d}:{seconds:02d}",
            "total_tokens": usage.get("total_tokens", 0),
            "total_requests": usage.get("total_requests", 0)
        }
    except Exception as e:
        print(f"❌ Lỗi tính thời gian reset: {e}")
        return None
# ========== DIALOG HIỂN THỊ TOKEN USAGE ==========
class TokenUsageDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("📊 Token Usage Statistics")
        self.setMinimumWidth(400)
        
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("📊 Thống kê sử dụng Gemini API")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; color: #2c3e50; margin-bottom: 20px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Thêm section hiển thị trạng thái key
        key_group = QGroupBox("🔑 Trạng thái API Keys")
        key_layout = QVBoxLayout()
        
        config = load_config()
        api_keys = config.get("api_keys", [])
        current_index = config.get("current_key_index", 0)
        
        if api_keys:
            key_status = f"📊 Đang sử dụng: Key {current_index + 1}/{len(api_keys)}"
            key_status += f"\n🔑 Tổng số key: {len(api_keys)}"
            
            # Hiển thị key hiện tại (ẩn phần giữa)
            if api_keys:
                current_key = api_keys[current_index]
                masked_key = current_key[:10] + "..." + current_key[-10:] if len(current_key) > 20 else current_key
                key_status += f"\n\n🔐 Key hiện tại: {masked_key}"
        else:
            key_status = "❌ Chưa cấu hình API Key"
        
        key_label = QLabel(key_status)
        key_label.setWordWrap(True)
        key_layout.addWidget(key_label)
        
        # Nút xoay key thủ công
        manual_rotate_btn = QPushButton("🔄 Xoay Key thủ công")
        manual_rotate_btn.clicked.connect(self.manual_rotate_key)
        key_layout.addWidget(manual_rotate_btn)
        
        key_group.setLayout(key_layout)
        layout.addWidget(key_group)
        
        # Get token info
        token_info = get_token_reset_time()
        
        if token_info:
            # Token usage section
            usage_group = QGroupBox("Token đã sử dụng hôm nay")
            usage_layout = QVBoxLayout()
            
            # Total tokens
            tokens_label = QLabel(f"📈 Tổng số token: <b>{token_info['total_tokens']:,}</b>")
            tokens_label.setStyleSheet("font-size: 14px; margin: 5px;")
            usage_layout.addWidget(tokens_label)
            
            # Total requests
            requests_label = QLabel(f"🔢 Tổng số request: <b>{token_info['total_requests']}</b>")
            requests_label.setStyleSheet("font-size: 14px; margin: 5px;")
            usage_layout.addWidget(requests_label)
            
            # Average tokens per request
            if token_info['total_requests'] > 0:
                avg_tokens = token_info['total_tokens'] // token_info['total_requests']
                avg_label = QLabel(f"📊 Trung bình mỗi request: <b>{avg_tokens:,}</b> token")
                avg_label.setStyleSheet("font-size: 14px; margin: 5px;")
                usage_layout.addWidget(avg_label)
            
            usage_group.setLayout(usage_layout)
            layout.addWidget(usage_group)
            
            # Reset time section
            reset_group = QGroupBox("Thời gian reset token")
            reset_layout = QVBoxLayout()
            
            # Reset time
            reset_time_label = QLabel(f"🔄 Reset vào lúc: <b>{token_info['reset_time']}</b>")
            reset_time_label.setStyleSheet("font-size: 14px; margin: 5px;")
            reset_layout.addWidget(reset_time_label)
            
            # Time left
            time_left_label = QLabel(f"⏱️ Thời gian còn lại: <b>{token_info['time_left']}</b>")
            time_left_label.setStyleSheet("font-size: 14px; margin: 5px; color: #e74c3c;")
            reset_layout.addWidget(time_left_label)
            
            reset_group.setLayout(reset_layout)
            layout.addWidget(reset_group)
            
            # Note section
            note_group = QGroupBox("📝 Ghi chú")
            note_layout = QVBoxLayout()
            
            note_text = QLabel(
                "• Token sẽ được reset vào 00:00:00 mỗi ngày<br>"
                "• 1 token ≈ 4 ký tự tiếng Anh<br>"
                "• 1 token ≈ 2 ký tự tiếng Việt/tiếng Hoa<br>"
                "• Đây là ước tính, số liệu thực tế có thể khác"
            )
            note_text.setStyleSheet("font-size: 12px; color: #7f8c8d; margin: 5px;")
            note_text.setWordWrap(True)
            note_layout.addWidget(note_text)
            
            note_group.setLayout(note_layout)
            layout.addWidget(note_group)
        else:
            error_label = QLabel("❌ Không thể lấy thông tin token")
            error_label.setStyleSheet("font-size: 14px; color: #e74c3c;")
            layout.addWidget(error_label)
        
        # Buttons
        button_layout = QHBoxLayout()
        
        refresh_btn = QPushButton("🔄 Làm mới")
        refresh_btn.clicked.connect(self.refresh)
        
        close_btn = QPushButton("✖️ Đóng")
        close_btn.clicked.connect(self.close)
        
        button_layout.addWidget(refresh_btn)
        button_layout.addWidget(close_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
    
    def manual_rotate_key(self):
        """Xoay key thủ công"""
        config = load_config()
        
        # Tạo request giả để kiểm tra các Key
        fake_url = f"https://generativelanguage.googleapis.com/v1beta/models/{config.get('model', GEMINI_DEFAULT_MODEL)}:generateContent?key={{API_KEY}}"
        fake_payload = {"contents": [{"parts": [{"text": "Hello"}]}]}
        
        showInfo("⏳ Đang kiểm tra danh sách Key...")
        
        # Gọi hàm từ gemini_features để test key
        # Hàm này sẽ tự động thử lần lượt các key trong danh sách
        success, _ = call_gemini_with_key_rotation(
            fake_url, 
            {"Content-Type": "application/json"}, 
            fake_payload, 
            config, 
            timeout=10
        )
        
        if success: 
             showInfo("✅ Kết nối thành công! Hệ thống đã tìm được Key hoạt động tốt.")
             self.close()
             show_token_usage_dialog()  # Mở lại bảng để cập nhật trạng thái
        else:
             showInfo("❌ Tất cả các Key đều không hoạt động. Vui lòng kiểm tra lại mạng hoặc danh sách Key.")
    
    def refresh(self):
        self.close()
        show_token_usage_dialog()

def show_token_usage_dialog():
    """Hiển thị dialog thống kê token usage"""
    dialog = TokenUsageDialog(mw)
    dialog.exec()

def setup_menu():
    settings_action = QAction("Gemini Editor Settings...", mw)
    settings_action.triggered.connect(show_settings_dialog)
    mw.form.menuTools.addAction(settings_action)
    
    # Token usage action
    token_action = QAction("📊 Token Usage Statistics", mw)
    token_action.triggered.connect(show_token_usage_dialog)
    mw.form.menuTools.addAction(token_action)

    # Kiểm tra key sống/chết/hết lượt + ước tính số từ còn thêm được hôm nay
    key_health_action = QAction("🩺 Kiểm tra API key Gemini", mw)
    key_health_action.triggered.connect(show_gemini_key_health_dialog)
    mw.form.menuTools.addAction(key_health_action)

    # Batch add actions
    batch_add_action = QAction("✨ Thêm hàng loạt từ Gemini...", mw)
    batch_add_action.triggered.connect(show_batch_add_dialog)
    mw.form.menuTools.addAction(batch_add_action)
    
    # Optimized batch add action
    optimized_batch_action = QAction("🚀 Thêm hàng loạt tối ưu (Optimized)...", mw)
    optimized_batch_action.triggered.connect(show_optimized_batch_dialog)
    mw.form.menuTools.addAction(optimized_batch_action)
    
    # Resume interrupted batch
    resume_action = QAction("🔄 Tiếp tục tiến trình bị gián đoạn", mw)
    resume_action.triggered.connect(resume_interrupted_batch)
    mw.form.menuTools.addAction(resume_action)
    
    # Action để tạo từ vựng liên quan từ bài đọc
    related_vocab_action = QAction("🔗 Tạo từ vựng liên quan từ bài đọc", mw)  
    related_vocab_action.triggered.connect(generate_related_vocabulary_from_reading_tools)
    mw.form.menuTools.addAction(related_vocab_action)
    
    # Thêm action để cập nhật template
    update_template_action = QAction("📝 Cập nhật template cho tab Áp dụng", mw)
    update_template_action.triggered.connect(update_note_type_template)
    mw.form.menuTools.addAction(update_template_action)
    
    # THÊM ACTION TEST PHÁT HIỆN NGÔN NGỮ
    test_audio_action = QAction("🔊 Test phát hiện ngôn ngữ audio", mw)
    test_audio_action.triggered.connect(test_audio_language_detection)
    mw.form.menuTools.addAction(test_audio_action)
    # ... existing menu actions ...
    
    # [NEW] Upgrade Note Type Action
    upgrade_action = QAction("⬆️ Upgrade Note Type (Add Specialized Fields)", mw)
    upgrade_action.triggered.connect(upgrade_note_type_specialized)
    mw.form.menuTools.addAction(upgrade_action)

    # THÊM NÚT MỚI: Thêm nút bài tập dịch vào template
    update_drill_template_action = QAction("🔄 Thêm nút bài tập dịch vào template", mw)
    update_drill_template_action.triggered.connect(add_drill_buttons_to_template)
    mw.form.menuTools.addAction(update_drill_template_action)

    context_guide_action = QAction("📚 Hướng dẫn sử dụng Context", mw)
    context_guide_action.triggered.connect(show_context_usage_guide)
    mw.form.menuTools.addAction(context_guide_action)
    
def generate_related_vocabulary_from_reading_tools():
    """Tạo từ vựng liên quan từ bài đọc cho note hiện tại trong editor"""
    # Kiểm tra xem có editor đang mở không
    if hasattr(mw, 'currentEditor') and mw.currentEditor is not None:
        editor = mw.currentEditor
        generate_related_vocabulary_from_reading(editor)
    else:
        showInfo("⚠️ Vui lòng mở một thẻ trong trình chỉnh sửa để sử dụng chức năng này.")

# ========== CHỨC NĂNG TẠO BÀI ĐỌC CHO TAB ÁP DỤNG ==========
def generate_reading_passage(word: str, config: dict):
    """Tạo bài đọc ngắn liên quan đến từ vựng (Đã update Key Rotation)"""
    prompt = f"""
Bạn là một giáo viên ngôn ngữ chuyên nghiệp. Hãy tạo một bài đọc ngắn (khoảng 100-150 từ) cho người học tiếng Anh, sử dụng từ "{word}" một cách tự nhiên.

YÊU CẦU:
1. Bài đọc phải liên quan đến chủ đề của từ "{word}"
2. Sử dụng từ "{word}" ít nhất 2-3 lần trong ngữ cảnh phù hợp
3. Ngôn ngữ phù hợp với trình độ intermediate (B1-B2)
4. Có tính giáo dục và thú vị

Sau bài đọc, hãy tạo 2 câu hỏi đọc hiểu:
- 1 câu hỏi về nội dung chính
- 1 câu hỏi về cách sử dụng từ vựng

Định dạng JSON:
{{
    "title": "Tiêu đề bài đọc bằng tiếng Anh",
    "content": "Nội dung bài đọc bằng tiếng Anh...",
    "translation": "Bản dịch tiếng Việt của toàn bộ bài đọc",
    "questions": [
        {{
            "question": "Câu hỏi đọc hiểu 1?",
            "options": ["Đáp án A", "Đáp án B", "Đáp án C", "Đáp án D"],
            "correctAnswer": 0,
            "explanation": "Explanation in English about why this answer is correct"
        }},
        {{
            "question": "Câu hỏi đọc hiểu 2?",
            "options": ["Đáp án A", "Đáp án B", "Đáp án C", "Đáp án D"],
            "correctAnswer": 1, 
            "explanation": "Explanation in English about why this answer is correct"
        }}
    ]
}}

Chỉ trả về JSON, không có text nào khác.
"""
    # CẬP NHẬT: Sử dụng URL Template cho Key Rotation
    model = config.get("model", GEMINI_DEFAULT_MODEL)
    url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        # GỌI QUA HÀM XOAY VÒNG KEY
        success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout=60)
        
        if not success:
            return (False, f"Lỗi API: {result}")
        
        response = result
        raw_response = response.json()
        
        if "candidates" not in raw_response or not raw_response["candidates"]:
             return (False, "Không nhận được phản hồi từ Gemini")

        content_text = raw_response["candidates"][0]["content"]["parts"][0]["text"]
        
        # Trích xuất JSON từ response
        json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                reading_data = json.loads(json_str)
                return (True, reading_data)
            except json.JSONDecodeError:
                return (False, "Lỗi parse JSON bài đọc")
        else:
            return (False, "Không tìm thấy dữ liệu JSON trong phản hồi")
            
    except Exception as e:
        return (False, f"Lỗi kết nối: {str(e)}")

# ========== DIALOG PROGRESS VỚI NÚT CANCEL ==========
class BatchProgressDialog(QDialog):
    def __init__(self, parent=None, total=0, title="Processing"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.total = total
        self.current = 0
        self.cancelled = False

        layout = QVBoxLayout()

        self.label = QLabel("Starting...")
        layout.addWidget(self.label)

        self.progress = QProgressBar()
        self.progress.setMaximum(total)
        layout.addWidget(self.progress)

        # Nút Cancel
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_button)

        self.setLayout(layout)
        self.resize(400, 120)

    def update(self, value, label=None):
        self.current = value
        self.progress.setValue(value)
        if label:
            self.label.setText(label)
        
        # Tự động đóng khi hoàn thành
        if value >= self.total:
            self.close()

    def cancel(self):
        self.cancelled = True
        self.label.setText("Cancelling...")
        self.cancel_button.setEnabled(False)
        self.close()

# ========== POPUP WINDOW FOR FAILED VOCABULARY WITH SCROLL BAR ==========
def show_failed_vocabulary_popup(failed_vocabulary_list, popup_type="corrected"):
    """Show popup window with failed vocabulary for user to copy"""
    """Show popup window with failed vocabulary for user to copy"""
    from aqt.qt import QDialog, QVBoxLayout, QLabel, QTextEdit, QPushButton, QHBoxLayout, QScrollArea, QWidget
    
    # Set title and message based on popup type
    if popup_type == "corrected":
        title = "✏️ Từ đã được sửa chính tả"
        instruction = "📋 Copy các từ ĐÃ ĐƯỢC SỬA bên dưới để thêm lại:"
        button_text = "📋 Copy vocabulary corrected"
    else:  # paused or other errors
        title = "❌ Từ không thể thêm"
        instruction = "📋 Copy các từ bên dưới để thử lại sau (đúng chính tả nhưng gặp lỗi khác):"
        button_text = "📋 Copy vocabulary"
    
    popup = QDialog(mw)
    popup.setWindowTitle(title)
    popup.resize(500, 400)
    
    layout = QVBoxLayout()
    
    # Title and instructions
    title_label = QLabel(title)
    title_label.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px; color: #2c3e50;")
    layout.addWidget(title_label)
    
    instruction_label = QLabel(instruction)
    instruction_label.setStyleSheet("color: #34495e; margin-bottom: 10px; font-size: 14px;")
    instruction_label.setWordWrap(True)
    layout.addWidget(instruction_label)
    
    # Create scroll area
    scroll_area = QScrollArea()
    scroll_area.setWidgetResizable(True)
    scroll_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    
    # Create container widget for scroll area
    scroll_widget = QWidget()
    scroll_layout = QVBoxLayout(scroll_widget)
    
    # Text area with scroll bar for vocabulary
    text_area = QTextEdit()
    text_area.setReadOnly(True)
    text_area.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    text_area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    
    # Format the vocabulary list - clean format for easy copying
    if failed_vocabulary_list:
        formatted_text = ""
        for vocab in failed_vocabulary_list:
            # For corrected words, extract just the suggested spelling
            if popup_type == "corrected" and "→" in vocab:
                # Extract the suggested word from format: "'word' → 'corrected'"
                try:
                    suggested_word = vocab.split("→")[1].strip().replace("'", "")
                    formatted_text += f"{suggested_word}\n"
                except:
                    formatted_text += f"{vocab}\n"
            else:
                # For other failed words, use the original word (already cleaned in on_done)
                formatted_text += f"{vocab}\n"
        
        text_area.setText(formatted_text.strip())
        text_area.selectAll()  # Select all text for easy copying
    else:
        text_area.setText("Không có từ nào cần hiển thị.")
    
    scroll_layout.addWidget(text_area)
    scroll_area.setWidget(scroll_widget)
    layout.addWidget(scroll_area)
    
    # Button layout
    button_layout = QHBoxLayout()
    
    copy_button = QPushButton(button_text)
    copy_button.clicked.connect(lambda: copy_vocabulary_to_clipboard(failed_vocabulary_list, popup_type))
    copy_button.setStyleSheet("""
        QPushButton {
            background: #3498db;
            color: white;
            padding: 10px;
            border-radius: 5px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: #2980b9;
        }
    """)
    
    close_button = QPushButton("✖️ Đóng")
    close_button.clicked.connect(popup.close)
    close_button.setStyleSheet("""
        QPushButton {
            background: #e74c3c;
            color: white;
            padding: 10px;
            border-radius: 5px;
            font-weight: bold;
        }
        QPushButton:hover {
            background: #c0392b;
        }
    """)
    
    button_layout.addWidget(copy_button)
    button_layout.addWidget(close_button)
    layout.addLayout(button_layout)
    
    popup.setLayout(layout)
    popup.exec()

def copy_vocabulary_to_clipboard(vocabulary_list, popup_type="corrected"):
    """Copy vocabulary list to clipboard - clean format for re-adding"""
    if vocabulary_list:
        # Clean the words for easy re-adding
        clean_words = []
        for vocab in vocabulary_list:
            if popup_type == "corrected" and "→" in vocab:
                # Extract the suggested word
                try:
                    suggested_word = vocab.split("→")[1].strip().replace("'", "")
                    clean_words.append(suggested_word)
                except:
                    # Fallback: remove quotes if any
                    clean_word = vocab.replace("'", "").replace('"', '')
                    clean_words.append(clean_word)
            else:
                # For other failed words, use as-is (already cleaned)
                clean_words.append(vocab)
        
        text_to_copy = "\n".join(clean_words)
        from aqt.qt import QApplication, QClipboard
        clipboard = QApplication.clipboard()
        clipboard.setText(text_to_copy)
        tooltip(f"✅ Đã sao chép {len(clean_words)} từ vào clipboard!")
# ========== CẬP NHẬT HÀM BATCH PROCESSING (FIX LỖI KHÔNG NHẬN CONTEXT) ==========
def run_batch_processing_for_browser(browser: Browser, processing_type="fill"):
    """Hàm xử lý hàng loạt tổng quát cho Browser - VỚI POPUP CHO TỪ THẤT BẠI"""
    config = load_config()
    nids = browser.selected_notes()
    if not nids:
        tooltip("Vui lòng chọn ít nhất một thẻ.")
        return
    
    # Kiểm tra API key
    api_key = None
    if "api_keys" in config and isinstance(config["api_keys"], list) and config["api_keys"]:
        api_key = config["api_keys"][0]
    if not api_key and config.get("api_key"):
        api_key = config["api_key"]
        
    if not api_key or "YOUR_API_KEY_HERE" in api_key:
        showCritical("Vui lòng thiết lập API Key trong Tools → Gemini Editor Settings...")
        return
    # Tạo progress dialog
    dialog_title = "🔄 Cải thiện dữ liệu từ vựng" if processing_type == "fill" else "🔄 Tạo từ vựng liên quan"
    progress_dialog = BatchProgressDialog(parent=browser, total=len(nids), title=dialog_title)
    
    # Biến để theo dõi trạng thái hủy
    cancelled = False
    
    def worker():
        nonlocal cancelled
        results = {
            'updated_count': 0,
            'spelling_corrections': [],
            'skipped_notes': [],
            'error_notes': [],
            'failed_vocabulary': [],  # Từ sai chính tả
            'paused_vocabulary': [],  # Từ đúng chính tả nhưng lỗi khác
            'total_notes': len(nids)
        }
        
        for i, nid in enumerate(nids):
            # KIỂM TRA NẾU NGƯỜI DÙNG ĐÃ HỦY
            if cancelled or progress_dialog.cancelled:
                cancelled = True
                break
                
            try:
                note = mw.col.get_note(nid)
                
                # [FIX] Dùng hàm tìm Word linh hoạt
                keyword = get_note_field_value(note, ["Word", "Từ vựng", "Keyword", "Thuật ngữ", "Expression"])
                
                # CẬP NHẬT PROGRESS DIALOG
                current_number = i + 1
                if keyword:
                    progress_label = f"🔄 Đang xử lý {current_number}/{len(nids)}: '{keyword}'"
                else:
                    progress_label = f"🔄 Đang xử lý {current_number}/{len(nids)}"
                
                # Cập nhật dialog trong main thread
                mw.taskman.run_on_main(lambda n=current_number, lbl=progress_label: progress_dialog.update(n, lbl))
                
                if not keyword:
                    results['skipped_notes'].append("(thiếu từ khóa)")
                    continue
                
                # XỬ LÝ THEO LOẠI
                if processing_type == "fill":
                    # [FIX] Dùng hàm tìm Context linh hoạt cho Batch
                    context_fields = ["Context", "Ngữ cảnh", "Topic", "Chủ đề", "Situation", "Tình huống", "Context/Topic"]
                    user_context = get_note_field_value(note, context_fields)
                    
                    # Gọi Gemini với Context đã tìm thấy
                    result = get_gemini_data(keyword, config, user_context)
                    
                    if isinstance(result, tuple) and len(result) == 2:
                        status, data = result
                        
                        if status == "spelling_correction":
                            correction_msg = f"'{keyword}' → '{data}'"
                            results['spelling_corrections'].append(correction_msg)
                            results['failed_vocabulary'].append(f"{keyword} (suggested: {data})")
                            continue
                        
                        if status == True:
                            if 'fill_note_with_data' in globals():
                                fill_note_with_data(note, data)
                            else:
                                for key, value in data.items():
                                    if key in note: note[key] = str(value)
                                    
                            mw.col.update_note(note)
                            results['updated_count'] += 1
                        else:
                            # Xử lý lỗi
                            if 'format_error_message' in globals():
                                error_msg = format_error_message(keyword, data)
                            else:
                                error_msg = f"{keyword}: {data}"
                                
                            results['error_notes'].append(error_msg)
                            results['paused_vocabulary'].append(keyword)
                
                elif processing_type == "related_vocab":
                    # Logic cho related vocabulary (giữ nguyên logic gốc)
                    reading_content = ""
                    if "Reading" in note: reading_content = note["Reading"]
                    
                    if not reading_content.strip():
                        results['skipped_notes'].append(f"'{keyword}' (thiếu bài đọc)")
                        continue
                    
                    # Xử lý nội dung bài đọc
                    try:
                        reading_data = json.loads(reading_content)
                        reading_text = reading_data.get("content", reading_content) if isinstance(reading_data, dict) else reading_content
                    except:
                        reading_text = reading_content
                    
                    if not reading_text.strip():
                        results['skipped_notes'].append(f"'{keyword}' (nội dung trống)")
                        continue
                    
                    # Gọi hàm phân tích (giả định hàm này đã tồn tại trong code của bạn)
                    if 'call_gemini_for_vocabulary_analysis' in globals():
                        result = call_gemini_for_vocabulary_analysis(keyword, reading_text, config)
                        if isinstance(result, tuple) and len(result) == 2:
                            success, vocab_data = result
                            if success:
                                set_reading_vocab_fields(note, vocab_data)
                                
                                mw.col.update_note(note)
                                results['updated_count'] += 1
                            else:
                                results['error_notes'].append(f"{keyword}: {vocab_data}")
                                results['paused_vocabulary'].append(keyword)
                    else:
                        results['error_notes'].append("Chưa định nghĩa hàm call_gemini_for_vocabulary_analysis")
                            
            except Exception as e:
                error_msg = f"'{keyword if keyword else 'unknown'}' - Lỗi hệ thống: {str(e)}"
                results['error_notes'].append(error_msg)
                if keyword:
                    results['paused_vocabulary'].append(keyword)
        
        # THÊM THÔNG TIN HỦY VÀO KẾT QUẢ
        results['cancelled'] = cancelled
        results['processed_count'] = i + 1 if not cancelled else i
        
        return results
    
    def on_done(future):
        nonlocal cancelled
        try:
            results = future.result()
            progress_dialog.close()
            
            # HIỂN THỊ POPUP CHO TỪ SAI CHÍNH TẢ
            if results.get('failed_vocabulary') and 'show_failed_vocabulary_popup' in globals():
                show_failed_vocabulary_popup(results['failed_vocabulary'], "corrected")
            
            # HIỂN THỊ POPUP CHO TỪ ĐÚNG CHÍNH TẢ NHƯNG LỖI KHÁC
            if results.get('paused_vocabulary') and 'show_failed_vocabulary_popup' in globals():
                show_failed_vocabulary_popup(results['paused_vocabulary'], "paused")
            
            # TẠO THÔNG BÁO KẾT QUẢ
            message_parts = []
            
            if results.get('cancelled', False):
                message_parts.append(f"🛑 ĐÃ DỪNG! Đã xử lý được {results['processed_count']}/{results['total_notes']} thẻ")
            
            if results['updated_count'] > 0:
                message_parts.append(f"✅ Đã cải thiện thành công {results['updated_count']}/{results['processed_count']} thẻ")
            
            if results['spelling_corrections']:
                corrections_count = len(results['spelling_corrections'])
                message_parts.append(f"🔍 Phát hiện {corrections_count} từ có thể sai chính tả")
            
            if results['skipped_notes']:
                skipped_count = len(results['skipped_notes'])
                message_parts.append(f"⏭️ Bỏ qua {skipped_count} thẻ (thiếu thông tin)")
            
            # THÔNG BÁO VỀ TỪ THẤT BẠI
            failed_count = len(results.get('failed_vocabulary', []))
            paused_count = len(results.get('paused_vocabulary', []))
            
            if failed_count > 0:
                message_parts.append(f"✏️ {failed_count} từ sai chính tả (đã hiển thị gợi ý sửa)")
            if paused_count > 0:
                message_parts.append(f"⏸️ {paused_count} từ không thể thêm (xem popup để sao chép)")
            
            # LUÔN HIỂN THỊ THÔNG BÁO
            if message_parts:
                final_message = "\n\n".join(message_parts)
                showInfo(final_message)
            else:
                showInfo("🔄 Hoàn tất! Không có thẻ nào cần cập nhật.")
            
            # Refresh browser
            try:
                if browser and hasattr(browser, 'search') and callable(browser.search):
                    browser.search()
            except Exception as e:
                print(f"Không thể refresh browser: {e}")
                
        except Exception as e:
            progress_dialog.close()
            showCritical(f"❌ Lỗi trong quá trình xử lý: {e}")

    # XÁC NHẬN TRƯỚC KHI BẮT ĐẦU
    from aqt.qt import QMessageBox
    
    if processing_type == "fill":
        title = "🔄 CẢI THIỆN DỮ LIỆU TỪ VỰNG"
        message = f"Bạn có muốn cải thiện thông tin từ vựng cho {len(nids)} thẻ đã chọn?\n(Gemini sẽ ưu tiên Context nếu có)"
    else:
        title = "🔄 TẠO TỪ VỰNG LIÊN QUAN" 
        message = f"Bạn có muốn tạo từ vựng liên quan cho {len(nids)} thẻ đã chọn?"
    
    reply = QMessageBox.question(browser, title, message, 
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    
    if reply == QMessageBox.StandardButton.Yes:
        # Hiển thị progress dialog
        progress_dialog.show()
        
        # Kết nối sự kiện cancel
        def handle_cancel():
            nonlocal cancelled
            cancelled = True
            progress_dialog.cancel()
        
        progress_dialog.cancel_button.clicked.connect(handle_cancel)
        
        # Chạy worker
        mw.taskman.run_in_background(worker, on_done)

# ========== CẬP NHẬT HÀM BATCH ADD VỚI POPUP CHO TỪ THẤT BẠI ==========
def run_batch_add(words_text: str, deck_name: str):
    """Chạy thêm hàng loạt từ với Progress Dialog và nút Cancel - VỚI POPUP CHO TỪ THẤT BẠI"""
    import time
    
    config = load_config()
    words = [word.strip() for word in words_text.splitlines() if word.strip()]
    if not words:
        tooltip("Danh sách từ trống.")
        return

    model = mw.col.models.current()
    model_fields = mw.col.models.field_names(model)

    required_fields_check = ["Word", "Definition_VI", "Exercises"]
    missing_fields_check = [f for f in required_fields_check if f not in model_fields]
    if missing_fields_check:
        showCritical("Kiểu thẻ (Note Type) của bạn đang thiếu các trường cần thiết:\n\n" + "\n".join(missing_fields_check))
        return

    did = mw.col.decks.id(deck_name)

    # Tạo progress dialog
    progress_dialog = BatchProgressDialog(parent=mw, total=len(words), title="✨ Thêm hàng loạt từ Gemini")
    cancelled = False

    def worker():
        nonlocal cancelled
        created_count = 0
        failed_words = []
        spelling_corrections = []
        failed_vocabulary = []  # Từ sai chính tả
        paused_vocabulary = []  # Từ đúng chính tả nhưng lỗi khác

        for i, keyword in enumerate(words):
            # KIỂM TRA NẾU NGƯỜI DÙNG ĐÃ HỦY
            if cancelled or progress_dialog.cancelled:
                cancelled = True
                break

            # CẬP NHẬT PROGRESS DIALOG
            current_label = f"🔄 Đang xử lý: {keyword}"
            mw.taskman.run_on_main(lambda n=i + 1, lbl=current_label: progress_dialog.update(n, lbl))

            # Gọi Gemini với context rỗng vì batch add không có context
            result = get_gemini_data(keyword, config, "")
            
            if isinstance(result, tuple) and len(result) == 2:
                status, data = result
                
                # XỬ LÝ CHÍNH TẢ
                if status == "spelling_correction":
                    spelling_corrections.append(f"'{keyword}' → '{data}'")
                    failed_words.append(f"{keyword} (sai chính tả, gợi ý: {data})")
                    failed_vocabulary.append(f"{keyword} (suggested: {data})")
                    continue
                
                if status == True:
                    # 1. TẠO VÀ LƯU THẺ
                    note = mw.col.new_note(model)
                    fill_note_with_data(note, data)
                    mw.col.add_note(note, did)
                    created_count += 1
                    
                    # 2. TỰ ĐỘNG TẠO ẢNH (LOGIC MỚI ĐƯỢC THÊM VÀO)
                    # Kiểm tra xem user có bật auto_image_gen không
                    if config.get("auto_image_gen", True):
                        try:
                            # Cập nhật UI báo đang vẽ
                            paint_label = f"🎨 Đang vẽ minh họa cho: {keyword}..."
                            mw.taskman.run_on_main(lambda lbl=paint_label: progress_dialog.label.setText(lbl))
                            
                            # Lấy Definition và POS từ dữ liệu Gemini vừa trả về
                            # Đây là điểm quan trọng: Dùng Definition làm prompt để vẽ chính xác
                            definition_en = data.get("definition_en", "")
                            pos_type = data.get("part_of_speech", "")
                            
                            # Gọi hàm xử lý ảnh (đảm bảo hàm này tồn tại)
                            if 'handle_image_generation_and_save' in globals():
                                img_tag = handle_image_generation_and_save(
                                    keyword=keyword,
                                    config=config,
                                    definition_en=definition_en, # Truyền definition vào
                                    context="", 
                                    pos_type=pos_type
                                )
                                
                                if img_tag:
                                    # Tìm trường ảnh để điền
                                    target_fields = ["Image", "Picture", "Hình ảnh", "Minh họa"]
                                    field_updated = False
                                    
                                    if "Image" in note:
                                        note["Image"] = img_tag
                                        field_updated = True
                                    else:
                                        for f in target_fields:
                                            if f in note:
                                                note[f] = img_tag
                                                field_updated = True
                                                break
                                    
                                    # Cập nhật note nếu có ảnh mới
                                    if field_updated:
                                        mw.col.update_note(note)
                                        print(f"✅ Đã thêm ảnh cho {keyword}")
                        except Exception as e:
                            print(f"⚠️ Lỗi tạo ảnh trong batch cho '{keyword}': {e}")

                else:
                    failed_words.append(keyword)
                    paused_vocabulary.append(keyword)
            else:
                failed_words.append(keyword)
                paused_vocabulary.append(keyword)
            
            # Thêm delay nhỏ để tránh quá tải API
            time.sleep(0.5)

        # THÊM THÔNG TIN HỦY VÀO KẾT QUẢ
        result = {
            'created_count': created_count,
            'failed_words': failed_words,
            'spelling_corrections': spelling_corrections,
            'failed_vocabulary': failed_vocabulary,
            'paused_vocabulary': paused_vocabulary,
            'cancelled': cancelled,
            'processed_count': i + 1 if not cancelled else i,
            'total_words': len(words)
        }
        
        return result

    def on_done(future):
        nonlocal cancelled
        try:
            result = future.result()
            progress_dialog.close()
            
            # HIỂN THỊ POPUP CHO TỪ SAI CHÍNH TẢ
            if result.get('failed_vocabulary'):
                show_failed_vocabulary_popup(result['failed_vocabulary'], "corrected")
            
            # HIỂN THỊ POPUP CHO TỪ ĐÚNG CHÍNH TẢ NHƯNG LỖI KHÁC
            if result.get('paused_vocabulary'):
                show_failed_vocabulary_popup(result['paused_vocabulary'], "paused")
            
            # THÔNG BÁO THÀNH CÔNG - LUÔN HIỂN THỊ
            if result['created_count'] > 0:
                success_msg = f"✅ Đã tạo thành công {result['created_count']} thẻ vào bộ '{deck_name}'"
                
                # THÊM THÔNG BÁO NẾU CÓ HỦY
                if result.get('cancelled', False):
                    success_msg = f"🛑 ĐÃ DỪNG! Đã tạo {result['created_count']} / {result['processed_count']} thẻ vào bộ '{deck_name}'"
                
                if result['spelling_corrections']:
                    corrections_count = len(result['spelling_corrections'])
                    success_msg += f"\n\n🔍 Phát hiện {corrections_count} từ có thể sai chính tả"
                
                # HIỂN THỊ THÔNG BÁO THÀNH CÔNG
                showInfo(success_msg)

            # LUÔN RESET GIAO DIỆN
            mw.reset()
            
        except Exception as e:
            progress_dialog.close()
            showCritical(f"Có lỗi xảy ra: {e}")

    # Hiển thị progress dialog
    progress_dialog.show()
    
    # Kết nối sự kiện cancel
    def handle_cancel():
        nonlocal cancelled
        cancelled = True
        progress_dialog.cancel()
    
    progress_dialog.cancel_button.clicked.connect(handle_cancel)
    
    # Chạy worker
    mw.taskman.run_in_background(worker, on_done)
# ========== CẬP NHẬT HÀM XỬ LÝ BROWSER OPTIMIZED ==========
# ========== CẬP NHẬT: HÀM CHẠY TỐI ƯU TRONG BROWSER ==========
def run_optimized_browser_processing(browser: Browser):
    """
    Hàm xử lý sự kiện khi chọn '🚀 Add optimized vocabulary list' trong Browser.
    """
    nids = browser.selected_notes()
    if not nids:
        tooltip("Vui lòng chọn ít nhất một thẻ.")
        return

    # 1. Hiển thị Dialog cấu hình (MỚI)
    dialog = OptimizedBrowserDialog(mw, len(nids))
    if not dialog.exec():
        return # Người dùng hủy

    # Lấy thông số từ dialog
    global_context = dialog.global_context_input.text().strip()
    global_def_vi = dialog.global_def_input.text().strip()
    batch_size = dialog.batch_size_spin.value()
    delay = dialog.delay_spin.value()
    auto_image = dialog.auto_image_cb.isChecked()
    
    config = load_config()

    # 2. Khởi tạo Progress Dialog
    try:
        progress_dialog = OptimizedBatchProgressDialog(parent=mw, total_words=len(nids), title="🚀 Optimizing Selected Cards")
    except NameError:
        progress_dialog = BatchProgressDialog(parent=mw, total=len(nids), title="🚀 Optimizing Selected Cards")

    progress_dialog.show()

    # 3. Định nghĩa Worker
    def worker():
        try:
            # Khởi tạo Engine với tham số đầy đủ từ Dialog
            engine = OptimizedBrowserEngine(
                config=config, 
                nids=nids, 
                batch_size=batch_size, 
                delay=delay, 
                max_retries=3,
                global_context=global_context,
                global_def_vi=global_def_vi,
                auto_image=auto_image
            )
            return engine.run(progress_dialog)
        except Exception as e:
            print(f"❌ Lỗi khởi tạo engine: {str(e)}")
            return None

    # 4. Xử lý kết quả
    def on_done(future):
        try:
            results = future.result()
            progress_dialog.close()

            if not results:
                showCritical("❌ Đã xảy ra lỗi hệ thống trong quá trình xử lý.")
                return

            if results.get('stopped_early', False):
                showInfo("🛑 Đã dừng xử lý theo yêu cầu.")
            
            # Hiển thị popup lỗi chính tả nếu có
            if results.get('spelling_corrections') and 'show_failed_vocabulary_popup' in globals():
                show_failed_vocabulary_popup(results['spelling_corrections'], "corrected")

            # Hiển thị từ thất bại
            if results.get('failed'):
                failed_clean = [f.split('(')[0].strip() if '(' in f else f for f in results['failed']]
                if 'show_failed_vocabulary_popup' in globals():
                    show_failed_vocabulary_popup(failed_clean, "paused")

            # Tổng kết
            success_count = results.get('succeeded', 0)
            total = results.get('total_words', len(nids))
            rate = (success_count / total * 100) if total > 0 else 0
            
            msg = f"""
✅ HOÀN TẤT TỐI ƯU HÓA!

📊 Thống kê:
• Thành công: {success_count}/{total} ({rate:.1f}%)
• Thất bại: {len(results.get('failed', []))}
"""
            if global_context: msg += f"• Global Context: {global_context}\n"
            if global_def_vi: msg += f"• Global Def VN: {global_def_vi}\n"
            
            showInfo(msg)
            
            # Refresh lại browser
            browser.search()

        except Exception as e:
            progress_dialog.close()
            showCritical(f"❌ Lỗi xử lý kết quả: {str(e)}")

    # 5. Chạy background task
    mw.taskman.run_in_background(worker, on_done)
# ========== UPDATED: BROWSER MENU HOOKS ==========
def add_browser_context_menu_item(browser: Browser, menu):
    """Thêm item vào menu chuột phải (Context Menu) trong Browser"""
    try:
        menu.addSeparator()
        
        # Action 1: Fill
        action1 = menu.addAction("✨ Thêm chi tiết với Gemini")
        action1.triggered.connect(lambda: run_batch_processing_for_browser(browser, "fill"))
        
        # Action 2: Related Vocab
        action2 = menu.addAction("🔗 Tạo từ vựng liên quan")
        action2.triggered.connect(lambda: run_batch_processing_for_browser(browser, "related_vocab"))
        
        # Action 3: Optimized Batch Add (UPDATED to use new flow)
        action3 = menu.addAction("🚀 Add optimized vocabulary list")
        action3.triggered.connect(lambda: run_optimized_browser_processing(browser))
        
    except Exception as e:
        print(f"❌ Lỗi thêm context menu: {e}")

# ========== CẬP NHẬT HÀM BATCH ADD DIALOG ==========
def show_batch_add_dialog():
    """Hiển thị dialog thêm hàng loạt - VỚI PROGRESS DIALOG MỚI"""
    dialog = BatchAddDialog(mw)
    if dialog.exec(): 
        run_batch_add(dialog.words_text, dialog.selected_deck)

# ========== CẬP NHẬT HÀM FORMAT ERROR MESSAGE ==========

def format_error_message(keyword, error_data):
    """Định dạng thông báo lỗi cho dễ đọc"""
    error_str = str(error_data)
    
    if "Expecting value" in error_str:
        return f"'{keyword}' - Lỗi JSON: Phản hồi không hợp lệ từ API"
    elif "429" in error_str:
        return f"'{keyword}' - Lỗi 429: Quá nhiều request, thử lại sau"
    elif "timed out" in error_str.lower():
        return f"'{keyword}' - Lỗi timeout: Kết nối quá lâu, thử lại"
    elif "connection" in error_str.lower():
        return f"'{keyword}' - Lỗi kết nối: Kiểm tra internet"
    else:
        # Giới hạn độ dài thông báo lỗi
        if len(error_str) > 100:
            return f"'{keyword}' - {error_str[:100]}..."
        else:
            return f"'{keyword}' - {error_str}"

# ========== XỬ LÝ PYCMD TỪ BACK TEMPLATE ==========
# Field lưu lịch sử tab Luyện câu (JSON). Field UserSentence cũ không còn dùng nên tận dụng lại,
# khỏi phải thêm field mới (thêm field sẽ bắt đồng bộ lại toàn bộ lên AnkiWeb).
SENTENCE_LOG_FIELD = "UserSentence"

def _note_for_card_message(context, word):
    """Note của thẻ đang hiển thị (Reviewer/Previewer). Trả về (note, None) hoặc (None, mã lỗi)."""
    card = getattr(context, "card", None)
    if callable(card):  # Previewer dùng card() thay vì thuộc tính card
        card = card()
    if card is None:
        return None, "no_card"
    try:
        note = card.note()
    except Exception:
        return None, "no_note"
    if not getattr(note, "id", 0):
        return None, "no_note"
    # Đã chuyển sang thẻ khác trong lúc AI đang chạy -> không ghi nhầm vào note khác
    if "Word" in note and clean_field_text(note["Word"]).lower() != clean_field_text(word).lower():
        return None, "word_mismatch"
    return note, None

def save_card_data(context, payload, kind):
    """Lưu dữ liệu do thẻ gửi lên (thẻ tự gọi Gemini, chỉ nhờ add-on ghi vào note để đồng bộ AnkiWeb).
    kind 'sp' = lịch sử Luyện câu -> UserSentence; 'rv' = từ vựng bài đọc -> Reading_Vocabulary.
    Trả về chuỗi trạng thái cho callback pycmd bên JS ('ok' nếu đã lưu)."""
    import html
    try:
        message = json.loads(payload)
        word, data = message["word"], message["data"]
    except (ValueError, TypeError, KeyError):
        return "bad_payload"
    note, error = _note_for_card_message(context, word)
    if error:
        return error

    if kind == "sp":
        if SENTENCE_LOG_FIELD not in note:
            return "no_field"
        # Escape để JSON nằm an toàn trong HTML của thẻ; JS đọc lại bằng textContent
        note[SENTENCE_LOG_FIELD] = html.escape(json.dumps(data, ensure_ascii=False), quote=False)
    else:
        if "Reading_Vocabulary" not in note or not isinstance(data, dict):
            return "no_field"
        set_reading_vocab_fields(note, data)

    try:
        mw.col.update_note(note, skip_undo_entry=True)  # không chen vào lịch sử Undo của lượt ôn
    except TypeError:
        mw.col.update_note(note)
    return "ok"

def fill_full_from_card(context, payload):
    """Nút '✨ Điền đầy đủ' trên thẻ nhẹ (máy tính): AI điền đủ các mục cho đúng thẻ đang ôn.
    Trả lời ngay 'started'; điền xong thẻ tự vẽ lại (update_notes), lỗi thì hiện tooltip."""
    try:
        word = json.loads(payload)["word"]
    except (ValueError, TypeError, KeyError):
        return "bad_payload"
    note, error = _note_for_card_message(context, word)
    if error:
        return error
    context_text = get_note_field_value(note, ["Context", "Ngữ cảnh", "Topic", "Chủ đề", "Situation", "Tình huống", "Context/Topic"])

    def done(outcomes):
        ok, res = outcomes[0] if outcomes else (False, "không có kết quả")
        tooltip(f"✨ Đã thêm chi tiết cho thẻ '{word}'" if ok else f"❌ Chưa thêm được chi tiết cho '{word}': {str(res)[:120]}")

    fill_full_notes([{"nid": note.id, "word": clean_field_text(word), "context": context_text}], done)
    return "started"

def handle_webview_message(handled, message, context):
    """Xử lý các lệnh từ JavaScript trong back template - ĐÃ SỬA LỖI CONTEXT.WEB"""
    try:
        if isinstance(message, str):
            print(f"🔍 Nhận message từ webview: {message[:100]}...")

            # Lưu lịch sử tab Luyện câu / từ vựng bài đọc (thẻ tự gọi Gemini, chỉ gửi kết quả lên để lưu)
            if message.startswith("sp_save:"):
                return (True, save_card_data(context, message[len("sp_save:"):], "sp"))
            elif message.startswith("rv_save:"):
                return (True, save_card_data(context, message[len("rv_save:"):], "rv"))
            elif message.startswith("fill_full:"):
                return (True, fill_full_from_card(context, message[len("fill_full:"):]))

            # Xử lý tạo bài tập dịch
            elif message == "generate_translation_drill":
                print("🎯 NHẬN LỆNH: generate_translation_drill từ back template")
                
                # Hiển thị loading indicator
                js_loading = """
                console.log('🔄 Hiển thị loading cho bài tập dịch...');
                
                // Tạo loading indicator nếu chưa có
                var loadingDiv = document.getElementById('drill-loading');
                if (!loadingDiv) {
                    loadingDiv = document.createElement('div');
                    loadingDiv.id = 'drill-loading';
                    loadingDiv.style.cssText = `
                        position: fixed;
                        top: 50%;
                        left: 50%;
                        transform: translate(-50%, -50%);
                        background: rgba(0,0,0,0.8);
                        color: white;
                        padding: 20px;
                        border-radius: 10px;
                        z-index: 9999;
                        text-align: center;
                    `;
                    loadingDiv.innerHTML = `
                        <div style="margin-bottom: 10px;">
                            <div class="spinner" style="
                                width: 30px;
                                height: 30px;
                                border: 3px solid rgba(255,255,255,0.3);
                                border-radius: 50%;
                                border-top-color: #fff;
                                animation: spin 1s ease-in-out infinite;
                                margin: 0 auto;
                            "></div>
                        </div>
                        <div>🔄 Đang tạo bài tập dịch...</div>
                    `;
                    document.body.appendChild(loadingDiv);
                } else {
                    loadingDiv.style.display = 'block';
                }
                
                // Vô hiệu hóa nút
                var btn = document.getElementById('generate-translation-btn');
                if (btn) {
                    btn.disabled = true;
                    btn.style.opacity = '0.6';
                    btn.style.cursor = 'not-allowed';
                }
                """
                
                # Sử dụng mw.reviewer.web thay vì context.web
                if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                    mw.reviewer.web.eval(js_loading)
                
                def process_translation_drill():
                    try:
                        card = context.card
                        if not card:
                            return (False, "Không tìm thấy card")
                        
                        note = card.note()
                        if not note:
                            return (False, "Không tìm thấy note")
                        
                        # SỬA LỖI: Dùng note["Word"] thay vì note.get("Word", "")
                        word = note["Word"] if "Word" in note else ""
                        
                        if not word:
                            return (False, "Không tìm thấy từ khóa trong trường 'Word'")
                        
                        print(f"🎯 Tạo bài tập dịch cho từ: '{word}'")
                        config = load_config()
                        return create_translation_drill(word, config)
                        
                    except Exception as e:
                        print(f"❌ Lỗi trong process_translation_drill: {str(e)}")
                        return (False, f"Lỗi xử lý: {str(e)}")
                
                def on_translation_done(future):
                    try:
                        success, result = future.result()
                        
                        # Ẩn loading và kích hoạt lại nút
                        js_hide_loading = """
                        var loadingDiv = document.getElementById('drill-loading');
                        if (loadingDiv) {
                            loadingDiv.style.display = 'none';
                        }
                        
                        var btn = document.getElementById('generate-translation-btn');
                        if (btn) {
                            btn.disabled = false;
                            btn.style.opacity = '1';
                            btn.style.cursor = 'pointer';
                        }
                        """
                        
                        if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                            mw.reviewer.web.eval(js_hide_loading)
                        
                        if success:
                            # Định dạng và hiển thị kết quả
                            html_content = format_translation_drill_html(result, result.get('keyword', ''))
                            
                            js_result = f"""
                            console.log('✅ Hiển thị bài tập dịch từ Python');
                            
                            var container = document.getElementById('translation-drill-container');
                            if (container) {{
                                container.innerHTML = {json.dumps(html_content)};
                            }} else {{
                                // Tạo container nếu chưa có
                                container = document.createElement('div');
                                container.id = 'translation-drill-container';
                                container.style.cssText = 'margin: 20px 0; padding: 15px; border: 2px solid #4CAF50; border-radius: 10px; background: #f9f9f9;';
                                
                                var drillSection = document.getElementById('translation-drill-section');
                                if (drillSection) {{
                                    drillSection.appendChild(container);
                                }} else {{
                                    // Fallback: thêm vào cuối body
                                    document.body.appendChild(container);
                                }}
                                container.innerHTML = {json.dumps(html_content)};
                            }}
                            
                            if (typeof showPracticeMessage === 'function') {{
                                showPracticeMessage('✅ Đã tạo bài tập dịch thành công!', 'success');
                            }} else {{
                                // Fallback
                                alert('✅ Đã tạo bài tập dịch thành công!');
                            }}
                            """
                            
                            if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                                mw.reviewer.web.eval(js_result)
                        else:
                            js_error = f"""
                            if (typeof showPracticeMessage === 'function') {{
                                showPracticeMessage({json.dumps('❌ Lỗi tạo bài tập dịch: ' + str(result))}, 'error');
                            }} else {{
                                alert({json.dumps('❌ Lỗi tạo bài tập dịch: ' + str(result))});
                            }}
                            """
                            if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                                mw.reviewer.web.eval(js_error)
                                
                    except Exception as e:
                        print(f"❌ Lỗi trong on_translation_done: {str(e)}")
                        js_error = f"""
                        var loadingDiv = document.getElementById('drill-loading');
                        if (loadingDiv) loadingDiv.style.display = 'none';
                        
                        var btn = document.getElementById('generate-translation-btn');
                        if (btn) {{
                            btn.disabled = false;
                            btn.style.opacity = '1';
                            btn.style.cursor = 'pointer';
                        }}
                        
                        if (typeof showPracticeMessage === 'function') {{
                            showPracticeMessage({json.dumps('❌ Lỗi xử lý bài tập dịch: ' + str(e))}, 'error');
                        }}
                        """
                        if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                            mw.reviewer.web.eval(js_error)
                
                # Chạy xử lý trong background
                mw.taskman.run_in_background(process_translation_drill, on_translation_done)
                return (True, None)
            
            # Xử lý tạo bài tập phiên dịch
            elif message == "generate_interpreting_drill":
                print("🎯 NHẬN LỆNH: generate_interpreting_drill từ back template")
                
                # Hiển thị loading indicator
                js_loading = """
                console.log('🔄 Hiển thị loading cho bài tập phiên dịch...');
                
                // Tạo loading indicator nếu chưa có
                var loadingDiv = document.getElementById('drill-loading');
                if (!loadingDiv) {
                    loadingDiv = document.createElement('div');
                    loadingDiv.id = 'drill-loading';
                    loadingDiv.style.cssText = `
                        position: fixed;
                        top: 50%;
                        left: 50%;
                        transform: translate(-50%, -50%);
                        background: rgba(0,0,0,0.8);
                        color: white;
                        padding: 20px;
                        border-radius: 10px;
                        z-index: 9999;
                        text-align: center;
                    `;
                    loadingDiv.innerHTML = `
                        <div style="margin-bottom: 10px;">
                            <div class="spinner" style="
                                width: 30px;
                                height: 30px;
                                border: 3px solid rgba(255,255,255,0.3);
                                border-radius: 50%;
                                border-top-color: #fff;
                                animation: spin 1s ease-in-out infinite;
                                margin: 0 auto;
                            "></div>
                        </div>
                        <div>🔄 Đang tạo bài tập phiên dịch...</div>
                    `;
                    document.body.appendChild(loadingDiv);
                } else {
                    loadingDiv.style.display = 'block';
                }
                
                // Vô hiệu hóa nút
                var btn = document.getElementById('generate-interpreting-btn');
                if (btn) {
                    btn.disabled = true;
                    btn.style.opacity = '0.6';
                    btn.style.cursor = 'not-allowed';
                }
                """
                
                # Sử dụng mw.reviewer.web thay vì context.web
                if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                    mw.reviewer.web.eval(js_loading)
                
                def process_interpreting_drill():
                    try:
                        card = context.card
                        if not card:
                            return (False, "Không tìm thấy card")
                        
                        note = card.note()
                        if not note:
                            return (False, "Không tìm thấy note")
                        
                        # SỬA LỖI: Dùng note["Word"] thay vì note.get("Word", "")
                        word = note["Word"] if "Word" in note else ""
                        
                        if not word:
                            return (False, "Không tìm thấy từ khóa trong trường 'Word'")
                        
                        print(f"🎯 Tạo bài tập phiên dịch cho từ: '{word}'")
                        config = load_config()
                        return create_interpreting_drill(word, config)
                        
                    except Exception as e:
                        print(f"❌ Lỗi trong process_interpreting_drill: {str(e)}")
                        return (False, f"Lỗi xử lý: {str(e)}")
                
                def on_interpreting_done(future):
                    try:
                        success, result = future.result()
                        
                        # Ẩn loading và kích hoạt lại nút
                        js_hide_loading = """
                        var loadingDiv = document.getElementById('drill-loading');
                        if (loadingDiv) {
                            loadingDiv.style.display = 'none';
                        }
                        
                        var btn = document.getElementById('generate-interpreting-btn');
                        if (btn) {
                            btn.disabled = false;
                            btn.style.opacity = '1';
                            btn.style.cursor = 'pointer';
                        }
                        """
                        
                        if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                            mw.reviewer.web.eval(js_hide_loading)
                        
                        if success:
                            # Định dạng và hiển thị kết quả
                            html_content = format_interpreting_drill_html(result, result.get('keyword', ''))
                            
                            js_result = f"""
                            console.log('✅ Hiển thị bài tập phiên dịch từ Python');
                            
                            var container = document.getElementById('interpreting-drill-container');
                            if (container) {{
                                container.innerHTML = {json.dumps(html_content)};
                            }} else {{
                                // Tạo container nếu chưa có
                                container = document.createElement('div');
                                container.id = 'interpreting-drill-container';
                                container.style.cssText = 'margin: 20px 0; padding: 15px; border: 2px solid #9C27B0; border-radius: 10px; background: #f9f9f9;';
                                
                                var drillSection = document.getElementById('interpreting-drill-section');
                                if (drillSection) {{
                                    drillSection.appendChild(container);
                                }} else {{
                                    // Fallback: thêm vào cuối body
                                    document.body.appendChild(container);
                                }}
                                container.innerHTML = {json.dumps(html_content)};
                            }}
                            
                            if (typeof showPracticeMessage === 'function') {{
                                showPracticeMessage('✅ Đã tạo bài tập phiên dịch thành công!', 'success');
                            }} else {{
                                // Fallback
                                alert('✅ Đã tạo bài tập phiên dịch thành công!');
                            }}
                            """
                            
                            if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                                mw.reviewer.web.eval(js_result)
                        else:
                            js_error = f"""
                            if (typeof showPracticeMessage === 'function') {{
                                showPracticeMessage({json.dumps('❌ Lỗi tạo bài tập phiên dịch: ' + str(result))}, 'error');
                            }} else {{
                                alert({json.dumps('❌ Lỗi tạo bài tập phiên dịch: ' + str(result))});
                            }}
                            """
                            if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                                mw.reviewer.web.eval(js_error)
                                
                    except Exception as e:
                        print(f"❌ Lỗi trong on_interpreting_done: {str(e)}")
                        js_error = f"""
                        var loadingDiv = document.getElementById('drill-loading');
                        if (loadingDiv) loadingDiv.style.display = 'none';
                        
                        var btn = document.getElementById('generate-interpreting-btn');
                        if (btn) {{
                            btn.disabled = false;
                            btn.style.opacity = '1';
                            btn.style.cursor = 'pointer';
                        }}
                        
                        if (typeof showPracticeMessage === 'function') {{
                            showPracticeMessage({json.dumps('❌ Lỗi xử lý bài tập phiên dịch: ' + str(e))}, 'error');
                        }}
                        """
                        if hasattr(mw, 'reviewer') and mw.reviewer and hasattr(mw.reviewer, 'web'):
                            mw.reviewer.web.eval(js_error)
                
                # Chạy xử lý trong background
                mw.taskman.run_in_background(process_interpreting_drill, on_interpreting_done)
                return (True, None) 
    except Exception as e:
        print(f"💥 Lỗi tổng thể trong handle_webview_message: {str(e)}")
        import traceback
        traceback.print_exc()
    
    return handled
# ========== LUYỆN CÂU TRONG EDITOR (hiện kết quả trong cửa sổ riêng) ==========

def show_rich_result_dialog(title, content, is_markdown=True, parent=None):
    """Hiện kết quả AI trong cửa sổ riêng (Markdown hoặc HTML).
    Không phụ thuộc vào DOM của editor nên chạy được với cả editor cũ lẫn editor thử nghiệm mới."""
    from aqt.qt import QApplication
    dlg = QDialog(parent or mw)
    dlg.setWindowTitle(title)
    dlg.resize(640, 580)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    layout = QVBoxLayout(dlg)

    view = QTextBrowser()
    view.setOpenExternalLinks(True)
    if is_markdown:
        view.setMarkdown(content)
    else:
        view.setHtml(content)
    layout.addWidget(view)

    btn_row = QHBoxLayout()
    copy_btn = QPushButton("📋 Copy")
    copy_btn.clicked.connect(lambda: (QApplication.clipboard().setText(view.toPlainText()), tooltip("✅ Đã copy")))
    close_btn = QPushButton("Đóng")
    close_btn.clicked.connect(dlg.accept)
    btn_row.addStretch()
    btn_row.addWidget(copy_btn)
    btn_row.addWidget(close_btn)
    layout.addLayout(btn_row)

    dlg.show()
    return dlg

def _run_sentence_ai_editor(editor: Editor, mode: str):
    """Kiểm tra (mode='check') hoặc đề xuất cải thiện (mode='suggest') câu người dùng tự đặt.
    Trước đây hàm dùng editor.web.eval() để lấy câu, nhưng eval() luôn trả về None nên nút
    luôn báo 'Vui lòng nhập câu'. Giờ: đọc ô nhập (nếu có) bằng evalWithCallback, không có thì
    hỏi bằng hộp thoại, rồi hiện kết quả trong cửa sổ riêng."""
    note = editor.note
    word = clean_field_text(get_note_field_value(note, ["Word", "Từ vựng", "Keyword", "Expression"])) if note else ""
    if not word:
        tooltip("⚠️ Vui lòng nhập từ vào trường 'Word' trước")
        return

    config = load_config()
    is_check = mode == "check"
    title = "✅ Kiểm tra câu" if is_check else "💡 Đề xuất cải thiện câu"
    ai_func = check_user_sentence_backside if is_check else suggest_sentence_improvement_backside
    parent = getattr(editor, "parentWindow", None) or mw

    def start(user_sentence):
        user_sentence = (user_sentence or "").strip()
        if not user_sentence:
            text, ok = QInputDialog.getMultiLineText(parent, title, f'Nhập câu của bạn có dùng từ "{word}":')
            if not ok or not text.strip():
                return
            user_sentence = text.strip()

        tooltip("⏳ Đang kiểm tra câu với Gemini..." if is_check else "⏳ Đang đề xuất cải thiện với Gemini...")

        def on_done(future):
            try:
                success, result = future.result()
            except Exception as e:
                success, result = False, str(e)
            if success:
                show_rich_result_dialog(f"{title}: {word}",
                                        f"**Câu của bạn:** {user_sentence}\n\n---\n\n{result}",
                                        parent=parent)
            else:
                showCritical(f"❌ Lỗi: {result}")

        mw.taskman.run_in_background(lambda: ai_func(word, user_sentence, config), on_done)

    editor.web.evalWithCallback(
        "(function(){var el=document.getElementById('user-sentence-input');return el?el.value:'';})()",
        start
    )

def run_sentence_check_editor(editor: Editor):
    """Chạy kiểm tra câu tự đặt trong editor"""
    _run_sentence_ai_editor(editor, "check")

def run_sentence_suggestion_editor(editor: Editor):
    """Chạy đề xuất cải thiện câu trong editor"""
    _run_sentence_ai_editor(editor, "suggest")

# ========== CHỨC NĂNG LUYỆN CÂU & XỬ LÝ PYCMD ==========
def check_user_sentence_backside(word: str, user_sentence: str, config: dict):
    """Kiểm tra câu người dùng tự đặt và đưa ra phản hồi chi tiết"""
    
    try:
        # Kiểm tra độ dài câu (tối đa 500 từ để test)
        word_count = len(user_sentence.split())
        if word_count > 500:
            return (False, f"Câu của bạn quá dài ({word_count} từ). Vui lòng giới hạn trong 500 từ.")
        
        # Kiểm tra API key
        api_key = None
        if "api_keys" in config and isinstance(config["api_keys"], list) and config["api_keys"]:
            api_key = config["api_keys"][0]
        if not api_key and config.get("api_key"):
            api_key = config["api_key"]
        if not api_key or "YOUR_API_KEY_HERE" in api_key:
            return (False, "Vui lòng thiết lập API Key trong phần cài đặt Gemini.")
        
        # Prompt đơn giản hơn để test
        prompt = f"""
You are a friendly, practical English teacher helping a Vietnamese learner.
The learner is studying the word "{word}" and wrote this sentence:
"{user_sentence}"

Give feedback in Vietnamese. Be CONCRETE and SIMPLE: imagine you're talking to a student, not writing a textbook.

REQUIRED OUTPUT FORMAT (follow exactly):

---
📌 **Nhận xét nhanh:** (1 câu tóm tắt: câu đúng/sai/gần đúng và tại sao)

🔍 **Vấn đề chính (nếu có):**
- Giải thích LỖI cụ thể bằng tiếng Việt đơn giản, không dùng thuật ngữ ngôn ngữ học
- Ví dụ: "Từ 'facilitate' thường đi với sự việc/quá trình, không đi với người. Ví dụ: facilitate a meeting, facilitate learning, không dùng 'facilitate someone'"
- Nếu câu ĐÚNG, ghi rõ "✅ Câu của bạn đúng và tự nhiên."

✅ **Câu mẫu đúng:**
(Viết 1-2 câu mẫu chuẩn dùng từ "{word}" đúng cách, gần với ý định của người học)

💡 **Mẹo nhớ cách dùng "{word}":**
(1-2 câu ngắn, thực tế. Ví dụ: "'{word}' thường đi với [loại object], hay gặp trong ngữ cảnh [X]")

---

QUAN TRỌNG:
- Không dùng: "mệnh đề", "chủ vị", "ngoại động từ", "thức giả định" hay bất kỳ thuật ngữ ngữ pháp khó hiểu nào
- LUÔN đưa ra câu ví dụ đúng để người học so sánh
- Nếu câu người dùng viết đúng rồi, khen ngắn gọn và gợi ý nâng cao thêm
- Tối đa 200 từ tổng cộng
"""
        print(f"🔍 Gọi check_user_sentence_backside với prompt đơn giản")
        return call_gemini_api_simple(prompt, config)
        
    except Exception as e:
        print(f"❌ Lỗi trong check_user_sentence_backside: {str(e)}")
        import traceback
        traceback.print_exc()
        return (False, f"Lỗi xử lý câu: {str(e)}")

def suggest_sentence_improvement_backside(word: str, user_sentence: str, config: dict):
    """Đề xuất cách cải thiện câu để tự nhiên hơn - Tập trung và cô đọng"""
    prompt = f"""
Bạn là một giáo viên tiếng Anh bản xứ thân thiện và chuyên nghiệp.
Học sinh đang học từ "{word}" và viết câu này:
"{user_sentence}"

Hãy đánh giá và đề xuất cải thiện câu cho học sinh theo cấu trúc sau:

1. **Đánh giá câu gốc (Original Sentence Evaluation):**
   - Đánh giá độ tự nhiên: [Tự nhiên / Chưa tự nhiên / Sai ngữ pháp / Sai từ vựng].
   - Giải thích ngắn gọn lý do hoặc lỗi sai bằng tiếng Việt (ví dụ: dùng sai giới từ, sai collocation với từ "{word}", v.v.).

2. **Gợi ý viết lại (Suggested Improvements):**
   - Đề xuất 2 đến 3 cách viết lại câu trên để tự nhiên hơn.
   - Phân loại rõ phong cách của từng đề xuất (ví dụ: "Casual/Daily Life" - Giao tiếp, "Formal/Academic" - Trang trọng, "Idiomatic/Natural" - Bản xứ).
   - Với mỗi đề xuất, kèm theo giải thích ngắn gọn bằng tiếng Việt vì sao cách viết này tốt hơn câu gốc.

3. **Điểm ngữ pháp/Từ vựng cần nhớ (Key Learning Point):**
   - Nếu câu gốc có lỗi ngữ pháp (như dùng sai thì, sai cấu trúc), hãy giải thích ngắn gọn cách dùng đúng của cấu trúc đó trong câu này. Không giải thích lý thuyết lan man.

**Yêu cầu định dạng:**
- Trình bày bằng Markdown rõ ràng, dễ đọc.
- Nội dung cô đọng, đi thẳng vào vấn đề, tối ưu cho người học trên thiết bị di động.
- Không giải thích dông dài hoặc đưa các kiến thức không liên quan.
- Không giải thích lại các thông tin đã được nói từ đoạn trước, tránh trùng lặp, nói lan man.
"""
    return call_gemini_api_simple(prompt, config)

    return call_gemini_api_simple(prompt, config)

def call_gemini_api_simple(prompt: str, config: dict):
    """Hàm gọi API Gemini đơn giản cho chức năng luyện câu (Đã update Key Rotation)"""
    # CẬP NHẬT: Sử dụng URL Template cho Key Rotation
    model = config.get("model", GEMINI_DEFAULT_MODEL)
    url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    print(f"🔍 Gọi Gemini API với prompt dài: {len(prompt)} ký tự (Model: {model})")
    
    try:
        print("🔄 Đang gửi request đến Gemini (có xoay vòng key)...")
        # Sử dụng timeout 300s mặc định để đảm bảo đủ thời gian
        success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout=300)
        
        if not success:
            error_msg = f"Lỗi API: {result}"
            print(f"❌ {error_msg}")
            return (False, error_msg)
        
        # result là response object
        response = result
        raw_response = response.json()
        print("✅ Đã nhận response JSON từ Gemini")
        
        if "candidates" not in raw_response or not raw_response["candidates"]:
            print("❌ Không có candidates trong response")
            return (False, "Không nhận được phản hồi từ Gemini")
            
        content_text = raw_response["candidates"][0]["content"]["parts"][0]["text"]
        print(f"✅ Đã trích xuất nội dung: {len(content_text)} ký tự")
        return (True, content_text)
        
    except Exception as e:
        print(f"❌ Lỗi exception trong call_gemini_api_simple: {str(e)}")
        return (False, f"Lỗi kết nối: {str(e)}")

# ========== CHỨC NĂNG TẠO TỪ VỰNG TỪ BÀI ĐỌC ==========
def generate_vocabulary_from_reading(editor: Editor):
    """Tạo danh sách từ vựng và cấu trúc câu từ bài đọc trong trường Reading"""
    config = load_config()
    note = editor.note
    
    # Kiểm tra trường Reading
    if "Reading" not in note or not (note["Reading"] or '').strip():
        tooltip("⚠️ Không tìm thấy dữ liệu bài đọc trong trường 'Reading'")
        return
        
    reading_content = note["Reading"]
    
    # Kiểm tra xem có phải là JSON không
    try:
        reading_data = json.loads(reading_content)
        if isinstance(reading_data, dict) and "content" in reading_data:
            reading_text = reading_data["content"]
        else:
            reading_text = reading_content
    except:
        reading_text = reading_content
    
    if not reading_text.strip():
        tooltip("⚠️ Nội dung bài đọc trống")
        return
        
    tooltip("⏳ Đang phân tích từ vựng từ bài đọc...")
    
    def worker():
        return analyze_reading_vocabulary(reading_text, config)
    
    def on_data_received(future):
        try:
            success, result = future.result()
            if success:
                # Điền dữ liệu vào các trường mới (JSON gọn cho tab Áp dụng)
                set_reading_vocab_fields(note, result)
                
                editor.loadNote()
                tooltip("✅ Đã tạo từ vựng từ bài đọc!")
            else:
                showCritical(f"❌ Lỗi phân tích bài đọc: {result}")
        except Exception as e:
            showCritical(f"❌ Lỗi xử lý: {str(e)}")
    
    mw.taskman.run_in_background(worker, on_data_received)

def analyze_reading_vocabulary(reading_text: str, config: dict):
    """Phân tích bài đọc để trích xuất từ vựng (Đã update Key Rotation)"""
    prompt = f"""
Hãy phân tích bài đọc sau và trích xuất:

1. Đúng 5 từ/cụm từ đáng học nhất có trong bài (ưu tiên cụm từ, collocation; sau đó mới đến từ đơn khó)
2. Đúng 2 cấu trúc câu đáng chú ý trong bài

Bài đọc:
{reading_text}

YÊU CẦU:
- Sắp xếp từ vựng theo mức độ quan trọng
- Với mỗi từ vựng: từ gốc, loại từ, phiên âm, nghĩa tiếng Việt, ví dụ từ bài đọc
- Với mỗi cấu trúc: cấu trúc, giải thích cách dùng, ví dụ từ bài đọc
- Ưu tiên từ và cấu trúc xuất hiện trong bài đọc

Định dạng JSON:
{{
    "vocabulary": [
        {{
            "word": "từ vựng",
            "base_form": "dạng gốc",
            "pos": "loại từ",
            "pronunciation": "phiên âm",
            "meaning_vi": "nghĩa tiếng Việt",
            "example_from_reading": "ví dụ từ bài đọc",
            "translation": "bản dịch ví dụ"
        }}
    ],
    "structures": [
        {{
            "structure": "cấu trúc câu",
            "explanation_vi": "giải thích cách dùng",
            "example_from_reading": "ví dụ từ bài đọc", 
            "translation": "bản dịch ví dụ"
        }}
    ]
}}

Chỉ trả về JSON, không có text nào khác.
""" 
    # CẬP NHẬT: Sử dụng URL Template cho Key Rotation
    model = config.get("model", GEMINI_DEFAULT_MODEL)
    url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        # GỌI QUA HÀM XOAY VÒNG KEY
        success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout=60)
        
        if not success:
            return (False, f"Lỗi API: {result}")
            
        response = result
        raw_response = response.json()
        
        if "candidates" not in raw_response or not raw_response["candidates"]:
             return (False, "Không nhận được phản hồi từ Gemini")

        content_text = raw_response["candidates"][0]["content"]["parts"][0]["text"]
        
        # Trích xuất JSON từ response
        json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                vocab_data = json.loads(json_str)
                return (True, vocab_data)
            except json.JSONDecodeError:
                return (False, "Lỗi parse JSON phân tích bài đọc")
        else:
            return (False, "Không tìm thấy dữ liệu JSON trong phản hồi")
            
    except Exception as e:
        return (False, f"Lỗi kết nối: {str(e)}")

# ========== CHỨC NĂNG MỚI: PHÂN TÍCH TỪ VỰNG LIÊN QUAN TỪ BÀI ĐỌC ==========
def generate_related_vocabulary_from_reading(editor: Editor):
    """Phân tích bài đọc và trích xuất từ vựng liên quan đến từ khóa chính"""
    config = load_config()
    note = editor.note
    
    # Kiểm tra trường Word và Reading
    if "Word" not in note or not (note["Word"] or '').strip():
        tooltip("⚠️ Vui lòng nhập từ khóa vào trường 'Word' trước")
        return
        
    if "Reading" not in note or not (note["Reading"] or '').strip():
        tooltip("⚠️ Không tìm thấy dữ liệu bài đọc trong trường 'Reading'")
        return
        
    keyword = (note["Word"] or '').strip()
    reading_content = note["Reading"]
    
    # Kiểm tra xem có phải là JSON không
    try:
        reading_data = json.loads(reading_content)
        if isinstance(reading_data, dict) and "content" in reading_data:
            reading_text = reading_data["content"]
        else:
            reading_text = reading_content
    except:
        reading_text = reading_content
    
    if not reading_text.strip():
        tooltip("⚠️ Nội dung bài đọc trống")
        return
        
    tooltip("⏳ Đang phân tích từ vựng liên quan từ bài đọc...")
    
    def worker():
        return analyze_related_reading_vocabulary(keyword, reading_text, config)
    
    def on_data_received(future):
        try:
            success, result = future.result()
            if success:
                # Điền dữ liệu vào các trường mới (JSON gọn cho tab Áp dụng)
                set_reading_vocab_fields(note, result)
                
                editor.loadNote()
                tooltip("✅ Đã tạo từ vựng liên quan từ bài đọc!")
            else:
                showCritical(f"❌ Lỗi phân tích bài đọc: {result}")
        except Exception as e:
            showCritical(f"❌ Lỗi xử lý: {str(e)}")
    
    mw.taskman.run_in_background(worker, on_data_received)

def analyze_related_reading_vocabulary(keyword: str, reading_text: str, config: dict):
    """Phân tích bài đọc để trích xuất từ vựng liên quan (Đã update Key Rotation)"""
    prompt = f"""
Hãy phân tích bài đọc sau và trích xuất các từ vựng, cấu trúc câu LIÊN QUAN ĐẾN TỪ KHÓA "{keyword}".

Từ khóa: {keyword}
Bài đọc:
{reading_text}

YÊU CẦU:
1. Tìm đúng 5 từ/cụm từ trong bài đọc có liên quan đến từ khóa "{keyword}" (ưu tiên cụm từ, collocation; cùng chủ đề, đồng nghĩa/trái nghĩa, cùng họ từ, v.v.)
2. Tìm đúng 2 cấu trúc câu trong bài đọc có sử dụng hoặc liên quan đến từ khóa "{keyword}"
3. Giải thích rõ mối liên hệ giữa các từ vựng/cấu trúc với từ khóa chính

Định dạng JSON:
{{
    "vocabulary": [
        {{
            "word": "từ vựng liên quan",
            "base_form": "dạng gốc", 
            "pos": "loại từ",
            "pronunciation": "phiên âm",
            "meaning_vi": "nghĩa tiếng Việt",
            "relation_to_keyword": "MỐI LIÊN HỆ với từ '{keyword}' (cùng chủ đề, đồng nghĩa, trái nghĩa, v.v.)",
            "example_from_reading": "ví dụ từ bài đọc",
            "translation": "bản dịch ví dụ"
        }}
    ],
    "structures": [
        {{
            "structure": "cấu trúc câu liên quan",
            "explanation_vi": "giải thích cách dùng và liên quan đến '{keyword}'",
            "relation_to_keyword": "MỐI LIÊN HỆ với từ '{keyword}'",
            "example_from_reading": "ví dụ từ bài đọc",
            "translation": "bản dịch ví dụ"
        }}
    ]
}}

Chỉ trả về JSON, không có text nào khác.
"""
    # CẬP NHẬT: Sử dụng URL Template cho Key Rotation
    model = config.get("model", GEMINI_DEFAULT_MODEL)
    url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        # GỌI QUA HÀM XOAY VÒNG KEY
        success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout=60)
        
        if not success:
            return (False, f"Lỗi API: {result}")
            
        response = result
        raw_response = response.json()
        
        if "candidates" not in raw_response or not raw_response["candidates"]:
             return (False, "Không nhận được phản hồi từ Gemini")

        content_text = raw_response["candidates"][0]["content"]["parts"][0]["text"]
        
        # Trích xuất JSON từ response
        json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                vocab_data = json.loads(json_str)
                return (True, vocab_data)
            except json.JSONDecodeError:
                 return (False, "Lỗi parse JSON phân tích bài đọc liên quan")
        else:
            return (False, "Không tìm thấy dữ liệu JSON trong phản hồi")
            
    except Exception as e:
        return (False, f"Lỗi kết nối: {str(e)}")

# ========== CHỨC NĂNG CHO BROWSER ==========
def run_related_vocab_for_browser(browser: Browser):
    """Chạy tạo từ vựng liên quan cho nhiều thẻ trong browser"""
    config = load_config()
    nids = browser.selected_notes()
    if not nids:
        tooltip("Vui lòng chọn ít nhất một thẻ.")
        return
        
    def worker():
        updated_count = 0
        failed_notes = []
        
        mw.progress.start(label="Đang tạo từ vựng liên quan từ bài đọc...", max=len(nids))
        
        for i, nid in enumerate(nids):
            note = mw.col.get_note(nid)
            keyword = note["Word"] if "Word" in note else ""
            reading_content = note["Reading"] if "Reading" in note else ""
            
            mw.progress.update(label=f"Đang xử lý: {keyword}", value=i)
            
            if "Word" in note and keyword.strip() and "Reading" in note and reading_content.strip():
                try:
                    # Kiểm tra xem có phải là JSON không
                    try:
                        reading_data = json.loads(reading_content)
                        if isinstance(reading_data, dict) and "content" in reading_data:
                            reading_text = reading_data["content"]
                        else:
                            reading_text = reading_content
                    except:
                        reading_text = reading_content
                    
                    if reading_text.strip():
                        result = analyze_related_reading_vocabulary(keyword, reading_text, config)
                        if isinstance(result, tuple) and len(result) == 2:
                            success, vocab_data = result
                            if success:
                                set_reading_vocab_fields(note, vocab_data)
                                
                                mw.col.update_note(note)
                                updated_count += 1
                            else:
                                failed_notes.append(f"{keyword} (lỗi: {vocab_data})")
                        else:
                            failed_notes.append(f"{keyword} (kết quả không hợp lệ)")
                    else:
                        failed_notes.append(f"{keyword} (bài đọc trống)")
                except Exception as e:
                    failed_notes.append(f"{keyword} (lỗi: {str(e)})")
            else:
                failed_notes.append(f"{keyword} (thiếu trường Word hoặc Reading)")
                
        mw.progress.finish()
        return updated_count, failed_notes
        
    def on_done(future):
        try:
            updated_count, failed_notes = future.result()
            message = f"Hoàn tất! Đã cập nhật {updated_count} / {len(nids)} thẻ."
            
            if failed_notes:
                failed_list_str = "\n".join(failed_notes)
                message += f"\n\n❌ Các thẻ sau không thể xử lý:\n{failed_list_str}"
                
            showInfo(message)
            browser.search()
        except Exception as e:
            showCritical(f"Có lỗi xảy ra: {e}")
            
    mw.taskman.run_in_background(worker, on_done)

# ========== MODIFIED: OPTIMIZED BROWSER ENGINE ==========
# ========== CẬP NHẬT: OPTIMIZED BROWSER ENGINE (HỖ TRỢ GLOBAL CONTEXT) ==========
class OptimizedBrowserEngine:
    """
    Engine xử lý tối ưu cho các note đã chọn trong Browser.
    Hỗ trợ Global Context & Definition fallback (Tương tự Batch Add).
    """
    
    def __init__(self, config, nids, batch_size=10, delay=5, max_retries=3, 
                 global_context="", global_def_vi="", auto_image=True):
        self.config = config
        self.nids = nids
        self.batch_size = batch_size
        self.delay = delay
        self.max_retries = max_retries
        # Lưu thông tin Global (nhập từ Dialog)
        self.global_context = global_context.strip()
        self.global_def_vi = global_def_vi.strip()
        self.auto_image = auto_image
        
        self.results = {
            'total_words': len(nids), 'processed': 0, 'succeeded': 0, 'failed': [], 
            'spelling_corrections': [], 'retry_success': 0, 'batches_completed': 0,
            'total_batches': (len(nids) + batch_size - 1) // batch_size if len(nids) > 0 else 0
        }
        
        self.progress_data = {'start_time': datetime.now()}

    def _calculate_eta(self):
        if self.results['processed'] == 0: return "Đang tính..."
        elapsed = (datetime.now() - self.progress_data['start_time']).total_seconds()
        
        # Fix lỗi chia cho 0
        if elapsed <= 0.001: return "Đang tính..."
            
        speed = self.results['processed'] / elapsed
        if speed > 0:
            remaining = (self.results['total_words'] - self.results['processed']) / speed
            return f"{int(remaining // 60)} phút {int(remaining % 60)} giây"
        return "Đang tính..."

    def _process_word_with_retry(self, word, context=""):
        if hasattr(self, 'progress_dialog') and self.progress_dialog.cancelled:
            return (False, "Cancelled", word)

        # LOGIC ƯU TIÊN CONTEXT:
        # Nếu thẻ có Context riêng -> Dùng nó.
        # Nếu thẻ không có -> Dùng Global Context.
        final_context = context if context else self.global_context

        for attempt in range(self.max_retries + 1):
            if hasattr(self, 'progress_dialog') and self.progress_dialog.cancelled:
                return (False, "Cancelled", word)

            try:
                if attempt > 0: 
                    import time
                    time.sleep(attempt * 2)
                
                # Gọi Gemini với Context đã xác định
                result = get_gemini_data(word, self.config, final_context)
                
                if isinstance(result, tuple) and len(result) == 2:
                    status, data = result
                    if status == "spelling_correction":
                        # Tự động chấp nhận sửa lỗi chính tả
                        result = get_gemini_data(data, self.config, final_context)
                        if isinstance(result, tuple) and result[0] == True:
                            self.results['spelling_corrections'].append(f"'{word}' → '{data}'")
                            return (True, result[1], data) # Trả về từ đã sửa
                    elif status == True:
                        if attempt > 0: self.results['retry_success'] += 1
                        return (True, data, word)
            except: pass
            
            if attempt < self.max_retries: 
                import time
                time.sleep(3)
        return (False, "Lỗi API", word)

    def _process_batch(self, batch_nids, batch_number):
        batch_results = {'succeeded': 0, 'failed': []}
        
        for i, nid in enumerate(batch_nids):
            if hasattr(self, 'progress_dialog') and self.progress_dialog.cancelled:
                return batch_results

            self.results['processed'] += 1
            eta = self._calculate_eta()
            
            try:
                note = mw.col.get_note(nid)
                # Lấy Word
                word = get_note_field_value(note, ["Word", "Từ vựng", "Keyword", "Thuật ngữ"])
                if not word and "Word" in note: word = note["Word"]
                
                # Lấy Context hiện tại trong thẻ
                context_val = get_note_field_value(note, ["Context", "Ngữ cảnh", "Topic"])
                
                if not word:
                    batch_results['failed'].append(f"Card ID {nid} (No Word)")
                    self.results['failed'].append(f"Card ID {nid}")
                    continue

                progress_label = f"🔄 Batch {batch_number}: {word}"
                
                if self.results['total_words'] > 0:
                    percent = int((self.results['processed'] / self.results['total_words']) * 100)
                else:
                    percent = 0
                    
                mw.taskman.run_on_main(lambda p=percent, lbl=f"{progress_label}\n⏱️ Còn lại: {eta}":
                                       self.progress_dialog.update(p, lbl))
                
                # 1. Xử lý Text
                success, data, processed_word = self._process_word_with_retry(word, context_val)
                
                if hasattr(self, 'progress_dialog') and self.progress_dialog.cancelled:
                    return batch_results

                if success:
                    # LOGIC GHI ĐÈ / ĐIỀN DỮ LIỆU
                    
                    # A. Nếu có Global Definition VN -> Ghi đè vào kết quả
                    if self.global_def_vi:
                        data['definition_vi'] = self.global_def_vi
                        data['Definition_VI'] = self.global_def_vi
                    
                    # B. Nếu thẻ chưa có Context mà dùng Global Context -> Lưu vào thẻ luôn
                    if not context_val and self.global_context:
                        data['context'] = self.global_context
                        data['Context'] = self.global_context

                    # Điền dữ liệu vào note
                    fill_note_with_data(note, data)
                    mw.col.update_note(note)
                    
                    # 2. Xử lý Ảnh (Nếu bật auto_image)
                    if self.auto_image:
                        if hasattr(self, 'progress_dialog') and self.progress_dialog.cancelled:
                            return batch_results

                        mw.taskman.run_on_main(lambda p=percent, lbl=f"🎨 Đang vẽ minh họa cho: {processed_word}...":
                                               self.progress_dialog.update(p, lbl))
                        
                        try:
                            if 'handle_image_generation_and_save' in globals():
                                # Ưu tiên image_query từ Gemini
                                image_prompt = data.get("image_query", data.get("definition_en", processed_word))
                                
                                # Xây dựng context cho ảnh (Kết hợp Context thẻ/chung + Nghĩa VN)
                                final_context = context_val if context_val else self.global_context
                                def_vi = data.get("definition_vi", "")
                                pos_type = data.get("part_of_speech", "")
                                
                                img_context_parts = []
                                if final_context: img_context_parts.append(f"Context: {final_context}")
                                if def_vi: img_context_parts.append(f"Meaning: {def_vi}")
                                img_context_str = ". ".join(img_context_parts)

                                img_tag = handle_image_generation_and_save(
                                    keyword=processed_word,
                                    config=self.config,
                                    definition_en=image_prompt,
                                    context=img_context_str,
                                    pos_type=pos_type
                                )
                                
                                if img_tag:
                                    target_fields = ["Image", "Picture", "Hình ảnh", "Minh họa"]
                                    if "Image" in note: note["Image"] = img_tag
                                    else:
                                        for f in target_fields:
                                            if f in note:
                                                note[f] = img_tag
                                                break
                                    mw.col.update_note(note)
                        except: pass
                    
                    batch_results['succeeded'] += 1
                    self.results['succeeded'] += 1
                else:
                    batch_results['failed'].append(word)
                    self.results['failed'].append(word)

            except Exception as e:
                batch_results['failed'].append(f"Error {nid}: {e}")
                self.results['failed'].append(f"Error {nid}")
            
            # Delay
            if i < len(batch_nids) - 1: 
                import time
                for _ in range(self.delay):
                    if hasattr(self, 'progress_dialog') and self.progress_dialog.cancelled:
                        return batch_results
                    time.sleep(1)
            
        self.results['batches_completed'] += 1
        return batch_results

    def run(self, progress_dialog):
        self.progress_dialog = progress_dialog
        batches = [self.nids[i:i + self.batch_size] for i in range(0, len(self.nids), self.batch_size)]
        
        stopped_early = False
        
        for i, batch in enumerate(batches, 1):
            if progress_dialog and progress_dialog.cancelled: 
                stopped_early = True
                break
            
            self._process_batch(batch, i)
            
            if progress_dialog and progress_dialog.cancelled: 
                stopped_early = True
                break
                
            if i < len(batches): 
                import time
                for _ in range(self.delay):
                    if progress_dialog and progress_dialog.cancelled:
                        stopped_early = True
                        break
                    time.sleep(1)
                if stopped_early: break
        
        self.results['stopped_early'] = stopped_early
        return self.results
# ========== OPTIMIZED BATCH ADD DIALOG (CẬP NHẬT UI CÓ TRƯỜNG NHẬP LIỆU) ==========
class OptimizedBatchAddDialog(QDialog):
    """Dialog thêm từ hàng loạt tối ưu - Giao diện Bảng + Global Settings"""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("🚀 Optimized Batch Add (Advanced)")
        self.setMinimumWidth(1000) # Mở rộng bề ngang ra chút để chứa 4 cột cho thoải mái
        self.setMinimumHeight(650)
        self.config = load_config()
        
        layout = QVBoxLayout(self)
        
        # Title
        title_label = QLabel("🚀 Tối ưu hóa thêm từ hàng loạt với Gemini")
        title_label.setStyleSheet("font-weight: bold; font-size: 18px; margin-bottom: 5px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        img_status = "BẬT" if self.config.get("auto_image_gen", True) else "TẮT"
        img_color = "#2E7D32" if self.config.get("auto_image_gen", True) else "#c62828"
        img_status_label = QLabel(f"🎨 Chế độ tạo ảnh tự động đang: <b style='color:{img_color}'>{img_status}</b>")
        img_status_label.setStyleSheet("font-size: 13px; margin: 0 0 10px 0;")
        img_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(img_status_label)
        
        # --- GLOBAL SETTINGS SECTION (1 Ô DÙNG CHUNG) ---
        global_group = QGroupBox("🌐 Cài đặt chung (Áp dụng cho tất cả các từ, trừ khi có tùy chỉnh riêng)")
        global_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #2196F3; border-radius: 5px; margin-top: 10px; padding-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: #1976D2; }")
        global_layout = QHBoxLayout()
        
        # Global Context
        self.global_context_input = QLineEdit()
        self.global_context_input.setPlaceholderText("VD: Medical, IT... (Để trống nếu muốn tự động)")
        global_layout.addWidget(QLabel("Global Context:"))
        global_layout.addWidget(self.global_context_input)
        
        # Global Def VN
        self.global_def_input = QLineEdit()
        self.global_def_input.setPlaceholderText("VD: Sự phát triển... (Để trống nếu muốn tự động)")
        global_layout.addWidget(QLabel("Global Def VN:"))
        global_layout.addWidget(self.global_def_input)
        
        global_group.setLayout(global_layout)
        layout.addWidget(global_group)
        
        # --- TABLE SECTION (TÙY CHỈNH RIÊNG) ---
        table_group = QGroupBox("📝 Danh sách từ và tùy chỉnh chi tiết")
        table_layout = QVBoxLayout()
        
        # Toolbar buttons
        toolbar_layout = QHBoxLayout()
        
        add_btn = QPushButton("➕ Thêm dòng")
        add_btn.clicked.connect(self.add_row)
        toolbar_layout.addWidget(add_btn)
        
        paste_btn = QPushButton("📋 Paste từ Clipboard")
        paste_btn.setToolTip("Dán danh sách từ. Hỗ trợ nhiều dòng.")
        paste_btn.clicked.connect(self.paste_from_clipboard)
        paste_btn.setStyleSheet("background-color: #e3f2fd; color: #1565c0;")
        toolbar_layout.addWidget(paste_btn)
        
        clear_btn = QPushButton("🗑️ Xóa hết")
        clear_btn.clicked.connect(self.clear_table)
        clear_btn.setStyleSheet("color: #c62828;")
        toolbar_layout.addWidget(clear_btn)
        
        toolbar_layout.addStretch()
        self.count_label = QLabel("Số lượng: 0")
        toolbar_layout.addWidget(self.count_label)
        
        table_layout.addLayout(toolbar_layout)
        
        # --- [ĐÃ SỬA] TABLE WIDGET CHÍNH THỨC VỚI 4 CỘT ---
        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Từ vựng (Word)", "Context (Ghi đè Global)", "Định nghĩa VN (Ghi đè Global)", "IPA Riêng (Ghi đè)"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents) # Word vừa khít
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch) # Context co giãn
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch) # Def co giãn
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch) # IPA co giãn
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setAlternatingRowColors(True)
        table_layout.addWidget(self.table)
        
        table_group.setLayout(table_layout)
        layout.addWidget(table_group)
        
        # Settings
        settings_group = QGroupBox("⚙️ Cài đặt batch")
        settings_layout = QVBoxLayout()
        
        deck_layout = QHBoxLayout()
        deck_layout.addWidget(QLabel("Bộ thẻ:"))
        self.deck_combo = QComboBox()
        self.refresh_deck_list()
        deck_layout.addWidget(self.deck_combo)
        
        self.new_deck_btn = QPushButton("➕")
        self.new_deck_btn.setFixedWidth(40)
        self.new_deck_btn.clicked.connect(self.create_new_deck)
        deck_layout.addWidget(self.new_deck_btn)
        settings_layout.addLayout(deck_layout)

        # Note type selector
        note_type_layout = QHBoxLayout()
        note_type_layout.addWidget(QLabel("Loại thẻ:"))
        self.note_type_combo = QComboBox()
        self.refresh_note_type_list()
        note_type_layout.addWidget(self.note_type_combo)
        settings_layout.addLayout(note_type_layout)
        
        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("Batch Size:"))
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 50)
        self.batch_size_spin.setValue(10)
        param_layout.addWidget(self.batch_size_spin)

        param_layout.addWidget(QLabel("Delay (s):"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(2, 60)
        self.delay_spin.setValue(5)
        param_layout.addWidget(self.delay_spin)
        settings_layout.addLayout(param_layout)
        
        cb_layout = QHBoxLayout()
        self.retry_spin = QSpinBox()
        self.retry_spin.setRange(0, 10)
        self.retry_spin.setValue(3)
        cb_layout.addWidget(QLabel("Retries:"))
        cb_layout.addWidget(self.retry_spin)
        
        self.spell_check_cb = QCheckBox("Sửa lỗi chính tả")
        self.spell_check_cb.setChecked(True)
        cb_layout.addWidget(self.spell_check_cb)
        
        self.save_progress_cb = QCheckBox("Lưu tiến trình")
        self.save_progress_cb.setChecked(True)
        cb_layout.addWidget(self.save_progress_cb)
        settings_layout.addLayout(cb_layout)

        mode_layout = QHBoxLayout()
        mode_layout.addWidget(QLabel("Cách thêm:"))
        self.card_mode_combo = QComboBox()
        self.card_mode_combo.addItem("🪶 Thêm từ nhanh: từ, IPA, loại từ, nghĩa (lấy ở kho từ, vài giây)", True)
        self.card_mode_combo.addItem("✨ Thêm chi tiết: có thêm ví dụ, bài đọc, bài tập, ảnh (AI viết, khoảng 1 phút/từ)", False)
        self.card_mode_combo.setToolTip("Thêm từ nhanh xong, lúc nào cần thì bấm ✨ Thêm chi tiết: trên thẻ, trong Browse hoặc ở bảng báo cáo.")
        mode_layout.addWidget(self.card_mode_combo)
        settings_layout.addLayout(mode_layout)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("🚀 Bắt đầu xử lý")
        self.start_btn.setStyleSheet("background: #27ae60; color: white; padding: 12px; font-weight: bold; font-size: 14px;")
        self.start_btn.clicked.connect(self.start_processing)
        
        cancel_btn = QPushButton("Đóng")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        # Khởi tạo bảng với 1 dòng trống
        self.add_row()

    def refresh_deck_list(self):
        self.deck_combo.clear()
        all_decks = sorted(mw.col.decks.all_names())
        self.deck_combo.addItems(all_decks)
        current_deck_name = mw.col.decks.current()['name']
        self.deck_combo.setCurrentText(current_deck_name)

    def refresh_note_type_list(self):
        self.note_type_combo.clear()
        all_models = sorted([m['name'] for m in mw.col.models.all()])
        self.note_type_combo.addItems(all_models)
        current_model_name = mw.col.models.current()['name']
        self.note_type_combo.setCurrentText(current_model_name)
    
    def create_new_deck(self):
        new_name, ok = QInputDialog.getText(self, "Tạo bộ thẻ mới", "Nhập tên bộ thẻ mới:")
        if ok and new_name:
            mw.col.decks.id(new_name)
            self.refresh_deck_list()
            self.deck_combo.setCurrentText(new_name)
    
    def add_row(self):
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.update_count()
        
    def clear_table(self):
        self.table.setRowCount(0)
        self.add_row()
        self.update_count()
        
    def paste_from_clipboard(self):
        from aqt.qt import QApplication
        clipboard = QApplication.clipboard()
        text = clipboard.text()
        
        if not text:
            return
            
        rows = [r for r in text.split('\n') if r.strip()]
        if not rows:
            return
            
        current_row = self.table.rowCount()
        # Nếu dòng cuối cùng trống, dùng dòng đó luôn
        if current_row > 0:
            last_item = self.table.item(current_row - 1, 0)
            if not last_item or not last_item.text().strip():
                current_row -= 1
        
        for row_text in rows:
            # Tự động tách tab hoặc dấu phẩy (ưu tiên tab)
            if '\t' in row_text:
                parts = row_text.split('\t')
            else:
                parts = [row_text] # Mặc định chỉ có word
                
            self.table.insertRow(current_row)
            
            # Fill Word
            if len(parts) > 0:
                self.table.setItem(current_row, 0, QTableWidgetItem(parts[0].strip()))
            # Fill Context
            if len(parts) > 1:
                self.table.setItem(current_row, 1, QTableWidgetItem(parts[1].strip()))
            # Fill Definition
            if len(parts) > 2:
                self.table.setItem(current_row, 2, QTableWidgetItem(parts[2].strip()))
            # Fill IPA
            if len(parts) > 3:
                self.table.setItem(current_row, 3, QTableWidgetItem(parts[3].strip()))
            current_row += 1
            
        self.update_count()
        
    def update_count(self):
        self.count_label.setText(f"Số lượng: {self.table.rowCount()}")
        
    def get_items(self):
        """Lấy dữ liệu từ bảng dưới dạng list of dicts"""
        items = []
        for row in range(self.table.rowCount()):
            word_item = self.table.item(row, 0)
            if not word_item or not word_item.text().strip():
                continue
                
            word = word_item.text().strip()
            
            context_item = self.table.item(row, 1)
            context = context_item.text().strip() if context_item else ""
            
            def_item = self.table.item(row, 2)
            definition_vi = def_item.text().strip() if def_item else ""
            
            ipa_item = self.table.item(row, 3)
            ipa_val = ipa_item.text().strip() if ipa_item else ""
            
            items.append({
                "word": word,
                "context": context,
                "definition_vi": definition_vi,
                "ipa": ipa_val
            })
        return items

    def start_processing(self):
        items = self.get_items()
        if not items:
            showCritical("Vui lòng nhập ít nhất một từ vào bảng!")
            return
        self.items_to_process = items 
        # Lưu lại thông tin global inputs
        self.global_context_val = self.global_context_input.text()
        self.global_def_val = self.global_def_input.text()
        self.accept()

# ========== MỚI: DIALOG CẤU HÌNH CHO BROWSER (Giống Batch Add) ==========
class OptimizedBrowserDialog(QDialog):
    """Dialog cấu hình cho việc tối ưu hóa thẻ trong Browser"""
    def __init__(self, parent=None, total_cards=0):
        super().__init__(parent)
        self.setWindowTitle(f"🚀 Tối ưu hóa {total_cards} thẻ đã chọn")
        self.setMinimumWidth(500)
        self.config = load_config()
        
        layout = QVBoxLayout(self)
        
        # Header
        title_label = QLabel(f"🚀 Cấu hình xử lý {total_cards} thẻ")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px; color: #2196F3;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # --- GLOBAL SETTINGS ---
        global_group = QGroupBox("🌐 Dữ liệu chung (Áp dụng nếu thẻ chưa có)")
        global_group.setStyleSheet("QGroupBox { font-weight: bold; border: 1px solid #2196F3; border-radius: 5px; margin-top: 10px; padding-top: 10px; } QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 3px; color: #1976D2; }")
        global_layout = QVBoxLayout()
        
        # Global Context
        self.global_context_input = QLineEdit()
        self.global_context_input.setPlaceholderText("VD: Medical, IT... (Sẽ dùng nếu thẻ chưa có Context)")
        global_layout.addWidget(QLabel("Global Context:"))
        global_layout.addWidget(self.global_context_input)
        
        # Global Def VN
        self.global_def_input = QLineEdit()
        self.global_def_input.setPlaceholderText("VD: Nghĩa tiếng Việt cố định (Sẽ ghi đè)")
        global_layout.addWidget(QLabel("Global Def VN:"))
        global_layout.addWidget(self.global_def_input)
        
        global_group.setLayout(global_layout)
        layout.addWidget(global_group)
        
        # --- BATCH SETTINGS ---
        settings_group = QGroupBox("⚙️ Cấu hình chạy")
        settings_layout = QVBoxLayout()
        
        param_layout = QHBoxLayout()
        param_layout.addWidget(QLabel("Batch Size:"))
        self.batch_size_spin = QSpinBox()
        self.batch_size_spin.setRange(1, 50)
        self.batch_size_spin.setValue(10)
        param_layout.addWidget(self.batch_size_spin)

        param_layout.addWidget(QLabel("Delay (s):"))
        self.delay_spin = QSpinBox()
        self.delay_spin.setRange(2, 60)
        self.delay_spin.setValue(2)
        param_layout.addWidget(self.delay_spin)
        settings_layout.addLayout(param_layout)
        
        cb_layout = QHBoxLayout()
        self.auto_image_cb = QCheckBox("Tự động tạo ảnh (Pollinations)")
        self.auto_image_cb.setChecked(self.config.get("auto_image_gen", True))
        cb_layout.addWidget(self.auto_image_cb)
        
        settings_group.setLayout(settings_layout)
        layout.addWidget(settings_group)
        
        # Buttons
        button_layout = QHBoxLayout()
        self.start_btn = QPushButton("🚀 Bắt đầu ngay")
        self.start_btn.setStyleSheet("background: #27ae60; color: white; padding: 10px; font-weight: bold;")
        self.start_btn.clicked.connect(self.accept)
        
        cancel_btn = QPushButton("Hủy")
        cancel_btn.clicked.connect(self.reject)
        
        button_layout.addWidget(self.start_btn)
        button_layout.addWidget(cancel_btn)
        layout.addLayout(button_layout)
        
        self.setLayout(layout)
# ========== CÁC HÀM RUNNER (CẬP NHẬT TRUYỀN THAM SỐ) ==========
def show_optimized_batch_dialog():
    dialog = OptimizedBatchAddDialog(mw)
    if dialog.exec():
        items = dialog.items_to_process
        global_context = dialog.global_context_val
        global_def_vi = dialog.global_def_val
        
        deck_name = dialog.deck_combo.currentText()
        note_type_name = dialog.note_type_combo.currentText()
        batch_size = dialog.batch_size_spin.value()
        delay = dialog.delay_spin.value()
        max_retries = dialog.retry_spin.value()
        auto_spell_correction = dialog.spell_check_cb.isChecked()
        save_progress = dialog.save_progress_cb.isChecked()
        lite_mode = bool(dialog.card_mode_combo.currentData())

        run_optimized_batch_add(items, deck_name, batch_size, delay, max_retries,
                               auto_spell_correction, save_progress,
                               global_context, global_def_vi,
                               note_type_name=note_type_name, lite_mode=lite_mode)
# ========== MODIFIED: MAIN PROCESSING FUNCTION ==========
# ========== BẢNG BÁO CÁO SAU KHI THÊM TỪ HÀNG LOẠT ==========
def _entry_status(entry):
    """Chuỗi trạng thái của một từ trong bảng báo cáo."""
    if entry.get("failed"):
        return "❌ " + (entry.get("error") or "Thất bại")[:120]
    status = "✅ Đạt" if not entry.get("issues") else "⚠️ " + "; ".join(entry["issues"])
    if entry.get("lite"):
        source = entry.get("source") or "kho gốc"
        if source == "kho gốc":
            status = "🪶 Lấy ở kho từ · " + status
        elif source.startswith("kho gốc thô"):
            status = "🪶 Lấy ở kho từ (bản chưa chuẩn vì AI đang lỗi) · " + status
        else:
            status = "🪶 Từ chưa có trong kho, AI tra giúp · " + status
    if entry.get("original") and normalize_word_for_compare(entry["original"]) != normalize_word_for_compare(entry["word"]):
        status = f"✏️ sửa chính tả từ '{entry['original']}' · " + status
    return status

IMAGE_FIELD_NAMES = ["Image", "Picture", "Hình ảnh", "Minh họa"]

def _save_notes_and_refresh(notes):
    """Ghi các note đã sửa (gọi ở luồng chính). Dùng thao tác update_notes của Anki để thẻ đang ôn,
    Browse... tự vẽ lại ngay; bản Anki cũ không có thì ghi thẳng rồi reset."""
    if not notes:
        return
    try:
        from aqt.operations.note import update_notes
        update_notes(parent=mw, notes=notes).run_in_background()
    except ImportError:
        for note in notes:
            mw.col.update_note(note)
        mw.reset()

def fill_full_notes(jobs, on_done=None, on_images_done=None):
    """✨ Điền đầy đủ cho thẻ ĐÃ CÓ (thẻ nhẹ, thẻ cần điền lại): AI viết đủ mọi mục rồi ghi đè vào thẻ cũ.
    jobs: [{'nid', 'word', 'context', 'forced_vi'}]. Giữ IPA đang có trên thẻ (IPA kho gốc lấy từ Wiktionary).
    Chạy 2 bước nền: (1) phần chữ -> ghi thẻ -> on_done(outcomes), outcomes[i] = (True, data) | (False, lỗi);
    (2) thẻ chưa có ảnh thì vẽ ảnh (nếu bật tự tạo ảnh) -> on_images_done({nid: True/False})."""
    config = load_config()

    def write_text():
        outcomes, filled = [], []
        for job in jobs:
            try:
                note = mw.col.get_note(job["nid"])
            except Exception as ex:
                outcomes.append((False, f"không tìm thấy thẻ: {ex}"))
                continue
            res = get_gemini_data(job["word"], config, job.get("context", ""), job.get("forced_vi", ""))
            if not (isinstance(res, tuple) and res[0] is True):
                reason = res[1] if isinstance(res, tuple) else res
                if isinstance(res, tuple) and res[0] == "spelling_correction":
                    reason = f"AI cho là sai chính tả, gợi ý '{reason}'"
                outcomes.append((False, str(reason)))
                continue
            data = res[1]
            if job.get("forced_vi"):
                data["definition_vi"] = job["forced_vi"]
            kept_ipa = load_ipa_memory().get(job["word"].lower()) or (clean_field_text(note["IPA"]) if "IPA" in note else "")
            if kept_ipa:
                data["ipa"] = kept_ipa
            fill_note_with_data(note, data)
            filled.append((note, data))
            outcomes.append((True, data))
        return outcomes, filled

    def text_done(future):
        try:
            outcomes, filled = future.result()
        except Exception as ex:
            showCritical(f"❌ Lỗi khi thêm chi tiết: {ex}")
            return
        _save_notes_and_refresh([note for note, _ in filled])
        if on_done:
            on_done(outcomes)
        if not config.get("auto_image_gen", True):
            return
        image_fields = lambda n: [f for f in IMAGE_FIELD_NAMES if f in n]
        need_image = [(n, d) for n, d in filled
                      if image_fields(n) and not any(clean_field_text(n[f]) for f in image_fields(n))]
        if need_image:
            mw.taskman.run_in_background(lambda: draw_images(need_image), images_done)

    def draw_images(pairs):
        drawn = {}
        for note, data in pairs:
            ok, image_data = generate_image_from_gemini(keyword=data.get("keyword") or note["Word"], config=config,
                                                        definition_en=data.get("image_query") or data.get("definition_en", ""),
                                                        context=data.get("context", ""), pos_type=data.get("part_of_speech", ""))
            drawn[note.id] = (note, bool(ok and put_image_into_note(note, save_generated_image(note["Word"], image_data))))
        return drawn

    def images_done(future):
        try:
            drawn = future.result()
        except Exception as ex:
            tooltip(f"⚠️ Lỗi vẽ ảnh: {ex}")
            return
        _save_notes_and_refresh([note for note, ok in drawn.values() if ok])
        if on_images_done:
            on_images_done({nid: ok for nid, (_, ok) in drawn.items()})

    mw.taskman.run_in_background(write_text, text_done)

def refill_report_entries(entries, on_finish, on_images=None):
    """Điền đầy đủ / điền lại các thẻ trong bảng báo cáo (ghi đè thẻ cũ, không tạo thẻ mới)."""
    def done(outcomes):
        for entry, (ok, res) in zip(entries, outcomes):
            if not ok:
                entry["issues"] = [f"điền thất bại: {res[:80]}"]
                continue
            entry.update(pos=clean_field_text(res.get("part_of_speech") or ""),
                         definition_vi=clean_field_text(res.get("definition_vi") or ""),
                         definition_en=clean_field_text(res.get("definition_en") or ""),
                         issues=check_entry_quality(res, vi_given_by_user=bool(entry.get("forced_vi"))),
                         sections=summarize_note_sections(res), lite=False, source="")
        on_finish()

    def images_done(drawn):
        for entry in entries:
            if entry.get("nid") in drawn:
                entry["image"] = "ok" if drawn[entry["nid"]] else "fail"
        (on_images or on_finish)()

    tooltip(f"✨ Đang thêm chi tiết cho {len(entries)} từ...")
    fill_full_notes([{"nid": e["nid"], "word": e["word"], "context": e.get("context", ""), "forced_vi": e.get("forced_vi", "")}
                     for e in entries], done, images_done)

IMAGE_STATUS_LABELS = {"ok": "🖼️ Có", "fail": "❌ Lỗi", "skipped": "⏭️ Bỏ qua", "pending": "⏳ Chưa xong"}

def _percent(part, whole):
    return f"{part}/{whole} ({part / whole * 100:.0f}%)" if whole else "0/0"

def show_batch_report_dialog(results, note_lines="", deck_name=""):
    """Bảng kết quả sau khi thêm hàng loạt:
    - dòng tổng kết 'Chạy hoàn tất x/y (z%)' + tỷ lệ đạt format / cần xem lại / thất bại,
    - % độ đầy đủ của từng mục (IPA, ví dụ, bài đọc, ảnh...),
    - bảng từng từ 'từ (loại từ): nghĩa' kèm trạng thái, mục còn thiếu, ảnh (cuộn ngang được),
    - lượt API còn lại."""
    from aqt.qt import QApplication
    entries = results.get("entries") or []
    total = results.get("total_words", len(entries))
    dlg = QDialog(mw)
    dlg.setWindowTitle("📊 Báo cáo thêm từ hàng loạt")
    dlg.resize(1100, 680)
    dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    layout = QVBoxLayout(dlg)
    summary = QLabel()
    summary.setWordWrap(True)
    summary.setTextFormat(Qt.TextFormat.RichText)
    summary.setStyleSheet("font-size: 14px;")
    layout.addWidget(summary)

    headers = ["Từ (loại từ): Nghĩa", "Định nghĩa EN", "Trạng thái", "Mục còn thiếu", "Ảnh", "Từ bạn nhập"]
    widths = [300, 380, 260, 220, 90, 120]
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setWordWrap(True)
    table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
    table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    header = table.horizontalHeader()
    header.setStretchLastSection(False)
    for col, width in enumerate(widths):
        header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)   # kéo giãn cột được, dư thì cuộn ngang
        table.setColumnWidth(col, width)
    layout.addWidget(table)
    quota = QLabel()
    quota.setWordWrap(True)
    quota.setStyleSheet("color: #37474f; background: #f1f8e9; padding: 8px; border-radius: 6px;")
    layout.addWidget(quota)

    buttons = QHBoxLayout()
    copy_btn = QPushButton("📋 Copy từ cần xem lại / thất bại")
    refill_btn = QPushButton("🔁 Điền lại các từ cần xem lại")
    full_btn = QPushButton("✨ Thêm chi tiết")
    full_btn.setToolTip("Chọn dòng cần thêm (giữ Ctrl hoặc Shift để chọn nhiều dòng).\n"
                        "Không chọn dòng nào thì thêm chi tiết cho tất cả từ vừa thêm nhanh.\n"
                        "AI viết ví dụ, bài đọc, bài tập, ảnh vào chính thẻ đó, không tạo thẻ mới.")
    close_btn = QPushButton("Đóng")
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
    buttons.addWidget(copy_btn)
    buttons.addWidget(refill_btn)
    buttons.addWidget(full_btn)
    buttons.addStretch()
    buttons.addWidget(close_btn)
    layout.addLayout(buttons)

    def need_review():
        return [e for e in entries if not e.get("failed") and e.get("issues") and e.get("nid")]

    def section_line(added):
        """'IPA 100% · Ví dụ 100% · Bài đọc 75% · Ảnh 50%' cho các thẻ đã thêm."""
        counts = {}
        for e in added:
            for label, ok in (e.get("sections") or {}).items():
                have, seen = counts.get(label, (0, 0))
                counts[label] = (have + (1 if ok else 0), seen + 1)
        with_image = [e for e in added if e.get("image")]
        if with_image:
            counts["Ảnh"] = (sum(1 for e in with_image if e["image"] == "ok"), len(with_image))
        parts = []
        for label, (have, seen) in counts.items():
            pct = have / seen * 100 if seen else 0
            color = "#2e7d32" if pct >= 100 else ("#ef6c00" if pct >= 50 else "#c62828")
            parts.append(f"<span style='color:{color}'>{label} <b>{pct:.0f}%</b></span>")
        return " · ".join(parts)

    def render():
        added = [e for e in entries if not e.get("failed")]
        ok = sum(1 for e in added if not e.get("issues"))
        warn = len(need_review())
        failed = sum(1 for e in entries if e.get("failed"))
        fixed = sum(1 for e in added if e.get("original")
                    and normalize_word_for_compare(e["original"]) != normalize_word_for_compare(e["word"]))
        done = len(added)
        if failed == 0 and done == total:
            headline = f"✅ <b>Chạy hoàn tất {done}/{total} từ (100%)</b>, đã thêm đủ {done} thẻ"
        else:
            headline = f"⚠️ <b>Chạy hoàn tất {_percent(done, total)}</b>, đã thêm {done} thẻ, {failed} từ thất bại"
        if deck_name:
            headline += f" vào deck <b>{deck_name}</b>"
        lines = [
            headline,
            f"📋 Đạt format: <b>{_percent(ok, total)}</b> · ⚠️ Cần xem lại: <b>{_percent(warn, total)}</b> · "
            f"❌ Thất bại: <b>{_percent(failed, total)}</b> · ✏️ Sai chính tả thật đã sửa: <b>{fixed}</b>",
        ]
        lite = [e for e in added if e.get("lite")]
        if lite:
            from_dict = sum(1 for e in lite if e.get("source") == "kho gốc")
            line = f"🪶 Thêm từ nhanh: <b>{len(lite)}</b> từ · Lấy ở kho từ thành công: <b>{_percent(from_dict, len(lite))}</b>"
            if from_dict < len(lite):
                line += f" · <b>{len(lite) - from_dict}</b> từ chưa có trong kho nên AI tra giúp"
            lines.append(line)
            lines.append("- Muốn thêm chi tiết (ví dụ, bài đọc, bài tập, ảnh): chọn dòng cần thêm rồi bấm <b>✨ Thêm chi tiết</b>")
        full = [e for e in added if not e.get("lite")]
        if full:
            lines.append("📦 Độ đầy đủ các mục: " + section_line(full))
        if note_lines:
            lines.append(note_lines)
        summary.setText("<br>".join(lines))

        table.setRowCount(len(entries))
        for row, e in enumerate(entries):
            if e.get("failed"):
                cells = [e["word"], "", _entry_status(e), "", "", e.get("original", "")]
            else:
                missing = [label for label, have in (e.get("sections") or {}).items() if not have]
                cells = [f"{e['word']} ({e.get('pos') or '?'}): {e.get('definition_vi') or '-'}",
                         e.get("definition_en", ""), _entry_status(e),
                         "🪶 Chưa có chi tiết" if e.get("lite") else (", ".join(missing) if missing else "✅ Đủ"),
                         IMAGE_STATUS_LABELS.get(e.get("image"), "-"), e.get("original", "")]
            for col, text in enumerate(cells):
                item = QTableWidgetItem(text)
                item.setToolTip(text)
                table.setItem(row, col, item)
        table.resizeRowsToContents()
        refill_btn.setText(f"🔁 Điền lại các từ cần xem lại ({warn})")
        refill_btn.setEnabled(warn > 0)
        full_btn.setText("✨ Thêm chi tiết")
        full_btn.setEnabled(bool(added))
        quota.setText(format_capacity_summary(estimate_gemini_capacity(load_config())))

    def copy_words():
        words = [e["word"] for e in entries if e.get("failed") or e.get("issues")]
        QApplication.clipboard().setText("\n".join(words))
        tooltip(f"✅ Đã copy {len(words)} từ" if words else "Không có từ nào cần xem lại")

    def refill():
        targets = need_review()
        refill_btn.setEnabled(False)
        refill_btn.setText("⏳ Đang điền lại...")
        refill_report_entries(targets, render)

    def fill_full():
        rows = sorted({index.row() for index in table.selectionModel().selectedRows()})
        targets = [entries[r] for r in rows] if rows else [e for e in entries if e.get("lite")]
        targets = [e for e in targets if not e.get("failed") and e.get("nid")]
        if not targets:
            tooltip("Chọn ít nhất 1 dòng đã thêm thẻ (dòng thất bại không điền được)")
            return
        full_btn.setEnabled(False)
        full_btn.setText(f"⏳ Đang thêm chi tiết cho {len(targets)} từ...")
        refill_report_entries(targets, render)

    copy_btn.clicked.connect(copy_words)
    refill_btn.clicked.connect(refill)
    full_btn.clicked.connect(fill_full)
    close_btn.clicked.connect(dlg.accept)
    render()
    dlg.show()
    return dlg

# ========== KIỂM TRA SỨC KHOẺ API KEY ==========
def collect_card_template_keys():
    """Key Gemini nằm trong template thẻ (GEMINI_TTS_API_KEYS) - chỉ đọc để kiểm tra, không sửa."""
    keys = []
    for model in mw.col.models.all():
        for tmpl in model.get("tmpls", []):
            for side in ("qfmt", "afmt"):
                m = re.search(r"GEMINI_TTS_API_KEYS\s*=\s*`([^`]*)`", tmpl.get(side) or "")
                if m:
                    keys += get_key_list(m.group(1))
    return list(dict.fromkeys(keys))

def check_gemini_key(key, model="gemini-3.5-flash-lite"):
    """Gọi thử 1 lượt rất nhỏ bằng model Lite (500 lượt/ngày) để không tốn lượt của bản Flash.
    Trả về (mã trạng thái, chữ hiển thị)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    body = {"contents": [{"parts": [{"text": "Reply OK"}]}], "generationConfig": {"maxOutputTokens": 5}}
    try:
        res = requests.post(url, json=body, timeout=30)
    except Exception as e:
        return "error", f"⚠️ Lỗi mạng: {str(e)[:60]}"
    text = res.text
    if res.status_code == 200:
        record_gemini_call(key, model, "ok")
        return "alive", "✅ Sống"
    if res.status_code == 400 and "API_KEY" in text:
        record_gemini_call(key, model, "dead")
        return "dead", "💀 Chết (key không hợp lệ / đã bị xoá)"
    if res.status_code == 429:
        if "PerDay" in text:
            record_gemini_call(key, model, "exhausted")
            return "exhausted", "⏳ Hết lượt hôm nay"
        return "limited", "⏳ Đang chạm giới hạn theo phút, thử lại sau 1 phút"
    if res.status_code in (403, 404):
        return "unavailable", f"🚫 Không dùng được model {model}"
    if res.status_code >= 500:
        return "busy", "⏳ Google đang quá tải, thử lại sau"
    return "error", f"⚠️ Lỗi {res.status_code}"

def show_gemini_key_health_dialog():
    """Tools → 🩺 Kiểm tra API key: trạng thái từng key (cài đặt add-on + trong thẻ) và lượt còn lại."""
    config = load_config()
    addon_keys = get_key_list("\n".join(config.get("api_keys") or []))
    card_keys = [k for k in collect_card_template_keys() if k not in addon_keys]
    targets = [("Cài đặt add-on", k) for k in addon_keys] + [("Trong thẻ", k) for k in card_keys]
    if not targets:
        showInfo("Chưa có API key nào (Tools → Gemini Editor Settings).")
        return
    tooltip(f"🩺 Đang kiểm tra {len(targets)} key...")

    def worker():
        return [(src, key, check_gemini_key(key)) for src, key in targets]

    def done(future):
        try:
            rows = future.result()
        except Exception as e:
            showCritical(f"❌ Lỗi kiểm tra key: {e}")
            return
        usage = load_gemini_usage()
        capacity = estimate_gemini_capacity(config, addon_keys)
        dlg = QDialog(mw)
        dlg.setWindowTitle("🩺 Kiểm tra API key Gemini")
        dlg.resize(820, 460)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(dlg)
        table = QTableWidget(len(rows), 4)
        table.setHorizontalHeaderLabels(["Nơi dùng", "Key", "Trạng thái", "Đã dùng hôm nay (add-on đếm)"])
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        for row, (src, key, (state, label)) in enumerate(rows):
            kid = _gemini_kid(key)
            used = ", ".join(f"{m.replace('gemini-', '')}: {n}" for slot, n in usage["used"].items()
                             for m in [slot.split("|", 1)[1]] if slot.startswith(kid + "|")) or "-"
            for col, text in enumerate([src, "…" + key[-4:], label, used if src == "Cài đặt add-on" else "(thẻ tự dùng, add-on không đếm)"]):
                table.setItem(row, col, QTableWidgetItem(text))
        layout.addWidget(table)
        dead = sum(1 for _, _, (state, _) in rows if state == "dead")
        info = QLabel(format_capacity_summary(capacity)
                      + (f"\n💀 Có {dead} key chết: nên xoá khỏi danh sách." if dead else "")
                      + "\n🔎 Kiểm tra dùng model Flash-Lite (1 lượt/key) để không tốn lượt của bản Flash.")
        info.setWordWrap(True)
        layout.addWidget(info)
        close_btn = QPushButton("Đóng")
        close_btn.clicked.connect(dlg.accept)
        layout.addWidget(close_btn)
        dlg.show()

    mw.taskman.run_in_background(worker, done)

def run_optimized_batch_add(items, deck_name, batch_size=10, delay=2,
                           max_retries=3, auto_spell_correction=True, save_progress=True,
                           global_context="", global_def_vi="", note_type_name=None, lite_mode=False):
    """Chạy thêm từ hàng loạt tối ưu (lite_mode = thẻ nhẹ: kho gốc + Flash-Lite, không ảnh)"""
    # Select the note type model
    if note_type_name:
        model = mw.col.models.by_name(note_type_name)
        if model is None:
            showCritical(f"Không tìm thấy loại thẻ: {note_type_name}")
            return
        mw.col.models.set_current(model)
    else:
        model = mw.col.models.current()
    model_fields = mw.col.models.field_names(model)
    
    required_fields_check = ["Word", "Definition_VI", "Exercises"]
    missing_fields_check = [f for f in required_fields_check if f not in model_fields]
    if missing_fields_check:
        showCritical("Kiểu thẻ (Note Type) của bạn đang thiếu các trường cần thiết:\n\n" + "\n".join(missing_fields_check))
        return
    
    try:
        progress_dialog = OptimizedBatchProgressDialog(parent=mw, total_words=len(items))
    except NameError:
        progress_dialog = BatchProgressDialog(parent=mw, total=len(items), title="🚀 Adding Words")

    def worker():
        try:
            config = load_config()
            engine = OptimizedBatchAddEngine(
                config, items, deck_name, batch_size, delay, 
                max_retries, auto_spell_correction, save_progress,
                global_context, global_def_vi, lite_mode=lite_mode
            )
            return engine.run(progress_dialog)
        except Exception as e:
            import traceback
            log_error(f"Optimized batch worker: {e}\n{traceback.format_exc()}")
            return None

    def on_done(future):
        try:
            results = future.result()
            if progress_dialog: progress_dialog.close()

            if not results:
                showCritical("❌ Đã xảy ra lỗi trong quá trình xử lý (chi tiết trong editor_error_log.txt)")
                return

            if results.get('stopped_early', False):
                msg = f"🛑 Đã dừng xử lý theo yêu cầu. Đã tạo {results.get('succeeded', 0)} thẻ."
                if save_progress:
                    msg += "\n\n💾 Tiến trình đã được lưu. Vào Tools → 🔄 Tiếp tục tiến trình bị gián đoạn để chạy tiếp."
                showInfo(msg)
                mw.reset()
                return
            
            # Bảng báo cáo từng từ: 'từ (loại từ): nghĩa' + đạt/cần xem lại/thất bại + lượt API còn lại
            notes = []
            if global_context:
                notes.append(f"📌 Global Context: {global_context}")
            if global_def_vi:
                notes.append(f"📌 Global Def VN: {global_def_vi}")
            mw.reset()
            show_batch_report_dialog(results, "<br>".join(notes), deck_name)
            
        except Exception as e:
            if progress_dialog: progress_dialog.close()
            showCritical(f"❌ Lỗi xử lý kết quả: {str(e)}")
    
    from aqt.qt import QMessageBox
    confirm_msg = f"""
🚀 BẮT ĐẦU QUÁ TRÌNH TỐI ƯU

📝 Thông tin:
• Số từ: {len(items)} từ
• Batch size: {batch_size} | Delay: {delay}s
• Cách thêm: {"🪶 Thêm từ nhanh (lấy ở kho từ, không vẽ ảnh)" if lite_mode else "✨ Thêm chi tiết"}
"""
    if global_context: confirm_msg += f"• 📌 Global Context: {global_context}\n"
    if global_def_vi: confirm_msg += f"• 📌 Global Def VN: {global_def_vi}\n"

    confirm_msg += "\nBạn có muốn tiếp tục?"
    
    reply = QMessageBox.question(mw, "Xác nhận tối ưu hóa", confirm_msg, 
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    
    if reply == QMessageBox.StandardButton.Yes:
        progress_dialog.show()
        mw.taskman.run_in_background(worker, on_done)
# ========== UPDATE 4: OPTIMIZED BATCH ADD CLASS (Stop on Cancel & Notification) ==========
from aqt.qt import QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView

def get_progress_dir():
    """Thư mục lưu tiến trình batch. Đặt trong user_files của add-on (Anki giữ lại khi
    update add-on); thư mục cũ nằm thẳng trong addons21 dễ bị Anki nhận nhầm là add-on."""
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "user_files", "gemini_progress")

def _legacy_progress_dir():
    return os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "gemini_progress")

# ========== CLASS ENGINE: THÊM TỪ HÀNG LOẠT (CẬP NHẬT LOGIC ƯU TIÊN) ==========
class OptimizedBatchAddEngine:
    """
    Engine xử lý thêm từ hàng loạt.
    Logic ưu tiên: Dữ liệu riêng từng dòng > Dữ liệu chung (Global) > Để trống (AI tự làm)
    """
    
    def __init__(self, config, items, deck_name, batch_size=10, delay=5, 
                 max_retries=3, auto_spell_correction=True, save_progress=True,
                 global_context="", global_def_vi="", lite_mode=False):
        self.config = config
        self.lite_mode = lite_mode   # thẻ nhẹ: get_lite_card_data thay cho get_gemini_data, không vẽ ảnh
        self.items = items # List of dicts: {'word': '...', 'context': '...', 'definition_vi': '...'}
        self.deck_name = deck_name
        self.batch_size = batch_size
        self.delay = delay
        self.max_retries = max_retries
        self.auto_spell_correction = auto_spell_correction
        self.save_progress = save_progress
        
        # Lưu thông tin chung (Global fallback)
        self.global_context = global_context.strip()
        self.global_def_vi = global_def_vi.strip()

        # Ảnh được vẽ ở luồng phụ, song song với phần chữ (xem _queue_image / _collect_images)
        self._image_pool = None
        self._image_jobs = []

        self.results = {
            'total_words': len(items), 'processed': 0, 'succeeded': 0, 'failed': [],
            'spelling_corrections': [], 'retry_success': 0, 'batches_completed': 0,
            'total_batches': (len(items) + batch_size - 1) // batch_size if len(items) > 0 else 0
        }
        self.progress_data = {'start_time': datetime.now(), 'current_batch': 0, 'words_processed_in_batch': 0}
        self.next_index = 0  # Vị trí từ tiếp theo chưa xử lý xong (dùng cho resume)
        if save_progress: self.progress_file = self._get_progress_file_path()

    def _get_progress_file_path(self):
        progress_dir = get_progress_dir()
        os.makedirs(progress_dir, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        return os.path.join(progress_dir, f"progress_{timestamp}.json")

    def _save_progress(self):
        if not self.save_progress: return
        try:
            progress_info = {
                'results': self.results,
                'remaining_items': self.items[self.next_index:],
                'config': {
                    'deck_name': self.deck_name, 'timestamp': datetime.now().isoformat(),
                    'batch_size': self.batch_size, 'delay': self.delay, 'max_retries': self.max_retries,
                    'global_context': self.global_context, 'global_def_vi': self.global_def_vi,
                    'lite_mode': self.lite_mode,
                }
            }
            with open(self.progress_file, 'w', encoding='utf-8') as f:
                json.dump(progress_info, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"⚠️ Không lưu được tiến trình: {e}")

    def _calculate_eta(self):
        if self.results['processed'] == 0: return "Đang tính..."
        elapsed = (datetime.now() - self.progress_data['start_time']).total_seconds()
        if elapsed <= 0.001: return "Đang tính..."
        
        words_per_second = self.results['processed'] / elapsed
        if words_per_second > 0:
            remaining = (self.results['total_words'] - self.results['processed']) / words_per_second
            return f"{int(remaining // 60)} phút {int(remaining % 60)} giây"
        return "Đang tính..."

    def _process_item_with_retry(self, item):
        word = item['word']
        
        # LOGIC ƯU TIÊN CONTEXT ĐỂ GỬI GEMINI:
        # Riêng > Chung > Rỗng
        specific_context = item.get('context', '').strip()
        context_to_use = specific_context if specific_context else self.global_context
        if self.lite_mode:
            forced_vi = item.get('definition_vi', '').strip() or self.global_def_vi
            fetch = lambda w, cfg, ctx: get_lite_card_data(w, cfg, ctx, forced_vi)
        else:
            fetch = get_gemini_data

        if hasattr(self, 'progress_dialog') and self.progress_dialog and self.progress_dialog.cancelled:
            return (False, "Cancelled", word)

        last_error = "Lỗi API"
        for attempt in range(self.max_retries + 1):
            if hasattr(self, 'progress_dialog') and self.progress_dialog and self.progress_dialog.cancelled:
                return (False, "Cancelled", word)

            try:
                if attempt > 0:
                    time.sleep(attempt * 2)

                # Gọi Gemini với context đã xác định
                result = fetch(word, self.config, context_to_use)

                if isinstance(result, tuple) and len(result) == 2:
                    status, data = result
                    if status == "spelling_correction":
                        if not self.auto_spell_correction:
                            # Không bật tự sửa -> thử lại cũng vô ích
                            self.results['spelling_corrections'].append(f"'{word}' → '{data}'")
                            return (False, f"Sai chính tả, gợi ý: {data}", word)
                        corrected = data
                        result = fetch(corrected, self.config, context_to_use)
                        if isinstance(result, tuple) and result[0] == True:
                            self.results['spelling_corrections'].append(f"'{word}' → '{corrected}'")
                            return (True, result[1], corrected)
                    elif status == True:
                        if attempt > 0: self.results['retry_success'] += 1
                        return (True, data, word)
                    else:
                        last_error = data
            except Exception as e:
                last_error = str(e)
            if attempt < self.max_retries:
                time.sleep(3)
        return (False, last_error, word)
    def _process_batch(self, batch_items, batch_number):
        batch_results = {'succeeded': 0, 'failed': []}
        
        for i, item in enumerate(batch_items):
            word = item['word']
            
            if hasattr(self, 'progress_dialog') and self.progress_dialog and self.progress_dialog.cancelled:
                return batch_results

            self.results['processed'] += 1

            # Cập nhật UI thanh tiến trình (chụp giá trị hiện tại vào tham số mặc định,
            # tránh lambda đọc biến đã bị vòng lặp thay đổi khi main thread chạy tới)
            progress_label = f"🔄 Batch {batch_number}: {word}"
            percent = self.results['processed'] / max(1, self.results['total_words']) * 100
            eta = self._calculate_eta()
            mw.taskman.run_on_main(lambda p=percent, lbl=progress_label, e=eta: self._update_progress_ui(p, lbl, e))

            # Lấy data từ Gemini
            success, data, processed_word = self._process_item_with_retry(item)
            
            if hasattr(self, 'progress_dialog') and self.progress_dialog and self.progress_dialog.cancelled:
                return batch_results

            if success:
                # Ghi đè ngữ cảnh và định nghĩa
                final_def_vi = item.get('definition_vi', '').strip() or getattr(self, 'global_def_vi', '')
                final_context = item.get('context', '').strip() or getattr(self, 'global_context', '')
                
                if final_def_vi: 
                    data['definition_vi'] = final_def_vi
                    data['Definition_VI'] = final_def_vi
                if final_context: 
                    data['context'] = final_context
                    data['Context'] = final_context
                
                # --- [NEW] BỘ NHỚ IPA CHÍNH THỨC ---
                specific_ipa = item.get('ipa', '').strip()
                word_lower = processed_word.lower()
                ipa_memory = load_ipa_memory()
                
                final_ipa = specific_ipa
                if not final_ipa and word_lower in ipa_memory:
                    final_ipa = ipa_memory[word_lower]
                    
                if final_ipa:
                    data['ipa'] = final_ipa
                    data['IPA'] = final_ipa
                    if specific_ipa:
                        save_ipa_memory(word_lower, specific_ipa)
                # -----------------------------------

                # Tạo thẻ mới
                note = mw.col.new_note(mw.col.models.current())
                fill_note_with_data(note, data)
                mw.col.add_note(note, mw.col.decks.id(self.deck_name))

                # Ghi kết quả từng từ cho bảng báo cáo (kiểm tra format nghĩa ngay trong máy)
                self.results.setdefault('entries', []).append({
                    'word': processed_word, 'original': word, 'nid': note.id,
                    'pos': clean_field_text(data.get('part_of_speech') or ''),
                    'definition_vi': clean_field_text(data.get('definition_vi') or ''),
                    'definition_en': clean_field_text(data.get('definition_en') or ''),
                    'issues': check_entry_quality(data, vi_given_by_user=bool(final_def_vi)),
                    'context': final_context, 'forced_vi': final_def_vi,
                    'sections': {} if data.get('lite') else summarize_note_sections(data),
                    'lite': bool(data.get('lite')), 'source': data.get('lite_source', ''),
                })

                # Ảnh: phần vẽ (gọi mạng, rất chậm) chạy ở luồng phụ, SONG SONG với các từ tiếp theo;
                # gắn ảnh vào thẻ thì làm ở luồng này (_collect_images) để chỉ một nơi ghi vào collection
                if self.config.get("auto_image_gen", True) and not self.lite_mode:
                    self._queue_image(note.id, processed_word,
                                      data.get("image_query") or data.get("definition_en", ""),
                                      final_context, data.get("part_of_speech", ""),
                                      self.results['entries'][-1])

                batch_results['succeeded'] += 1
                self.results['succeeded'] += 1
            else:
                batch_results['failed'].append(word)
                self.results['failed'].append(word)
                self.results.setdefault('entries', []).append({'word': word, 'original': word, 'failed': True, 'error': str(data)})

            # Từ này đã xong (thành công hoặc thất bại) -> lưu tiến trình để có thể tiếp tục
            self.next_index += 1
            self._save_progress()
            self._collect_images()   # gắn những ảnh đã vẽ xong trong lúc chờ

            # Tránh Rate limit (vẫn cho phép bấm Hủy trong lúc chờ)
            if i < len(batch_items) - 1:
                for _ in range(max(1, int(getattr(self, 'delay', 2)))):
                    if self.progress_dialog and self.progress_dialog.cancelled:
                        return batch_results
                    time.sleep(1)
                
        return batch_results

    def _update_progress_ui(self, percent, label, eta):
        if hasattr(self, 'progress_dialog') and self.progress_dialog and not self.progress_dialog.cancelled:
            self.progress_dialog.update(int(percent), f"{label}\n⏱️ Còn lại: {eta}")

    def _queue_image(self, nid, word, prompt_hint, context, pos, entry):
        """Gửi việc vẽ ảnh cho luồng phụ (tối đa 2 ảnh cùng lúc)."""
        from concurrent.futures import ThreadPoolExecutor
        if self._image_pool is None:
            self._image_pool = ThreadPoolExecutor(max_workers=2)
        entry['image'] = 'pending'
        future = self._image_pool.submit(generate_image_from_gemini, keyword=word, config=self.config,
                                         definition_en=prompt_hint, context=context, pos_type=pos)
        self._image_jobs.append((future, nid, word, entry))

    def _collect_images(self):
        """Gắn các ảnh đã vẽ xong vào thẻ; ảnh chưa xong thì để lần sau."""
        remaining = []
        for job in self._image_jobs:
            future, nid, word, entry = job
            if not future.done():
                remaining.append(job)
                continue
            try:
                success, image_data = future.result()
                if success:
                    note = mw.col.get_note(nid)
                    if put_image_into_note(note, save_generated_image(word, image_data)):
                        mw.col.update_note(note)
                    entry['image'] = 'ok'
                else:
                    entry['image'] = 'fail'
            except Exception as e:
                print(f"Lỗi ảnh '{word}': {e}")
                entry['image'] = 'fail'
        self._image_jobs = remaining

    def _finish_images(self, cancelled=False):
        """Sau khi xong phần chữ: chờ nốt các ảnh còn đang vẽ (bấm Hủy thì bỏ ảnh chưa xong)."""
        jobs = self._image_jobs
        while jobs:
            if cancelled or (self.progress_dialog and self.progress_dialog.cancelled):
                for future, _, _, entry in jobs:
                    future.cancel()
                    entry['image'] = 'skipped'
                break
            label = f"🎨 Phần chữ đã xong. Đang hoàn tất ảnh: còn {len(jobs)} ảnh"
            mw.taskman.run_on_main(lambda lbl=label: self._update_progress_ui(100, lbl, "vài phút"))
            time.sleep(1)
            self._collect_images()
            jobs = self._image_jobs
        pool, self._image_pool = self._image_pool, None
        if pool is not None:
            pool.shutdown(wait=False)

    def run(self, progress_dialog=None):
        self.progress_dialog = progress_dialog
        
        # Chia batch dựa trên items
        batches = [self.items[i:i + self.batch_size] for i in range(0, len(self.items), self.batch_size)]
        
        stopped_early = False
        for i, batch in enumerate(batches, 1):
            if progress_dialog and progress_dialog.cancelled: 
                stopped_early = True
                break
            self._process_batch(batch, i)
            if progress_dialog and progress_dialog.cancelled: 
                stopped_early = True
                break
            if i < len(batches):
                for _ in range(self.delay):
                    if progress_dialog and progress_dialog.cancelled:
                        stopped_early = True
                        break
                    time.sleep(1)
                if stopped_early: break

        self._finish_images(cancelled=stopped_early)

        # Chạy hết -> xóa file tiến trình. Bị dừng giữa chừng -> GIỮ file để dùng
        # "Tools → Tiếp tục tiến trình bị gián đoạn".
        if self.save_progress and os.path.exists(self.progress_file):
            if not stopped_early or self.next_index >= len(self.items):
                try: os.remove(self.progress_file)
                except OSError: pass

        # Thông báo dừng do on_done hiển thị (trước đây bị hiện 2 lần)
        self.results['stopped_early'] = stopped_early
        return self.results

# ========== OPTIMIZED BATCH ADD PROGRESS DIALOG ==========
class OptimizedBatchProgressDialog(QDialog):
    """Dialog tiến trình cho thêm từ tối ưu"""
    
    def __init__(self, parent=None, total_words=0, title="🚀 Optimized Batch Add"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.total_words = total_words
        self.current = 0
        self.cancelled = False
        
        layout = QVBoxLayout()
        
        # Title
        title_label = QLabel("🚀 Đang xử lý tối ưu hóa...")
        title_label.setStyleSheet("font-weight: bold; font-size: 16px; margin-bottom: 10px;")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(title_label)
        
        # Stats display
        self.stats_label = QLabel("Chuẩn bị bắt đầu...")
        self.stats_label.setStyleSheet("font-size: 13px; color: #34495e; background: #f8f9fa; padding: 10px; border-radius: 5px;")
        self.stats_label.setWordWrap(True)
        layout.addWidget(self.stats_label)
        
        # Main progress bar
        self.progress = QProgressBar()
        self.progress.setMaximum(100)
        layout.addWidget(self.progress)
        
        # Detail label
        self.label = QLabel("Đang khởi tạo...")
        layout.addWidget(self.label)
        
        # ETA label
        self.eta_label = QLabel("⏱️ Thời gian ước tính: Đang tính...")
        self.eta_label.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        layout.addWidget(self.eta_label)
        
        # Cancel button
        self.cancel_button = QPushButton("❌ Hủy bỏ")
        self.cancel_button.clicked.connect(self.cancel)
        layout.addWidget(self.cancel_button)
        
        self.setLayout(layout)
        self.resize(500, 200)
    
    def update(self, value, label=None):
        """Cập nhật tiến trình"""
        self.current = value
        self.progress.setValue(value)
        
        if label:
            self.label.setText(label)
            
            # Cập nhật stats
            if "Batch" in label:
                parts = label.split('\n')
                if len(parts) > 1:
                    self.eta_label.setText(parts[1])
                self.stats_label.setText(f"📊 Tiến trình: {value}%\n{parts[0]}")
        
        # Tự động đóng khi hoàn thành
        if value >= 100:
            self.close()
    
    def cancel(self):
        """Hủy quá trình"""
        self.cancelled = True
        self.label.setText("Đang hủy bỏ...")
        self.cancel_button.setEnabled(False)
        self.close()

# (duplicate run_optimized_batch_add removed, see definition above at run_optimized_batch_add with note_type_name support)

# ========== CHỨC NĂNG TIẾP TỤC TIẾN TRÌNH BỊ GIÁN ĐOẠN ==========
def resume_interrupted_batch():
    """Tiếp tục tiến trình Optimized Batch Add bị gián đoạn (bấm Hủy, Anki bị tắt...)."""
    progress_files = []
    for progress_dir in (get_progress_dir(), _legacy_progress_dir()):
        if os.path.isdir(progress_dir):
            progress_files += [os.path.join(progress_dir, f) for f in os.listdir(progress_dir)
                               if f.startswith('progress_') and f.endswith('.json')]

    if not progress_files:
        showInfo("📭 Không tìm thấy tiến trình nào bị gián đoạn")
        return

    # Lấy file mới nhất
    latest_file = max(progress_files, key=os.path.getmtime)

    try:
        with open(latest_file, 'r', encoding='utf-8') as f:
            progress_info = json.load(f)
    except Exception as e:
        showCritical(f"❌ Lỗi tải tiến trình: {str(e)}")
        return

    cfg = progress_info.get('config', {})
    results = progress_info.get('results', {})
    # 'remaining_words' là key của bản cũ (list chữ), bản mới lưu 'remaining_items' (list dict)
    items = progress_info.get('remaining_items') or progress_info.get('remaining_words') or []
    items = [it if isinstance(it, dict) else {"word": str(it)} for it in items]

    if not items:
        try: os.remove(latest_file)
        except OSError: pass
        showInfo("✅ Tiến trình đã hoàn thành hoặc không còn từ nào để xử lý")
        return

    resume_msg = f"""
🔄 PHÁT HIỆN TIẾN TRÌNH BỊ GIÁN ĐOẠN

📊 Thông tin tiến trình:
• Thời gian: {cfg.get('timestamp', 'Không xác định')}
• Bộ thẻ: {cfg.get('deck_name', 'Không xác định')}
• Số từ còn lại: {len(items)}
• Đã xử lý: {results.get('processed', 0)}/{results.get('total_words', 0)}
• Thành công: {results.get('succeeded', 0)}

Bạn có muốn tiếp tục tiến trình này?
"""
    reply = QMessageBox.question(mw, "Tiếp tục tiến trình", resume_msg,
                                 QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    if reply != QMessageBox.StandardButton.Yes:
        return

    # Lần chạy mới sẽ tự tạo file tiến trình riêng -> xóa file cũ để không bị resume trùng
    try: os.remove(latest_file)
    except OSError: pass

    run_optimized_batch_add(
        items, cfg.get('deck_name', 'Default'),
        batch_size=cfg.get('batch_size', 10), delay=cfg.get('delay', 2),
        max_retries=cfg.get('max_retries', 3),
        global_context=cfg.get('global_context', ''), global_def_vi=cfg.get('global_def_vi', ''),
        lite_mode=cfg.get('lite_mode', False),
    )

# ========== MENU TRONG BROWSER ==========
def add_browser_menu_item(browser: Browser):
    """Thêm menu item vào browser (cùng hành vi với menu chuột phải)."""
    try:
        action1 = QAction("✨ Thêm chi tiết với Gemini", browser)
        action1.triggered.connect(lambda: run_batch_processing_for_browser(browser, "fill"))

        action2 = QAction("🔗 Tạo từ vựng liên quan", browser)
        action2.triggered.connect(lambda: run_batch_processing_for_browser(browser, "related_vocab"))

        # Tối ưu các thẻ đang chọn (trước đây menu này lại mở dialog thêm từ mới,
        # khác với menu chuột phải cùng tên)
        action3 = QAction("🚀 Add optimized vocabulary list", browser)
        action3.triggered.connect(lambda: run_optimized_browser_processing(browser))

        menus_to_check = []
        for menu_name in ('menu_Cards', 'menu_Edit', 'menu_Notes', 'menu_Tools'):
            if hasattr(browser.form, menu_name):
                menus_to_check.append(getattr(browser.form, menu_name))

        for menu in menus_to_check:
            menu.addSeparator()
            menu.addAction(action1)
            menu.addAction(action2)
            menu.addAction(action3)

    except Exception as e:
        print(f"❌ Lỗi thêm browser menu: {e}")

# ========== HÀM XỬ LÝ AUDIO (ĐÃ SỬA LỖI) ==========
def pcm_to_wav(pcm_data, sample_rate=24000):
    with io.BytesIO() as wav_file:
        with wave.open(wav_file, 'wb') as wav_out:
            wav_out.setnchannels(1)
            wav_out.setsampwidth(2)
            wav_out.setframerate(sample_rate)
            wav_out.writeframes(pcm_data)
        return wav_file.getvalue()

def get_gemini_speech(text, config):
    # 1. Ưu tiên sử dụng TTS API Key riêng, nếu không có thì dùng Key chung
    api_key_str = str(config.get("tts_api_key") or "").strip()
    if not api_key_str:
        api_key_str = str(config.get("api_key") or "").strip()
    # Fallback: dùng TOÀN BỘ danh sách api_keys để xoay vòng (trước đây chỉ lấy key đầu tiên)
    if not api_key_str and isinstance(config.get("api_keys"), list) and config["api_keys"]:
        api_key_str = "\n".join(config["api_keys"])
    
    # 2. Sử dụng TTS Model riêng biệt
    model = config.get("tts_model", "gemini-2.5-flash-preview-tts")
    
    # URL Template chuẩn
    url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
    headers = {"Content-Type": "application/json"}
    
    # 3. PHÁT HIỆN NGÔN NGỮ TỰ ĐỘNG
    language_code = detect_language_for_audio(text)
    voice_name = get_voice_for_language(language_code, config)
    
    payload = {
        "contents": [{"parts": [{"text": text}]}],
        "generationConfig": {
            "responseModalities": ["AUDIO"],
            "speechConfig": {
                "voiceConfig": {
                    "prebuiltVoiceConfig": {
                        "voiceName": voice_name
                    }
                }
            }
        }
    }

    # Gọi hàm request với key rotation
    success, result = make_request_with_rotation(url_template, payload, api_key_str, timeout=300)
        
    if success:
        response_data = result 
        
        if "candidates" in response_data and response_data["candidates"]:
            candidate = response_data["candidates"][0]
            if "content" in candidate and "parts" in candidate["content"]:
                part = candidate["content"]["parts"][0]
                if "inlineData" in part and "data" in part["inlineData"]:
                    audio_base64 = part["inlineData"]["data"]
                    try:
                        pcm_data = base64.b64decode(audio_base64)
                        wav_data = pcm_to_wav(pcm_data)
                        return (True, wav_data)
                    except Exception as e:
                        return (False, f"Lỗi xử lý audio data: {str(e)}")
        
        return (False, "No audio data in response")
    
    # Nếu thất bại, result chứa thông báo lỗi string
    return (False, result)

def run_gemini_tts_for_editor(editor):
    """Hàm xử lý khi nhấn nút tạo Audio với phát hiện ngôn ngữ"""
    config = load_config()
    note = editor.note
    
    text_to_speak = ""
    if "Word" in note and (note["Word"] or '').strip():
        text_to_speak = (note["Word"] or '').strip()
    elif "Front" in note and (note["Front"] or '').strip():
        text_to_speak = (note["Front"] or '').strip()
    
    if not text_to_speak:
        tooltip("⚠️ Cần trường 'Word' hoặc 'Front' để tạo audio")
        return
    
    # Phát hiện ngôn ngữ
    language_code = detect_language_for_audio(text_to_speak)
    voice_name = get_voice_for_language(language_code, config)
    audio_prompt = text_to_speak
    current_ipa = get_note_field_value(note, ["IPA", "Phonetic", "Phiên âm"])
    if current_ipa:
        # Ép AI TTS đọc bám sát phiên âm này
        audio_prompt = f"Please read the following word aloud exactly matching this phonetic pronunciation: /{current_ipa}/. Word: '{text_to_speak}'. DO NOT say any other words, just pronounce the target word clearly."
    # Mapping mã ngôn ngữ -> tên hiển thị
    language_names = {
        'en': 'Tiếng Anh',
        'vi': 'Tiếng Việt', 
        'zh': 'Tiếng Trung',
        'ja': 'Tiếng Nhật',
        'ko': 'Tiếng Hàn',
        'de': 'Tiếng Đức',
        'default': 'Mặc định'
    }
    
    language_display = language_names.get(language_code, 'Mặc định')
    
    tooltip(f"🔊 Đang tạo âm thanh ({language_display}) cho: '{text_to_speak}'...")
    
    def worker():
        # Gọi hàm với prompt đã được chế lại (nếu có IPA) thay vì chỉ text_to_speak
        return get_gemini_speech(audio_prompt, config)
        
    def on_done(future):
        try:
            success, result = future.result()
            if success:
                wav_data = result
                import re
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_text = re.sub(r'[^a-zA-Z0-9]', '', text_to_speak)[:20]
                filename = f"gemini_{safe_text}_{timestamp}.wav"
                mw.col.media.write_data(filename, wav_data)
                sound_tag = f"[sound:{filename}]"
                
                field_updated = False
                for field_name in ["Audio", "Sound", "Phát âm", "Pronunciation"]:
                    if field_name in note:
                        note[field_name] = sound_tag
                        field_updated = True
                        tooltip(f"✅ Đã lưu audio ({language_display}) vào '{field_name}'!")
                        break
                
                if not field_updated:
                    # Nếu không có trường audio nào, thêm vào trường đầu tiên có thể
                    first_field = list(note.keys())[0] if note.keys() else "Front"
                    note[first_field] += f"<br>{sound_tag}"
                    tooltip(f"✅ Đã thêm audio ({language_display}) vào trường '{first_field}'!")
                
                editor.loadNote()
            else:
                showCritical(f"❌ Lỗi tạo audio: {result}")
        except Exception as e:
            showCritical(f"❌ Lỗi xử lý audio: {str(e)}")
    
    mw.taskman.run_in_background(worker, on_done)
# [NEW] IMAGE GENERATION HELPER FUNCTION
# ========== HELPER: XỬ LÝ ẢNH ==========
def save_generated_image(keyword, image_data):
    """Lưu ảnh vào thư mục media của Anki, trả về thẻ <img>. Gọi từ luồng đang làm việc với collection."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
    safe_keyword = re.sub(r'[^a-zA-Z0-9]', '', str(keyword))[:20] or "image"
    filename = f"gemini_{safe_keyword}_{timestamp}.jpg"
    mw.col.media.write_data(filename, image_data)
    return f'<img src="{filename}">'

def put_image_into_note(note, img_tag):
    """Gắn thẻ ảnh vào field ảnh của note (Image, hoặc tên field ảnh khác)."""
    for field in ["Image", "Picture", "Hình ảnh", "Minh họa"]:
        if field in note:
            note[field] = img_tag
            return True
    return False

def handle_image_generation_and_save(keyword, config, definition_en=None, context=None, pos_type=None):
    """
    Hàm trung gian xử lý tạo ảnh và lưu file.
    - keyword: Từ vựng gốc (Dùng để đặt tên file)
    - definition_en: Định nghĩa (Dùng làm Prompt vẽ cho chính xác)
    """
    try:
        if not config.get("auto_image_gen", True):
            return None

        success, image_data = generate_image_from_gemini(
            keyword=keyword, 
            config=config, 
            definition_en=definition_en, 
            context=context, 
            pos_type=pos_type
        )
        
        if success:
            return save_generated_image(keyword, image_data)
        return None
    except Exception as e:
        print(f"Lỗi xử lý ảnh: {e}")
        return None
def detect_language(text):
    """Hàm phát hiện ngôn ngữ đơn giản"""
    if re.search(r"[\uAC00-\uD7A3]", text): return "Korean"
    if re.search(r"[äöüßÄÖÜẞ]", text): return "German"
    if re.search(r"[\u3040-\u30ff\u31f0-\u31ff]", text): return "Japanese"
    if re.search(r"[\u4e00-\u9faf]", text):
        if re.search(r"[\u3040-\u30ff\u31f0-\u31ff]", text): return "Japanese"
        return "Chinese"
    if re.search(r"[àáạảãâầấậẩẫăằắặẳẵèéẹẻẽêềếệểễìíịỉĩòóọỏõôồốộổỗơờớợởỡùúụủũưừứựửữỳýỵỷỹđ]", text.lower()): return "Vietnamese"
    return "English"

# ========== HÀM TẠO PROMPT ẢNH (CHẤT LƯỢNG CAO) ==========
def generate_image_prompt(keyword, definition_en="", context="", pos_type=""):
    """
    Tạo prompt tối ưu cho AI image generation.
    - Cụ thể, chi tiết, giàu ngữ cảnh thị giác
    - Phù hợp với loại từ (noun/verb/adj/adv)
    - Chống lỗi NoneType, import random đúng cách
    """
    keyword = keyword.strip() if keyword else ""
    definition_en = definition_en if definition_en else ""
    def_snippet = definition_en.split('.')[0].strip() if definition_en else ""
    context = context.strip() if context else ""
    pos_type = pos_type if pos_type else ""
    
    # === XÂY DỰNG PROMPT THEO LOẠI TỪ ===
    # Dùng mẫu cụ thể cho từng POS để ảnh chính xác hơn
    
    pos_lower = pos_type.lower() if pos_type else ""
    
    # Noun, vật thể, người, địa điểm rõ ràng
    if pos_lower in ['noun', 'n', 'danh từ']:
        if def_snippet:
            body = f"A clear, detailed photograph of {def_snippet}, representing '{keyword}', high resolution, professional photography, sharp focus"
        else:
            body = f"A high-quality photograph of a {keyword}, detailed texture, professional lighting, sharp focus, 8k"
    
    # Verb, hành động
    elif pos_lower in ['verb', 'v', 'động từ']:
        if def_snippet:
            body = f"A dynamic action scene showing {def_snippet}, motion, natural lighting, cinematic composition, photorealistic"
        else:
            body = f"A person or animal performing the action '{keyword}', dynamic pose, motion blur, action photography, cinematic lighting"
    
    # Adjective, mô tả cảnh vật
    elif pos_lower in ['adjective', 'adj', 'tính từ']:
        if def_snippet:
            body = f"A beautiful scene that perfectly captures the feeling of '{keyword}': {def_snippet}, atmospheric, cinematic lighting, emotional, stunning landscape or portrait photography"
        else:
            body = f"A stunning visual scene that illustrates the quality '{keyword}', atmospheric lighting, emotional mood, professional photography, masterpiece"
    
    # Adverb
    elif pos_lower in ['adverb', 'adv', 'trạng từ']:
        if def_snippet:
            body = f"A scene showing an action being done '{keyword}': {def_snippet}, dynamic composition, motion photography, sharp action shot"
        else:
            body = f"A person performing an action in a '{keyword}' manner, dynamic motion shot, cinematic, professional photography"
    
    # Mặc định, linh hoạt
    else:
        if def_snippet:
            body = f"A highly detailed visual of {def_snippet}, representing '{keyword}', professional photography, cinematic composition, vivid, sharp focus, 8k"
        else:
            body = f"A beautiful detailed illustration representing '{keyword}', professional, cinematic, sharp focus, vivid colors, masterpiece"
    
    # Thêm context nếu có
    if context:
        body += f", {context}, appropriate setting and atmosphere for this concept"
    
    # Thêm style boosters
    style_tags = [
        "masterpiece", "highly detailed", "vivid colors", "sharp focus",
        "professional photography", "cinematic composition", "no text"
    ]
    
    prompt_parts = [body] + style_tags
    final_prompt = ", ".join(prompt_parts)
    
    return final_prompt[:800]

def create_image_tag_from_bytes(image_bytes, keyword):
    """
    Tạo thẻ HTML img từ bytes ảnh
    """
    try:
        # Mã hóa base64
        b64_image = base64.b64encode(image_bytes).decode('utf-8')
        
        # Tạo thẻ HTML
        img_tag = f'<img src="data:image/png;base64,{b64_image}" '
        img_tag += f'alt="Illustration of {keyword}" '
        img_tag += 'style="max-width: 100%; height: auto; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); margin: 10px 0;">'
        
        return img_tag
    except Exception as e:
        print(f"❌ Lỗi tạo image tag: {e}")
        return None
# [NEW] IMAGE GENERATION HELPER FUNCTION
# ========== CẬP NHẬT CHỨC NĂNG TẠO ẢNH (IMAGEN 3) ==========
# Hãy copy đè đoạn code này lên 2 hàm cũ: run_standalone_image_gen và generate_image_from_gemini

def run_standalone_image_gen(editor):
    """Hàm worker xử lý logic UI và gọi tạo ảnh"""
    config = load_config()
    note = editor.note
    
    # 1. Kiểm tra trường Word
    if "Word" not in note or not (note["Word"] or '').strip():
        tooltip("⚠️ Vui lòng nhập từ vựng vào trường 'Word' trước.")
        return
        
    keyword = (note["Word"] or '').strip()
    
    # 2. Lấy Prompt từ trường ImageQuery nếu có
    image_query_prompt = None
    query_fields = ["ImageQuery", "Image Querry", "Image_Query"]
    for f in query_fields:
        if f in note and (note[f] or '').strip():
            image_query_prompt = note[f].strip()
            # Loại bỏ HTML tags nếu có
            image_query_prompt = re.sub(r'<[^>]+>', '', image_query_prompt)
            break
            
    # 3. Kiểm tra API Key
    # Ưu tiên Image API Key, nếu không có thì dùng Key chung, nếu cả 2 không có thì báo lỗi
    api_key = config.get("image_api_key") or config.get("api_key")
    # Fallback to api_keys list
    if not api_key and "api_keys" in config and isinstance(config["api_keys"], list) and config["api_keys"]:
        api_key = config["api_keys"][0]
    
    if not api_key or "YOUR_API_KEY_HERE" in api_key:
        showCritical("⚠️ Vui lòng cài đặt API Key trong menu Settings trước.")
        return

    # Hiển thị thông báo đang xử lý
    tooltip(f"🎨 Đang vẽ minh họa cho: '{keyword}'...")

    def worker():
        # Gọi hàm tạo ảnh
        # Nếu có image_query_prompt, dùng nó làm definition_en (prompt chính)
        success, result = generate_image_from_gemini(
            keyword=keyword, 
            config=config, 
            definition_en=image_query_prompt if image_query_prompt else None
        )
        if success:
            image_bytes = result
            # Tạo tên file an toàn
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_keyword = "".join(c for c in keyword if c.isalnum() or c in (' ', '-', '_')).rstrip().replace(" ", "_")
            # Giới hạn độ dài tên file
            safe_keyword = safe_keyword[:30]
            filename = f"gemini_{safe_keyword}_{timestamp}.png"
            
            # Lưu file vào thư mục media của Anki
            mw.col.media.write_data(filename, image_bytes)
            return (True, filename)
        else:
            return (False, result)
    
    def on_done(future):
        try:
            success, result = future.result()
            if success:
                filename = result
                # Tạo thẻ hình ảnh
                img_tag = f'<img src="{filename}">'
                
                # Tìm trường phù hợp để điền ảnh
                field_updated = False
                target_fields = ["Image", "Picture", "Hình ảnh", "Minh họa"]
                
                # Nếu note có trường Image (ưu tiên số 1)
                if "Image" in note:
                    note["Image"] = img_tag
                    field_updated = True
                else:
                    # Nếu không, tìm các trường tương tự
                    for field in target_fields:
                        if field in note:
                            note[field] = img_tag
                            field_updated = True
                            break
                
                if field_updated:
                    editor.loadNote()
                    tooltip(f"✅ Đã tạo và chèn ảnh thành công!")
                else:
                    # Nếu không tìm thấy trường nào để điền, copy vào clipboard
                    from aqt.qt import QApplication
                    QApplication.clipboard().setText(img_tag)
                    showInfo(f"✅ Đã tạo ảnh: {filename}\n⚠️ Không tìm thấy trường 'Image'.\n📋 Tag hình ảnh đã được copy vào Clipboard!")
            else:
                showCritical(f"❌ Lỗi tạo ảnh: {result}")
        except Exception as e:
            showCritical(f"❌ Lỗi hệ thống: {str(e)}")
            
    mw.taskman.run_in_background(worker, on_done)
# ========== HELPERS: KEY ROTATION (CHỨC NĂNG MỚI - THÊM VÀO SAU save_config) ==========
# ========== CÁC HÀM HỖ TRỢ API (Dán đè vào cuối file main.py) ==========
def call_groq_with_key_rotation(prompt, config, timeout=300):
    import time
    import requests
    import json

    GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
    model = config.get("groq_model", "llama-3.3-70b-versatile")
    MAX_RETRIES_PER_KEY = 5
    RETRY_BACKOFF_BASE = 3

    keys = []
    if "groq_api_keys" in config and isinstance(config["groq_api_keys"], list) and config["groq_api_keys"]:
        keys = config["groq_api_keys"]
    raw = config.get("groq_api_keys", "")
    if not keys and isinstance(raw, str) and raw.strip():
        keys = [k.strip() for k in raw.replace(',', '\n').split('\n') if k.strip() and k.strip() != "gsk_..."]

    if not keys:
        return (False, "Chua cau hinh Groq API Key.")

    errors = []

    for i, key in enumerate(keys):
        headers = {
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": prompt}]
        }

        for attempt in range(1, MAX_RETRIES_PER_KEY + 1):
            try:
                response = requests.post(GROQ_API_URL, headers=headers, json=payload, timeout=timeout)
                print(f"[Groq] Key {i+1} try {attempt}: status={response.status_code}")

                if response.status_code == 200:
                    data = response.json()
                    if "choices" in data and len(data["choices"]) > 0:
                        content = data["choices"][0]["message"]["content"]
                        finish_reason = data["choices"][0].get("finish_reason", "unknown")
                        print(f"[Groq] Response OK - content_len={len(content)}, finish_reason={finish_reason}")
                        print(f"[Groq] Content preview: {content[:200]}")
                        if not content or not content.strip():
                            errors.append(f"Key {i+1}: Content trong, finish_reason={finish_reason}")
                            continue
                        return (True, content)
                    else:
                        print(f"[Groq] No choices. Raw keys: {list(data.keys())}, text: {response.text[:500]}")
                        errors.append(f"Key {i+1}: Phan hoi trong, data keys: {list(data.keys())}")
                        break

                if response.status_code in [429, 500, 503]:
                    errors.append(f"Key {i+1} (lan {attempt}): {response.status_code}")
                    if attempt < MAX_RETRIES_PER_KEY:
                        wait = RETRY_BACKOFF_BASE * attempt
                        print(f"[Groq] Key {i+1} loi {response.status_code}. Thu lai lan {attempt+1}/{MAX_RETRIES_PER_KEY} sau {wait}s...")
                        time.sleep(wait)
                        continue
                    else:
                        print(f"[Groq] Key {i+1} van loi {response.status_code} sau {MAX_RETRIES_PER_KEY} lan thu. Chuyen key...")
                        break

                if response.status_code in [400, 401, 403]:
                    print(f"[Groq] Key {i+1} loi {response.status_code}: {response.text[:200]}")
                    errors.append(f"Key {i+1}: {response.status_code} - {response.text[:150]}")
                    break

                errors.append(f"Key {i+1}: HTTP {response.status_code} - {response.text[:150]}")
                break

            except Exception as e:
                errors.append(f"Key {i+1} (lan {attempt}) loi ket noi: {str(e)}")
                if attempt < MAX_RETRIES_PER_KEY:
                    time.sleep(RETRY_BACKOFF_BASE * attempt)
                    continue
                else:
                    break

    return (False, f"Tat ca Groq keys deu that bai.\nKeys: {len(keys)} key(s)\nChi tiet: {errors}")

def get_key_list(key_string):
    """Chuyển chuỗi key thành list, hỗ trợ phân cách bằng xuống dòng hoặc dấu phẩy"""
    if not key_string:
        return []
    # Thay thế dấu phẩy bằng xuống dòng, sau đó tách dòng
    keys = [k.strip() for k in key_string.replace(',', '\n').split('\n') if k.strip()]
    return keys

# Model dự phòng cho các yêu cầu trả về chữ. Lượt miễn phí của Google tính riêng cho từng model
# trên mỗi project, nên khi model chính hết lượt / quá tải / không còn cho dùng thì chuyển sang model kế tiếp.
# (gemini-2.0-flash đã bị khai tử; gemini-2.5-flash không còn cho tài khoản mới dùng.)
GEMINI_DEFAULT_MODEL = "gemini-3.8-flash"
GEMINI_FALLBACK_MODELS = ["gemini-3.8-flash", "gemini-2.5-flash", "gemini-3.5-flash-lite", "gemini-flash-lite-latest"]

# Vị trí key Gemini chạy tốt gần nhất: request sau bắt đầu từ key này thay vì luôn thử lại key số 1
_gemini_key_start = 0
# Ghi nhớ trong phiên làm việc để khỏi thử lại vô ích
_gemini_dead_keys = set()   # key bị xoá/thu hồi (400 API_KEY_INVALID)
_gemini_blocked = {}        # (model, key) -> thời điểm hết chặn (429 hết lượt, 403/404 không dùng được)
_gemini_model_busy = {}     # model -> thời điểm hết quá tải (500/503)

def _gemini_models_for(url_template, payload):
    """Chuỗi model sẽ thử: model trong URL trước, rồi các model dự phòng.
    Không áp dụng cho yêu cầu tạo âm thanh/ảnh (TTS, image) vì model chữ không làm được."""
    m = re.search(r"/models/([^/:?]+):", url_template)
    primary = m.group(1) if m else None
    gen = (payload or {}).get("generationConfig") or {}
    if not primary or gen.get("responseModalities") or re.search(r"tts|image|audio|embedding", primary):
        return [primary]
    if "lite" in primary:
        # Việc nhẹ (thẻ nhẹ) chỉ dự phòng bằng model Lite khác, không đốt lượt ít ỏi của bản Flash
        return [primary] + [x for x in GEMINI_FALLBACK_MODELS if x != primary and "lite" in x]
    return [primary] + [x for x in GEMINI_FALLBACK_MODELS if x != primary]

def call_gemini_with_key_rotation(url_template, headers, payload, config, timeout=300):
    """
    Thực hiện request với cơ chế tự động xoay vòng Key và đổi model dự phòng.
    call_gemini_with_key_rotation(url_template, headers, payload, config, timeout)
    Trả về (True, response) hoặc (False, thông_báo_lỗi).

    - Bắt đầu từ key chạy tốt lần trước (nhớ trong phiên làm việc).
    - 400 key không hợp lệ: bỏ key đó cho cả phiên.
    - 429 hết lượt / 403-404 model không dùng được với key: chuyển key NGAY, nhớ để lần sau bỏ qua.
    - 500/503 model quá tải: chuyển sang model dự phòng (model cuối cùng thì retry có backoff).
    - Lỗi mạng: retry có backoff trên cùng key.
    """
    global _gemini_key_start

    MAX_RETRIES_PER_KEY = 5   # số lần thử lại trên cùng 1 key khi gặp lỗi tạm thời
    RETRY_BACKOFF_BASE = 3    # giây, tăng dần theo số lần thử: 3s, 6s, 9s...

    # 1. Lấy danh sách key từ config: ưu tiên api_keys (list), fallback api_key (string cũ)
    key_string = ""
    if "api_keys" in config and isinstance(config["api_keys"], list) and config["api_keys"]:
        key_string = "\n".join(config["api_keys"])
    elif config.get("api_key") and str(config["api_key"]).strip():
        key_string = str(config["api_key"])

    keys = [k for k in get_key_list(key_string) if "YOUR_API_KEY" not in k]
    if not keys:
        return (False, "Chưa cấu hình API Key hợp lệ. Vào Tools → Gemini Editor Settings để nhập key.")

    models = _gemini_models_for(url_template, payload)
    start = _gemini_key_start % len(keys)
    order = list(range(start, len(keys))) + list(range(0, start))
    errors = []

    for model_pos, model in enumerate(models):
        is_last_model = model_pos == len(models) - 1
        if not is_last_model and _gemini_model_busy.get(model, 0) > time.time():
            continue
        # main.py dùng {key}, một số chỗ khác dùng {API_KEY}
        url_for_model = url_template if model == models[0] else url_template.replace(f"/models/{models[0]}:", f"/models/{model}:")
        # Đời 3.x mặc định "suy nghĩ" rất lâu (một từ có thể mất vài phút) -> đặt mức thấp cho yêu cầu chữ.
        # Đời 2.5 không hiểu tham số thinkingLevel nên giữ nguyên.
        model_payload = payload
        gen = (payload or {}).get("generationConfig") or {}
        if model and not model.startswith("gemini-2") and "thinkingConfig" not in gen and not gen.get("responseModalities"):
            model_payload = dict(payload, generationConfig=dict(gen, thinkingConfig={"thinkingLevel": "low"}))
        body = json.dumps(model_payload)
        saved_usage = load_gemini_usage()   # nhớ key chết / hết lượt cả giữa các lần mở Anki
        usable = [i for i in order
                  if keys[i] not in _gemini_dead_keys and _gemini_blocked.get((model, keys[i]), 0) <= time.time()
                  and saved_usage["keys"].get(_gemini_kid(keys[i]), {}).get("state") != "dead"
                  and not saved_usage["exhausted"].get(f"{_gemini_kid(keys[i])}|{model}")]
        next_model = False

        for pos, i in enumerate(usable):
            key = keys[i]
            is_last_try = is_last_model and pos == len(usable) - 1
            real_url = url_for_model.replace("{key}", key).replace("{API_KEY}", key)
            print(f"[Gemini] {model} · key {i+1}/{len(keys)}")

            for attempt in range(1, MAX_RETRIES_PER_KEY + 1):
                try:
                    response = requests.post(real_url, headers=headers, data=body, timeout=timeout)
                except requests.exceptions.Timeout:
                    # Quá thời gian chờ: model đang chậm/quá tải -> sang model khác ngay, không chờ lại 5 lần
                    print(f"⏳ {model} quá {timeout}s không trả lời -> chuyển model")
                    errors.append(f"{model} key {i+1}: quá {timeout}s")
                    if not is_last_model:
                        _gemini_model_busy[model] = time.time() + 600
                    next_model = True
                    break
                except Exception as e:
                    errors.append(f"{model} key {i+1} (lần {attempt}) lỗi kết nối: {str(e)}")
                    if attempt < 3:
                        time.sleep(RETRY_BACKOFF_BASE * attempt)
                        continue
                    break

                status = response.status_code
                if status == 200:
                    _gemini_key_start = i
                    record_gemini_call(key, model, "ok")
                    if model != models[0]:
                        print(f"[Gemini] Đã dùng model dự phòng {model}")
                    # Nơi gọi mong đợi object response (để gọi .json() sau này)
                    return (True, response)

                text = response.text
                if status == 400 and "API_KEY" in text:
                    print(f"❌ Key số {i+1} không hợp lệ (đã bị xoá/thu hồi?) -> bỏ qua trong phiên này")
                    _gemini_dead_keys.add(key)
                    record_gemini_call(key, model, "dead")
                    errors.append(f"Key {i+1}: không hợp lệ")
                    break

                if status == 429:
                    per_day = "PerDay" in text
                    if is_last_try and not per_day and attempt < MAX_RETRIES_PER_KEY:
                        # Lần thử cuối cùng còn lại: chờ giới hạn theo phút rồi thử lại
                        time.sleep(RETRY_BACKOFF_BASE * attempt)
                        continue
                    print(f"⚠️ {model} · key số {i+1} hết lượt ({'trong ngày' if per_day else 'tạm thời'}). Chuyển key...")
                    _gemini_blocked[(model, key)] = time.time() + (3 * 3600 if per_day else 60)
                    if per_day:
                        record_gemini_call(key, model, "exhausted")
                    errors.append(f"{model} key {i+1}: 429 hết lượt")
                    break

                if status in (403, 404):
                    print(f"❌ {model} · key số {i+1} lỗi {status}: {text[:200]}")
                    _gemini_blocked[(model, key)] = time.time() + (7 * 86400 if status == 404 else 86400)
                    record_gemini_call(key, model, "unavailable")
                    errors.append(f"{model} key {i+1}: {status} - {text[:150]}")
                    break

                if status in (500, 503):
                    if not is_last_model:
                        print(f"⏳ {model} đang quá tải ({status}) -> chuyển sang model dự phòng")
                        _gemini_model_busy[model] = time.time() + 600
                        errors.append(f"{model}: {status} quá tải")
                        next_model = True
                        break
                    errors.append(f"{model} key {i+1} (lần {attempt}): {status}")
                    if attempt < MAX_RETRIES_PER_KEY:
                        time.sleep(RETRY_BACKOFF_BASE * attempt)
                        continue
                    break

                # 400 khác: yêu cầu không hợp với model này (không phải lỗi key) -> các key khác cũng sẽ lỗi y hệt,
                # nên sang thẳng model kế tiếp (model cuối thì dừng) thay vì thử lần lượt từng key
                print(f"❌ {model} · key số {i+1} lỗi {status}: {text[:200]}")
                errors.append(f"{model} key {i+1}: {status} - {text[:150]}")
                next_model = True
                break

            if next_model:
                break

    safe_template = url_template.split("?key=")[0] + "?key=***"
    return (False, f"Tất cả key/model đều thất bại.\nURL: {safe_template}\nKeys: {len(keys)} key(s), models: {models}\nChi tiết: {errors[-8:]}")

# Hàm tương thích ngược cho các chức năng khác (nếu có gọi make_request_with_rotation)
def make_request_with_rotation(url_template, payload, key_string, timeout=300):
    # Tạo config giả và headers giả để gọi hàm chính
    fake_config = {"api_key": key_string}
    headers = {"Content-Type": "application/json"}
    
    success, result = call_gemini_with_key_rotation(url_template, headers, payload, fake_config, timeout)
    
    if success:
        # call_gemini_with_key_rotation trả về (True, response_object)
        # nhưng make_request_with_rotation thường trả về (True, json_dict)
        return (True, result.json())
    else:
        return (False, result)

    
# ========== CẬP NHẬT LẠI HÀM TẠO ẢNH (HỖ TRỢ GEMINI 2.0 FLASH) ==========
# Thay thế hàm generate_image_from_gemini cũ bằng hàm này

def generate_image_google_search(prompt: str, config: dict):
    """
    Tìm ảnh trên Google Images (Custom Search Engine).
    Trả về: (bytes_data, error_message)
    """
    import requests
    import random
    
    api_key = config.get("google_cse_key", "")
    cx = config.get("google_cse_cx", "")
    
    if not api_key or not cx:
        return (None, "Thiếu Google CSE Key hoặc CX ID trong Cài đặt.")
        
    url = "https://www.googleapis.com/customsearch/v1"
    params = {
        "key": api_key,
        "cx": cx,
        "q": prompt,
        "searchType": "image",
        "num": 3,
        "safe": "active",
        "imgSize": "large",
        "imgType": "photo"
    }
    
    print(f"🔍 [Google Search] Searching: '{prompt}'...")
    
    try:
        response = requests.get(url, params=params, timeout=30)
        if response.status_code == 200:
            data = response.json()
            items = data.get("items", [])
            if items:
                item = random.choice(items)
                link = item.get("link")
                print(f"✅ [Google Search] Found: {link}")
                
                try:
                    img_resp = requests.get(link, timeout=30)
                    if img_resp.status_code == 200:
                        return (img_resp.content, None)
                    else:
                        return (None, f"Lỗi tải ảnh gốc ({img_resp.status_code})")
                except Exception as e:
                    return (None, f"Lỗi kết nối tải ảnh: {e}")
            else:
                return (None, "Google Search trả về 0 kết quả.")
        else:
            return (None, f"Lỗi Google API ({response.status_code}): {response.text[:100]}")
    except Exception as e:
        return (None, f"Lỗi kết nối Google Search: {e}")
        
    return (None, "Lỗi không xác định.")

def generate_image_pollinations(prompt: str, config: dict):
    """
    Tạo ảnh qua Pollinations.ai (Hệ thống mới - Unified API).
    CẬP NHẬT FIX LỖI: Chặn AI vẽ chữ (text) vào hình.
    """
    import requests
    import random
    import urllib.parse
    import time
    
    # 1. Lấy danh sách Key
    key_input = config.get("pollinations_api_key", "")
    keys = []
    if isinstance(key_input, list):
        keys = [k.strip() for k in key_input if k.strip()]
    else:
        raw_str = str(key_input)
        if '\n' in raw_str:
             keys = [k.strip() for k in raw_str.split('\n') if k.strip()]
        else:
             keys = [k.strip() for k in raw_str.split(',') if k.strip()]
    if not keys: keys = [""]

    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    ]

    # Model Flux (Mạnh nhất)
    models_to_try = ["flux", "flux-realism", "turbo"]
    
    # --- [CẢI TIẾN] XỬ LÝ PROMPT CHÍNH XÁC HƠN ---
    # Gửi prompt gốc trực tiếp, không thêm prefix gây méo nghĩa
    # Chỉ thêm style boosters nhẹ để AI vẽ đẹp hơn
    clean_prompt = prompt.strip()
    # Thêm negative tags ngay trong prompt để AI hiểu
    enhanced_prompt = f"{clean_prompt}, no text, no letters, no writing, no watermark, no logo"
    
    safe_prompt = urllib.parse.quote(enhanced_prompt)
    
    # Tạo Negative prompt (Những thứ cấm xuất hiện: chữ, logo, watermark)
    negative = "text, watermark, writing, letters, typography, logo, signature, ugly, deformed"
    safe_negative = urllib.parse.quote(negative)

    last_error = "Unknown"
    key_index = 0
    
    for model in models_to_try:
        attempts_for_model = 0
        max_attempts_per_model = max(1, len(keys)) 
        
        while attempts_for_model < max_attempts_per_model:
            current_api_key = keys[key_index]
            seed = random.randint(1, 999999999)
            
            # --- URL ĐÃ CẬP NHẬT ---
            # 1. nologo=true: Bỏ logo Pollinations
            # 2. enhance=false: TẮT tự động enhance của hệ thống (vì nó hay tự thêm chữ vào)
            # 3. negative_prompt: Cấm chữ viết
            base_url = (f"https://image.pollinations.ai/prompt/{safe_prompt}?"
                        f"width=1024&height=1024&nologo=true&seed={seed}&enhance=false"
                        f"&negative_prompt={safe_negative}")
            
            if model:
                url = f"{base_url}&model={model}"
            else:
                url = base_url
            
            # Log kiểm tra
            print(f"🌍 [Pollinations Fix] Vẽ: '{clean_prompt}' | Model: {model} | No-Text Mode")
            
            try:
                headers = {"User-Agent": random.choice(user_agents)}
                if current_api_key:
                    headers["Authorization"] = f"Bearer {current_api_key}"
                
                response = requests.get(url, headers=headers, timeout=60)
                
                if response.status_code == 200:
                    content_type = response.headers.get("Content-Type", "")
                    if "image" in content_type and len(response.content) > 1000:
                        return (response.content, None)
                    else:
                        last_error = f"Response rác ({content_type})"
                        break 
                elif response.status_code == 429:
                    print(f"   ⚠️ Rate Limit. Đổi key...")
                    key_index = (key_index + 1) % len(keys)
                    attempts_for_model += 1
                    time.sleep(2)
                    continue
                else:
                    last_error = f"HTTP {response.status_code}"
                    print(f"   ⚠️ Lỗi {response.status_code}. Thử model khác...")
                    break 
            except Exception as e:
                last_error = f"Conn Err: {str(e)}"
                break
                
        time.sleep(1)
            
    return (None, f"Pollinations Error: {last_error}")

def generate_image_ai_horde(prompt: str):
    """
    Tạo ảnh qua AI Horde (Stable Horde) - Mạng lưới GPU cộng đồng.
    Ưu điểm: Miễn phí, không cần Key (dùng Anonymous), không bị 502 Overload.
    Nhược điểm: Chậm (cần chờ 30-60s xếp hàng).
    """
    import requests
    import time
    import random
    
    # URL API
    BASE_URL = "https://stablehorde.net/api/v2"
    
    # Key ẩn danh (Hợp lệ, được phép dùng)
    API_KEY = "0000000000"
    
    headers = {
        "apikey": API_KEY,
        "Client-Agent": "AnkiGemini:1.0:Unknown"
    }
    
    # 1. Gửi yêu cầu tạo ảnh
    payload = {
        "prompt": prompt + ", highly detailed, 4k",
        "params": {
            "sampler_name": "k_euler",
            "cfg_scale": 7.5,
            "steps": 25,
            "n": 1,
            "width": 512,
            "height": 512
        },
        "nsfw": False,
        "censor_nsfw": True,
        "models": ["stable_diffusion"] # Model cơ bản luôn có worker
    }
    
    print(f"🛡️ [AI Horde] Đang gửi yêu cầu xếp hàng: '{prompt}'...")
    
    try:
        req = requests.post(f"{BASE_URL}/generate/async", json=payload, headers=headers, timeout=30)
        if req.status_code != 202:
            return (None, f"Horde Error {req.status_code}: {req.text[:100]}")
            
        uuid = req.json().get("id")
        if not uuid:
            return (None, "Horde không trả về UUID.")
            
        print(f"⏳ [AI Horde] Đã vào hàng đợi (ID: {uuid}). Đang chờ thợ vẽ...")
        
        # 2. Polling (Chờ ảnh)
        # Timeout tổng cộng 90 giây
        start_time = time.time()
        while time.time() - start_time < 90:
            time.sleep(3) # Check mỗi 3 giây
            
            check_url = f"{BASE_URL}/generate/check/{uuid}"
            status_resp = requests.get(check_url, timeout=20)
            status_data = status_resp.json()
            
            done = status_data.get("done", False)
            wait_time = status_data.get("wait_time", 0)
            
            if done:
                # 3. Lấy ảnh về
                final_url = f"{BASE_URL}/generate/status/{uuid}"
                final_resp = requests.get(final_url, timeout=30)
                final_data = final_resp.json()
                
                generations = final_data.get("generations", [])
                if generations:
                    img_url = generations[0].get("img")
                    print(f"✅ [AI Horde] Xong! Đang tải ảnh: {img_url}")
                    
                    # Download ảnh từ URL kết quả
                    img_download = requests.get(img_url, timeout=30)
                    if img_download.status_code == 200:
                        return (img_download.content, None)
                
                return (None, "Horde hoàn tất nhưng không thấy URL ảnh.")
            
            # Update trạng thái
            if wait_time > 0:
                print(f"   ...Còn {status_data.get('queue_position')} người trước bạn (Chờ ~{wait_time}s)...")
                
        return (None, "Horde Timeout (Quá 90s chờ đợi).")
        
    except Exception as e:
        return (None, f"AI Horde Exception: {e}")

def generate_image_google(prompt: str, config: dict):
    """
    Tạo ảnh bằng Google Imagen 3 (thông qua Gemini API).
    Trả về: (bytes_data, error_message)
    """
    import requests
    import base64
    
    api_key = config.get("image_api_key") or config.get("api_key")
    if not api_key and "api_keys" in config and isinstance(config["api_keys"], list) and config["api_keys"]:
        api_key = config["api_keys"][0]
    if not api_key:
        return (None, "Thiếu Gemini API Key trong Cài đặt.")
        
    # Xử lý trường hợp nhiều key
    if isinstance(api_key, list): api_key = api_key[0]
    if "\n" in api_key: api_key = api_key.split("\n")[0]
        
    # FIX: Đảm bảo model là Imagen, không phải Gemini Flash (Vốn không vẽ được)
    model = config.get("image_model", "imagen-3.0-generate-001")
    if "gemini" in model.lower() or not model.startswith("imagen"):
        model = "imagen-3.0-generate-001"
        
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict?key={api_key}"
    
    headers = {"Content-Type": "application/json"}
    
    payload = {
        "instances": [{"prompt": prompt}],
        "parameters": {"sampleCount": 1, "aspectRatio": "1:1"}
    }
    
    print(f"🚀 [Google Imagen] Requesting model: {model}...")
    
    try:
        response = requests.post(url, headers=headers, json=payload, timeout=60)
        
        if response.status_code == 200:
            result = response.json()
            if "predictions" in result and result["predictions"]:
                b64_data = result["predictions"][0]["bytesBase64Encoded"]
                print("✅ [Google Imagen] Tạo ảnh thành công!")
                return (base64.b64decode(b64_data), None)
            else:
                return (None, f"Google API trả về không có ảnh: {result}")
        else:
            err_msg = response.text[:200]
            if response.status_code == 403:
                return (None, "API Key không có quyền truy cập Imagen 3 (Cần tài khoản trả phí hoặc Whitelist).")
            if response.status_code == 404:
                return (None, f"Model '{model}' không tồn tại hoặc sai Endpoint.")
            return (None, f"Lỗi Google API ({response.status_code}): {err_msg}")
            
    except Exception as e:
        return (None, f"Lỗi kết nối Google Imagen: {e}")
        
    return (None, "Lỗi không xác định.")

## ==========================================
# CẤU HÌNH LOCAL IMAGE GENERATION (SUBPROCESS)
# ==========================================
def generate_image_from_gemini(keyword: str, config: dict, definition_en=None, context=None, pos_type=None):
    """
    Hàm Router thông minh tối ưu cho người dùng Free.
    Ưu tiên: Pollinations (Flux) -> AI Horde (Free) -> HF (Free/Token) -> Google (Paid).
    
    CẢI TIẾN: Trích xuất definition_vi từ context để làm prompt chính xác hơn.
    """
    # Trích xuất definition_vi từ context (được truyền dạng "Context: X. Meaning: Y")
    def_vi = ""
    clean_context = context or ""
    if "Meaning:" in clean_context:
        parts = clean_context.split("Meaning:")
        if len(parts) > 1:
            def_vi = parts[1].strip()
        # Lấy phần context thuần (trước "Meaning:")
        clean_context = parts[0].replace("Context:", "").strip().rstrip(".")
    
    # 1. Tạo Prompt mô tả ảnh (Gen-AI Prompt)
    # Nếu definition_en là image_query từ Gemini (dài, có tags) -> dùng trực tiếp
    if definition_en and (len(definition_en) > 100 or any(tag in definition_en.lower() for tag in ["8k", "realistic", "masterpiece", "detailed", "hyper-realistic"])):
        gen_prompt = definition_en
    else:
        # Dùng definition_vi làm definition_en nếu nó có ý nghĩa hơn
        better_def = definition_en
        if def_vi and (not definition_en or len(definition_en) < 20):
            better_def = def_vi
        gen_prompt = generate_image_prompt(
            keyword=keyword, 
            definition_en=better_def, 
            context=clean_context, 
            pos_type=pos_type
        )
    
    # 2. Prompt tìm kiếm (dùng cho Google Search nếu cần)
    search_prompt = f"{keyword} {clean_context if clean_context else ''} visual illustration"

    priority = config.get("image_engine_priority", "auto")
    error_logs = []

    # --- ROUTE 1: POLLINATIONS (FLUX) - MIỄN PHÍ & ĐẸP NHẤT ---
    if priority in ["auto", "pollinations"]:
        print(f"🚀 [Router] Đang tạo ảnh Flux (Free) cho: {keyword}")
        img_data, err = generate_image_pollinations(gen_prompt, config) 
        if img_data: return (True, img_data)
        error_logs.append(f"Pollinations: {err}")

    # --- ROUTE 2: AI HORDE (GPU CỘNG ĐỒNG) - MIỄN PHÍ 100% ---
    if priority in ["auto", "horde"]:
        print("🚀 [Router] Đang thử AI Horde (Free Community GPU)...")
        if 'generate_image_ai_horde' in globals():
            img_data, err = generate_image_ai_horde(gen_prompt)
            if img_data: return (True, img_data)
            error_logs.append(f"AI Horde: {err}")

    # --- ROUTE 3: HUGGING FACE (SỬA LỖI TOKEN) ---
    if priority in ["auto", "hf"]:
        print("🚀 [Router] Đang thử Hugging Face Inference...")
        # Sử dụng hàm generate_image_huggingface có sẵn ở đầu file main.py
        if 'generate_image_huggingface' in globals():
            img_data = generate_image_huggingface(gen_prompt, config)
            if img_data: return (True, img_data)
            error_logs.append("Hugging Face: Chưa có token, token hết hạn hoặc model bận")

    # --- ROUTE 4: GOOGLE SEARCH (NẾU CÓ KEY) ---
    if (priority == "google_search") or (priority == "auto" and config.get("google_cse_key")):
        if 'generate_image_google_search' in globals():
            img_data, err = generate_image_google_search(search_prompt, config)
            if img_data: return (True, img_data)
            error_logs.append(f"Google Search: {err}")

    # --- ROUTE 5: GOOGLE IMAGEN (CHỈ CHẠY NẾU CÓ KEY THANH TOÁN) ---
    if priority == "google":
        # Kiểm tra xem có Key Imagen riêng không
        if config.get("image_api_key") or config.get("api_key") or config.get("api_keys"):
            print("🚀 [Router] Đang thử Google Imagen (Paid)...")
            if 'generate_image_google' in globals():
                img_data, err = generate_image_google(gen_prompt, config)
                if img_data: return (True, img_data)
                error_logs.append(f"Google Imagen: {err}")
        else:
            error_logs.append("Google Imagen: Require Paid API Key")

    final_error = " | ".join(error_logs)
    return (False, f"❌ Không thể tạo ảnh từ các nguồn miễn phí: {final_error}")

# ==============================================================================
# [NEW MODULE] SPECIALIZED TRANSLATION & INTERPRETING PRACTICE
# ==============================================================================

# --- CONSTANTS ---
SPECIALIZED_DOMAINS = [
    "Legal (Contracts/Court)", "Medical (Clinical/Pharma)", 
    "Business (Finance/Marketing)", "Technical (IT/Engineering)", 
    "Diplomatic (Polisci/IR)", "Logistics & Supply Chain",
    "Literary & Media", "Academic (Research/Education)", "Environmental Science",
    "Healthcare & Public Health", "Tourism & Hospitality", "Real Estate & Property Management",
    "Automotive & Transportation", "Retail & E-commerce", "Agriculture & Food Industry",
    "Energy & Utilities", "Telecommunications", "Human Resources & Recruitment",
    "Arts & Culture", "Sports & Recreation"
]

PROMPT_TRANSLATION_DRILL = """
Generate a specialized translation drill for the word "{word}" in the context of "{domain}".
Role: Senior Translator & Trainer.

Output JSON:
{{
    "context_type": "{domain}",
    "source_text": "A professional, dense paragraph (40-60 words) naturally using '{word}'. High formal register.",
    "model_translation_vi": "A high-quality, professional Vietnamese translation (North/Standard).",
    "terminology_notes": [
        {{"term": "Related term 1", "meaning": "Brief explanation", "collocation": "Common phrase"}},
        {{"term": "Related term 2", "meaning": "Brief explanation", "collocation": "Common phrase"}}
    ],
    "stylistic_tips": "Advice on tone, register, or false friends for this specific text."
}}
"""

PROMPT_INTERPRETING_DRILL = """
Generate an interpreting practice set for "{word}" ({domain}).
Role: Conference Interpreter Trainer.

Output JSON:
{{
    "drills": [
        {{
            "level": "Consecutive (Short)",
            "source_segment": "A single, punchy sentence (10-15 words) containing '{word}'.",
            "target_segment": "The ideal oral interpretation.",
            "chunking_cues": "Source / text / broken / into / logical / chunks."
        }},
        {{
            "level": "Simultaneous (Complex)",
            "source_segment": "A complex sentence (25+ words) with multiple clauses containing '{word}'.",
            "target_segment": "The ideal oral interpretation.",
            "chunking_cues": "Source / text / broken / into / logical / chunks."
        }}
    ],
    "shadowing_text": "A flowy paragraph suitable for shadowing practice, using '{word}'."
}}
"""

# --- 1. FIELD UPGRADER ---
def upgrade_note_type_specialized():
    """Safely adds specialized fields to the current Note Type if missing."""
    model = mw.col.models.current()
    if model is None:
        showInfo("Please select a note type (open Add Cards or Browser) first.")
        return

    new_fields = ["Translation_Practice", "Interpreting_Drills", "Domain_Tag", "Difficulty_Tag"]
    existing_fields = mw.col.models.field_names(model)
    
    added_count = 0
    for nf in new_fields:
        if nf not in existing_fields:
            mw.col.models.add_field(model, mw.col.models.new_field(nf))
            added_count += 1
            
    if added_count > 0:
        # Update template to show these fields in a specialized tab/section if desired
        # For now, we just add the fields so data can be stored.
        mw.col.models.save(model)
        showInfo(f"✅ Successfully added {added_count} specialized fields to '{model['name']}'.\n\nYou can now use the specialized buttons.")
    else:
        showInfo("ℹ️ All specialized fields already exist in this Note Type.")

# --- 2. DOMAIN AUTO-TAGGER ---
def auto_tag_domain_logic(editor):
    """Analyzes context and adds Domain/Difficulty tags."""
    if not editor.note: return
    note = editor.note
    word = note["Word"] if "Word" in note else ""
    context = note["Context"] if "Context" in note else ""
    
    if not word: 
        tooltip("⚠️ Please enter a Word first.")
        return

    config = load_config()
    prompt = f"""
    Classify the word "{word}" (Context: {context}) into ONE primary domain and ONE difficulty level.
    Domains: {', '.join(SPECIALIZED_DOMAINS)}.
    Difficulty: Beginner, Intermediate, Advanced, Expert.
    
    JSON Output: {{"domain": "Name", "difficulty": "Level"}}
    """
    
    tooltip("🏷️ Analyzing domain...")
    
    def worker():
        # Reuse existing call structure
        model = config.get("model", GEMINI_DEFAULT_MODEL)
        url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
        headers = {"Content-Type": "application/json"}
        payload = {"contents": [{"parts": [{"text": prompt}]}]}
        return call_gemini_with_key_rotation(url_template, headers, payload, config)

    def on_done(future):
        success, result = future.result()
        if success:
            try:
                # Extract JSON from response object
                res_json = result.json()
                content = res_json["candidates"][0]["content"]["parts"][0]["text"]
                
                json_match = re.search(r'\{.*\}', content, re.DOTALL)
                if json_match:
                    data = json.loads(json_match.group(0))
                    
                    # Update Tags
                    domain_tag = data.get("domain", "General").replace(" ", "_")
                    diff_tag = data.get("difficulty", "Intermediate")
                    
                    note.add_tag(f"Domain::{domain_tag}")
                    note.add_tag(f"Level::{diff_tag}")
                    
                    # Update Fields if they exist
                    if "Domain_Tag" in note: note["Domain_Tag"] = data.get("domain", "")
                    if "Difficulty_Tag" in note: note["Difficulty_Tag"] = diff_tag
                    
                    editor.loadNote()
                    tooltip(f"🏷️ Tagged: {domain_tag} | {diff_tag}")
            except Exception as e:
                print(e)
                tooltip("⚠️ Could not parse domain info.")
        else:
            tooltip(f"❌ Error: {result}")
    
    mw.taskman.run_in_background(worker, on_done)
# ========== CÁC HÀM BỊ THIẾU - THÊM VÀO CUỐI FILE TRƯỚC setup_menu() ==========

def _run_drill_for_editor(editor, create_func, format_func, title):
    """Tạo bài tập dịch / phiên dịch từ nút trên editor.
    Bản cũ tìm editor.card (màn hình Add không có card) và chèn HTML vào một container
    không tồn tại trong editor, nên bấm nút không thấy gì. Giờ lấy từ trực tiếp từ note
    và hiện kết quả trong cửa sổ riêng."""
    note = getattr(editor, "note", None)
    word = clean_field_text(get_note_field_value(note, ["Word", "Từ vựng", "Keyword", "Expression"])) if note else ""
    if not word:
        tooltip("⚠️ Vui lòng nhập từ vào trường 'Word' trước")
        return

    config = load_config()
    parent = getattr(editor, "parentWindow", None) or mw
    tooltip(f"🔄 Đang tạo {title.lower()} cho '{word}'...")

    def on_done(future):
        try:
            success, result = future.result()
        except Exception as e:
            success, result = False, str(e)
        if success:
            show_rich_result_dialog(f"{title}: {word}", format_func(result, word), is_markdown=False, parent=parent)
        else:
            showCritical(f"❌ Lỗi tạo {title.lower()}: {result}")

    mw.taskman.run_in_background(lambda: create_func(word, config), on_done)

def generate_translation_drill_logic(editor):
    """Nút 📝 trên editor: tạo bài tập dịch"""
    _run_drill_for_editor(editor, create_translation_drill, format_translation_drill_html, "📝 Bài tập dịch")

def generate_interpreting_drill_logic(editor):
    """Nút 🎧 trên editor: tạo bài tập phiên dịch"""
    _run_drill_for_editor(editor, create_interpreting_drill, format_interpreting_drill_html, "🎧 Bài tập phiên dịch")

def create_translation_drill(word: str, config: dict):
    """Tạo bài tập dịch thuật"""
    print(f"🔄 Tạo bài tập dịch cho từ: '{word}'")
    
    prompt = f"""
Bạn là một giáo viên ngôn ngữ chuyên nghiệp. Hãy tạo 5 bài tập dịch thuật cho từ "{word}" với các mức độ khó khác nhau.

YÊU CẦU:
1. Mỗi bài tập phải có một câu tiếng Anh có chứa từ "{word}"
2. Cung cấp bản dịch tiếng Việt chính xác
3. Giải thích ngắn gọn về cách sử dụng từ trong ngữ cảnh đó
4. Phân loại độ khó: dễ (easy), trung bình (medium), khó (hard)

Định dạng JSON:
{{
    "exercises": [
        {{
            "id": 1,
            "english": "Một câu tiếng Anh tự nhiên có chứa từ '{word}'",
            "vietnamese": "Bản dịch tiếng Việt chính xác và tự nhiên",
            "explanation": "Giải thích ngắn về cách dùng từ trong ngữ cảnh này",
            "difficulty": "easy",
            "translation_tips": "Mẹo dịch thuật hữu ích"
        }},
        {{
            "id": 2,
            "english": "Câu tiếng Anh khó hơn có chứa từ '{word}'",
            "vietnamese": "Bản dịch tiếng Việt",
            "explanation": "Giải thích chi tiết hơn",
            "difficulty": "medium",
            "translation_tips": "Mẹo dịch cho câu phức tạp"
        }}
    ]
}}

Chỉ trả về JSON, không có text nào khác.
"""
    
    # Gọi API Gemini
    model = config.get("model", GEMINI_DEFAULT_MODEL)
    url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        print(f"🌐 Gửi request tới Gemini cho bài tập dịch...")
        
        # Sử dụng key rotation
        success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout=60)
        
        if not success:
            print(f"❌ Lỗi API: {result}")
            return (False, f"Lỗi API: {result}")
            
        # result là response object
        response = result
        raw_response = response.json()
        
        if "candidates" not in raw_response or not raw_response["candidates"]:
            print("❌ Không có candidates trong response")
            return (False, "Không nhận được phản hồi từ Gemini")
            
        content_text = raw_response["candidates"][0]["content"]["parts"][0]["text"]
        print(f"✅ Đã nhận response: {len(content_text)} ký tự")
        
        # Trích xuất JSON từ response
        json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                data = json.loads(json_str)
                print(f"✅ Parse JSON thành công, có {len(data.get('exercises', []))} bài tập")
                return (True, data)
            except json.JSONDecodeError as e:
                print(f"❌ Lỗi parse JSON: {e}")
                return (False, "Lỗi parse JSON bài tập dịch")
        else:
            print("❌ Không tìm thấy JSON trong response")
            return (False, "Không tìm thấy dữ liệu JSON trong phản hồi")
            
    except Exception as e:
        print(f"❌ Lỗi kết nối: {str(e)}")
        import traceback
        traceback.print_exc()
        return (False, f"Lỗi kết nối: {str(e)}")

def create_interpreting_drill(word: str, config: dict):
    """Tạo bài tập phiên dịch"""
    print(f"🔄 Tạo bài tập phiên dịch cho từ: '{word}'")
    
    prompt = f"""
Bạn là một phiên dịch viên chuyên nghiệp. Hãy tạo 5 bài tập phiên dịch (interpreting) cho từ "{word}" trong các tình huống giao tiếp thực tế.

YÊU CẦU:
1. Mỗi bài tập phải có một tình huống giao tiếp cụ thể
2. Câu tiếng Anh chứa từ "{word}" cần được phiên dịch
3. Bản dịch tiếng Việt phải tự nhiên, phù hợp với văn hóa Việt Nam
4. Cung cấp ghi chú về văn hóa/ngữ cảnh khi cần

Định dạng JSON:
{{
    "exercises": [
        {{
            "id": 1,
            "situation": "Mô tả tình huống giao tiếp (hội nghị, cuộc họp, đàm phán, v.v.)",
            "english_phrase": "Câu tiếng Anh chứa từ '{word}' cần phiên dịch",
            "interpretation": "Bản dịch tự nhiên, phù hợp ngữ cảnh tiếng Việt",
            "cultural_note": "Ghi chú về văn hóa, cách diễn đạt trong tiếng Việt",
            "difficulty": "easy/medium/hard",
            "interpreting_tips": "Mẹo phiên dịch cho tình huống này"
        }},
        {{
            "id": 2,
            "situation": "Tình huống khác",
            "english_phrase": "Câu khó hơn chứa từ '{word}'",
            "interpretation": "Bản dịch phù hợp",
            "cultural_note": "Ghi chú văn hóa nếu có",
            "difficulty": "medium",
            "interpreting_tips": "Mẹo hữu ích"
        }}
    ]
}}

Chỉ trả về JSON, không có text nào khác.
"""
    
    # Gọi API Gemini
    model = config.get("model", GEMINI_DEFAULT_MODEL)
    url_template = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={{API_KEY}}"
    headers = {"Content-Type": "application/json"}
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    
    try:
        print(f"🌐 Gửi request tới Gemini cho bài tập phiên dịch...")
        
        # Sử dụng key rotation
        success, result = call_gemini_with_key_rotation(url_template, headers, payload, config, timeout=60)
        
        if not success:
            print(f"❌ Lỗi API: {result}")
            return (False, f"Lỗi API: {result}")
            
        # result là response object
        response = result
        raw_response = response.json()
        
        if "candidates" not in raw_response or not raw_response["candidates"]:
            print("❌ Không có candidates trong response")
            return (False, "Không nhận được phản hồi từ Gemini")
            
        content_text = raw_response["candidates"][0]["content"]["parts"][0]["text"]
        print(f"✅ Đã nhận response: {len(content_text)} ký tự")
        
        # Trích xuất JSON từ response
        json_match = re.search(r'\{.*\}', content_text, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
            try:
                data = json.loads(json_str)
                print(f"✅ Parse JSON thành công, có {len(data.get('exercises', []))} bài tập")
                return (True, data)
            except json.JSONDecodeError as e:
                print(f"❌ Lỗi parse JSON: {e}")
                return (False, "Lỗi parse JSON bài tập phiên dịch")
        else:
            print("❌ Không tìm thấy JSON trong response")
            return (False, "Không tìm thấy dữ liệu JSON trong phản hồi")
            
    except Exception as e:
        print(f"❌ Lỗi kết nối: {str(e)}")
        import traceback
        traceback.print_exc()
        return (False, f"Lỗi kết nối: {str(e)}")

def format_translation_drill_html(data, keyword):
    """Định dạng bài tập dịch thành HTML đẹp mắt"""
    if not data or "exercises" not in data or not data["exercises"]:
        return "<p>Không có dữ liệu bài tập dịch</p>"
    
    html = f"""
    <div class="translation-drill-container" style="
        border: 2px solid #4CAF50;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        background: #f9f9f9;
    ">
        <h3 style="color: #2E7D32; margin-top: 0; border-bottom: 2px solid #4CAF50; padding-bottom: 8px;">
            📝 Bài tập dịch thuật với từ: "{keyword}"
        </h3>
        <div class="exercises-list">
    """
    
    for i, exercise in enumerate(data["exercises"], 1):
        # Xác định màu sắc dựa trên độ khó
        difficulty_color = {
            "easy": "#4CAF50",
            "medium": "#FF9800",
            "hard": "#F44336"
        }.get(exercise.get("difficulty", "medium"), "#4CAF50")
        
        html += f"""
            <div class="exercise-item" style="
                background: white;
                margin: 15px 0;
                padding: 15px;
                border-radius: 8px;
                border-left: 4px solid {difficulty_color};
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            ">
                <div class="exercise-header" style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 10px;
                ">
                    <strong style="color: #1B5E20; font-size: 16px;">Bài {i}: Dịch câu sau</strong>
                    <span style="
                        background: {difficulty_color};
                        color: white;
                        padding: 4px 12px;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: bold;
                    ">
                        {exercise.get('difficulty', 'medium').upper()}
                    </span>
                </div>
                
                <div class="exercise-content" style="font-size: 14px; line-height: 1.4;">
                    <div style="margin-bottom: 10px;">
                        <strong>🇬🇧 Câu tiếng Anh:</strong>
                        <div style="
                            background: #e8f5e8;
                            padding: 10px;
                            border-radius: 6px;
                            margin: 5px 0;
                            font-style: italic;
                            border: 1px solid #c8e6c9;
                        ">
                            {exercise.get('english', '')}
                        </div>
                    </div>
                    
                    <div style="margin-bottom: 10px;">
                        <strong>🇻🇳 Bản dịch tiếng Việt:</strong>
                        <div style="
                            background: #e3f2fd;
                            padding: 10px;
                            border-radius: 6px;
                            margin: 5px 0;
                            border: 1px solid #bbdefb;
                        ">
                            {exercise.get('vietnamese', '')}
                        </div>
                    </div>
                    
                    <div style="margin-bottom: 10px;">
                        <strong>💡 Giải thích:</strong>
                        <div style="
                            padding: 8px;
                            margin: 5px 0;
                            font-size: 13px;
                            color: #555;
                        ">
                            {exercise.get('explanation', '')}
                        </div>
                    </div>
                    
                    <div style="
                        background: #fff3cd;
                        border: 1px solid #ffeaa7;
                        border-radius: 6px;
                        padding: 10px;
                        margin-top: 10px;
                        font-size: 13px;
                    ">
                        <strong>📌 Mẹo dịch thuật:</strong> {exercise.get('translation_tips', '')}
                    </div>
                </div>
            </div>
        """
    
    html += """
        </div>
        <div style="
            text-align: center;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
        ">
            <button onclick="window.location.reload()" style="
                background: #4CAF50;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
            ">
                🔄 Làm mới bài tập
            </button>
        </div>
    </div>
    """
    return html

def format_interpreting_drill_html(data, keyword):
    """Định dạng bài tập phiên dịch thành HTML đẹp mắt"""
    if not data or "exercises" not in data or not data["exercises"]:
        return "<p>Không có dữ liệu bài tập phiên dịch</p>"
    
    html = f"""
    <div class="interpreting-drill-container" style="
        border: 2px solid #9C27B0;
        border-radius: 10px;
        padding: 15px;
        margin: 10px 0;
        background: #f9f9f9;
    ">
        <h3 style="color: #7B1FA2; margin-top: 0; border-bottom: 2px solid #9C27B0; padding-bottom: 8px;">
            🎤 Bài tập phiên dịch với từ: "{keyword}"
        </h3>
        <div class="exercises-list">
    """
    
    for i, exercise in enumerate(data["exercises"], 1):
        # Xác định màu sắc dựa trên độ khó
        difficulty_color = {
            "easy": "#4CAF50",
            "medium": "#FF9800",
            "hard": "#F44336"
        }.get(exercise.get("difficulty", "medium"), "#9C27B0")
        
        html += f"""
            <div class="exercise-item" style="
                background: white;
                margin: 15px 0;
                padding: 15px;
                border-radius: 8px;
                border-left: 4px solid {difficulty_color};
                box-shadow: 0 2px 4px rgba(0,0,0,0.1);
            ">
                <div class="exercise-header" style="
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    margin-bottom: 10px;
                ">
                    <strong style="color: #7B1FA2; font-size: 16px;">Bài {i}: Phiên dịch tình huống</strong>
                    <span style="
                        background: {difficulty_color};
                        color: white;
                        padding: 4px 12px;
                        border-radius: 20px;
                        font-size: 12px;
                        font-weight: bold;
                    ">
                        {exercise.get('difficulty', 'medium').upper()}
                    </span>
                </div>
                
                <div class="exercise-content" style="font-size: 14px; line-height: 1.4;">
                    <div style="margin-bottom: 10px;">
                        <strong>📋 Tình huống:</strong>
                        <div style="
                            background: #f3e5f5;
                            padding: 10px;
                            border-radius: 6px;
                            margin: 5px 0;
                            font-style: italic;
                            border: 1px solid #e1bee7;
                        ">
                            {exercise.get('situation', '')}
                        </div>
                    </div>
                    
                    <div style="margin-bottom: 10px;">
                        <strong>🇬🇧 Câu cần phiên dịch:</strong>
                        <div style="
                            background: #e8f5e8;
                            padding: 10px;
                            border-radius: 6px;
                            margin: 5px 0;
                            font-weight: bold;
                            border: 1px solid #c8e6c9;
                        ">
                            "{exercise.get('english_phrase', '')}"
                        </div>
                    </div>
                    
                    <div style="margin-bottom: 10px;">
                        <strong>🎤 Bản phiên dịch:</strong>
                        <div style="
                            background: #e3f2fd;
                            padding: 10px;
                            border-radius: 6px;
                            margin: 5px 0;
                            border: 1px solid #bbdefb;
                        ">
                            <strong>📢 Phiên dịch viên:</strong> {exercise.get('interpretation', '')}
                        </div>
                    </div>
                    
                    <div style="margin-bottom: 10px;">
                        <strong>🌍 Ghi chú văn hóa:</strong>
                        <div style="
                            padding: 8px;
                            margin: 5px 0;
                            font-size: 13px;
                            color: #555;
                        ">
                            {exercise.get('cultural_note', '')}
                        </div>
                    </div>
                    
                    <div style="
                        background: #fff3cd;
                        border: 1px solid #ffeaa7;
                        border-radius: 6px;
                        padding: 10px;
                        margin-top: 10px;
                        font-size: 13px;
                    ">
                        <strong>💡 Mẹo phiên dịch:</strong> {exercise.get('interpreting_tips', '')}
                    </div>
                </div>
            </div>
        """
    
    html += """
        </div>
        <div style="
            text-align: center;
            margin-top: 15px;
            padding-top: 15px;
            border-top: 1px solid #ddd;
        ">
            <button onclick="window.location.reload()" style="
                background: #9C27B0;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 5px;
                cursor: pointer;
                font-size: 14px;
            ">
                🔄 Làm mới bài tập
            </button>
        </div>
    </div>
    """
    return html
def add_drill_buttons_to_template():
    """Thêm nút tạo bài tập vào template thẻ"""
    model = mw.col.models.current()
    if model is None:
        showInfo("Vui lòng mở một thẻ để cập nhật template.")
        return

    updated = False
    for template in model['tmpls']:
        current_back_template = template['afmt']

        # Thêm nút bấm vào template
        if "Tạo bài tập dịch" not in current_back_template:
            # Thêm phần bài tập dịch
            drill_section = """
<hr style="margin: 20px 0; border: 1px solid #ddd;">

<!-- Phần bài tập dịch -->
<div id="translation-drill-section" style="margin: 20px 0; padding: 15px; border: 2px solid #4CAF50; border-radius: 10px; background: #f9f9f9;">
    <h4 style="color: #2E7D32; margin-top: 0; margin-bottom: 15px;">📝 Bài tập dịch thuật</h4>
    <p style="color: #555; margin-bottom: 15px;">Tạo bài tập dịch với từ khóa này để luyện tập:</p>
    
    <button 
        id="generate-translation-btn"
        onclick="pycmd('generate_translation_drill')"
        style="
            background: #4CAF50;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            margin-right: 10px;
        "
        onmouseover="this.style.background='#388E3C'"
        onmouseout="this.style.background='#4CAF50'"
    >
        📝 Tạo bài tập dịch
    </button>

    <div id="translation-drill-container" style="margin-top: 15px;"></div>
</div>

<!-- Phần bài tập phiên dịch -->
<div id="interpreting-drill-section" style="margin: 20px 0; padding: 15px; border: 2px solid #9C27B0; border-radius: 10px; background: #f9f9f9;">
    <h4 style="color: #7B1FA2; margin-top: 0; margin-bottom: 15px;">🎤 Bài tập phiên dịch</h4>
    <p style="color: #555; margin-bottom: 15px;">Tạo bài tập phiên dịch thực tế với tình huống giao tiếp:</p>
    
    <button 
        id="generate-interpreting-btn"
        onclick="pycmd('generate_interpreting_drill')"
        style="
            background: #9C27B0;
            color: white;
            border: none;
            padding: 10px 20px;
            border-radius: 5px;
            cursor: pointer;
            font-size: 14px;
            font-weight: bold;
            margin-right: 10px;
        "
        onmouseover="this.style.background='#7B1FA2'"
        onmouseout="this.style.background='#9C27B0'"
    >
        🎤 Tạo bài tập phiên dịch
    </button>

    <div id="interpreting-drill-container" style="margin-top: 15px;"></div>
</div>

<!-- Loading indicator -->
<div id="drill-loading-indicator" style="
    display: none;
    text-align: center;
    margin: 15px 0;
    padding: 15px;
    background: #f8f9fa;
    border-radius: 8px;
    border: 2px dashed #2196F3;
">
    <div style="display: inline-flex; align-items: center; color: #2196F3;">
        <div class="spinner" style="
            width: 24px;
            height: 24px;
            border: 3px solid rgba(33, 150, 243, 0.3);
            border-radius: 50%;
            border-top-color: #2196F3;
            animation: spin 1s ease-in-out infinite;
            margin-right: 10px;
        "></div>
        <span id="loading-text" style="font-weight: bold; font-size: 14px;">Đang tạo bài tập...</span>
        <span id="loading-subtext" style="display: block; font-size: 12px; color: #666; margin-top: 5px;"></span>
    </div>
</div>

<style>
    @keyframes spin {
        0% { transform: rotate(0deg); }
        100% { transform: rotate(360deg); }
    }
    
    @keyframes bounce {
        0%, 20%, 50%, 80%, 100% {transform: translateY(0);}
        40% {transform: translateY(-5px);}
        60% {transform: translateY(-2px);}
    }
    
    #generate-translation-btn:hover, #generate-interpreting-btn:hover {
        animation: bounce 0.5s;
    }
    
    @media (max-width: 768px) {
        #generate-translation-btn, #generate-interpreting-btn {
            width: 100%;
            margin-bottom: 10px;
            padding: 12px;
            font-size: 16px;
        }
    }
</style>
"""
            current_back_template += drill_section
            template['afmt'] = current_back_template
            updated = True

    if updated:
        mw.col.models.save(model)
        showInfo("✅ Đã thêm nút bài tập dịch & phiên dịch vào template!")
    else:
        showInfo("ℹ️ Template đã có nút bài tập dịch & phiên dịch.")

# ========== ĐĂNG KÝ HOOKS ==========
def _after_note_saved(func):
    """Bọc handler nút editor: đợi editor lưu nội dung đang gõ vào note rồi mới chạy,
    để không bị đọc thiếu chữ vừa nhập ở field đang focus."""
    def handler(editor):
        if hasattr(editor, "call_after_note_saved"):
            editor.call_after_note_saved(lambda: func(editor))
        else:
            func(editor)
    return handler

# (cmd, label, tooltip, phím tắt, hàm xử lý, có cần đợi lưu note không)
EDITOR_BUTTONS = [
    ("trigger_gemini_fill_button", "✨", "✨ Auto fill vocabulary from Gemini (Ctrl+G)", "Ctrl+G", run_gemini_fill_for_editor, True),
    ("optimized_batch_add", "🚀", "🚀 Thêm hàng loạt tối ưu", None, lambda ed: show_optimized_batch_dialog(), False),
    ("sentence_check_editor", "✅", "✅ Kiểm tra câu tự đặt", None, run_sentence_check_editor, True),
    ("sentence_suggest_editor", "💡", "💡 Đề xuất cải thiện câu", None, run_sentence_suggestion_editor, True),
    ("generate_reading_vocabulary", "📖", "📖 Generate reading vocabulary", None, generate_vocabulary_from_reading, True),
    ("generate_related_reading_vocabulary", "🔗", "🔗 Generate related reading vocabulary", None, generate_related_vocabulary_from_reading, True),
    ("gemini_tts_button", "🔊", "🔊 Tạo phát âm với Gemini TTS (Ctrl+Alt+Q)", "Ctrl+Alt+Q", run_gemini_tts_for_editor, True),
    ("gemini_image_gen", "🖼️", "🖼️ Generate Image Only (Ctrl+Alt+I)", "Ctrl+Alt+I", run_standalone_image_gen, True),
    ("gemini_auto_tag", "🏷️", "🏷️ Auto-tag Domain & Difficulty", None, auto_tag_domain_logic, True),
    ("gemini_trans_drill", "📝", "📝 Generate Translation Drill", None, generate_translation_drill_logic, True),
    ("gemini_interp_drill", "🎧", "🎧 Generate Interpreting/Shadowing", None, generate_interpreting_drill_logic, True),
]

def add_all_editor_buttons(buttons, editor):
    """Thêm tất cả các nút vào thanh công cụ editor"""
    if not editor:
        return buttons
    for cmd, label, tip, keys, func, needs_saved_note in EDITOR_BUTTONS:
        try:
            buttons.append(editor.addButton(
                icon=None,
                cmd=cmd,
                func=_after_note_saved(func) if needs_saved_note else func,
                tip=tip,
                keys=keys,
                label=label,
            ))
        except Exception as e:
            print(f"❌ Lỗi khi thêm nút {label} vào editor: {e}")
    return buttons

# Hooks cho chức năng chính
gui_hooks.editor_did_init_buttons.append(add_all_editor_buttons)
gui_hooks.browser_menus_did_init.append(add_browser_menu_item)
gui_hooks.browser_will_show_context_menu.append(add_browser_context_menu_item)

# Hook cho pycmd từ template thẻ (luyện câu, bài tập dịch...)
gui_hooks.webview_did_receive_js_message.append(handle_webview_message)

# Hook cho menu Tools
gui_hooks.main_window_did_init.append(setup_menu)

print("✅ Gemini Editor Filler đã được tải thành công!")
