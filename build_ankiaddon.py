# -*- coding: utf-8 -*-
"""Đóng gói add-on để đăng lên AnkiWeb, ĐẢM BẢO không lọt API key nào.

Cách dùng (chạy ở thư mục add-on, KHÔNG cần mở Anki):
    python build_ankiaddon.py

Kết quả: dist/auto_vocab_gemini.ankiaddon  (file này mới được đem đi upload)

Cách hoạt động (an toàn theo kiểu "danh sách cho phép"):
1. Chỉ copy những file nằm trong ALLOWED_FILES / ALLOWED_DIRS. File mới tạo, file .bak,
   meta.json, user_files, .git, website... tự động KHÔNG vào gói.
2. config.json trong gói bị ép sạch: mọi mục giống key/token đều bị xoá về rỗng.
3. Quét toàn bộ nội dung gói tìm:
   - mọi key thật đang có trong meta.json, các file .bak và user_files của BẠN (so khớp chính xác), và
   - mọi chuỗi trông giống key (AIza..., AQ.Ab8..., gsk_..., sk_..., hf_..., pk_...).
   Thấy bất kỳ cái nào thì HUỶ gói, không tạo file .ankiaddon, thoát với mã lỗi.
Script này không sửa và không xoá key của bạn; chỉ tạo bản sao sạch.
"""
import glob
import json
import os
import re
import shutil
import sys
import tempfile
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "dist")
OUT_FILE = os.path.join(OUT_DIR, "auto_vocab_gemini.ankiaddon")

# Chỉ những thứ này được vào gói. Muốn đưa thêm file vào gói thì thêm vào đây.
ALLOWED_FILES = [
    "__init__.py", "main.py", "guide_content.py", "manifest.json", "config.json",
    "back_template.txt", "front template.txt", "styling.txt", "README.md",
]
ALLOWED_DIRS = {"data": (".sqlite",)}   # thư mục -> đuôi file được phép

KEYLIKE_FIELD = re.compile(r"key|token|secret|password|cse|\bcx\b|hf_", re.I)
KEY_PATTERNS = [
    re.compile(rb"AIza[0-9A-Za-z_\-]{20,}"),
    re.compile(rb"AQ\.Ab8[0-9A-Za-z_\-]{20,}"),
    re.compile(rb"gsk_[0-9A-Za-z]{20,}"),
    re.compile(rb"\b[sp]k_[0-9A-Za-z]{16,}"),
    re.compile(rb"hf_[0-9A-Za-z]{20,}"),
]


def is_placeholder(match: bytes) -> bool:
    """gsk_xxxxxxxxxxxx là chữ mẫu trong ô nhập, không phải key."""
    body = re.sub(rb"^(AIza|AQ\.Ab8|gsk_|[sp]k_|hf_)", b"", match)
    return set(body.lower()) <= {b"x"[0], b"."[0], b"_"[0], b"-"[0]}


def collect_real_secrets() -> set:
    """Gom mọi key thật của bạn trong thư mục này để dò xem có lọt vào gói không."""
    secrets = set()

    def add(value):
        if isinstance(value, str):
            for part in re.split(r"[\s,;]+", value):
                if len(part) >= 12 and "*" not in part:
                    secrets.add(part)
        elif isinstance(value, list):
            for item in value:
                add(item)
        elif isinstance(value, dict):
            for k, v in value.items():
                if KEYLIKE_FIELD.search(str(k)):
                    add(v)
                elif isinstance(v, (dict, list)):
                    add(v)

    def from_json_file(path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return
        data = data.get("config", data) if isinstance(data, dict) else data
        if isinstance(data, dict):
            for k, v in data.items():
                if KEYLIKE_FIELD.search(str(k)):
                    add(v)

    from_json_file(os.path.join(HERE, "meta.json"))
    for path in glob.glob(os.path.join(HERE, "meta.json.bak*")):
        from_json_file(path)
    # Mọi chuỗi giống key nằm trong file .bak / user_files cũng tính là key thật
    candidates = glob.glob(os.path.join(HERE, "*.bak*")) + glob.glob(os.path.join(HERE, "user_files", "**", "*"), recursive=True)
    for path in candidates:
        if not os.path.isfile(path):
            continue
        try:
            with open(path, "rb") as f:
                blob = f.read()
        except OSError:
            continue
        for pat in KEY_PATTERNS:
            for m in pat.findall(blob):
                if not is_placeholder(m):
                    secrets.add(m.decode("utf-8", "ignore"))
    return secrets


def sanitize_config(path):
    """Ép config.json trong gói về rỗng ở mọi mục giống key."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    def clean(obj):
        if isinstance(obj, dict):
            return {k: (([] if isinstance(v, list) else "") if KEYLIKE_FIELD.search(str(k)) and not isinstance(v, bool)
                        else clean(v)) for k, v in obj.items()}
        return obj

    with open(path, "w", encoding="utf-8") as f:
        json.dump(clean(data), f, ensure_ascii=False, indent=2)
        f.write("\n")


def main():
    staging = tempfile.mkdtemp(prefix="avg_build_")
    try:
        # 1. Copy theo danh sách cho phép
        for name in ALLOWED_FILES:
            src = os.path.join(HERE, name)
            if not os.path.isfile(src):
                print(f"❌ Thiếu file bắt buộc: {name}")
                return 1
            shutil.copy2(src, os.path.join(staging, name))
        for folder, exts in ALLOWED_DIRS.items():
            src_dir = os.path.join(HERE, folder)
            if not os.path.isdir(src_dir):
                print(f"❌ Thiếu thư mục bắt buộc: {folder}")
                return 1
            os.makedirs(os.path.join(staging, folder), exist_ok=True)
            for name in os.listdir(src_dir):
                if name.lower().endswith(exts):
                    shutil.copy2(os.path.join(src_dir, name), os.path.join(staging, folder, name))

        # 2. Ép config.json sạch
        sanitize_config(os.path.join(staging, "config.json"))

        # 3. Quét toàn bộ gói
        secrets = collect_real_secrets()
        print(f"🔎 Đang kiểm tra gói với {len(secrets)} key thật của bạn + mẫu hình key...")
        problems = []
        for root, _, files in os.walk(staging):
            for name in files:
                path = os.path.join(root, name)
                rel = os.path.relpath(path, staging).replace(os.sep, "/")
                with open(path, "rb") as f:
                    blob = f.read()
                for s in secrets:
                    if s.encode("utf-8") in blob:
                        problems.append(f"{rel}: chứa một key thật (đuôi ...{s[-4:]})")
                for pat in KEY_PATTERNS:
                    for m in pat.findall(blob):
                        if not is_placeholder(m):
                            problems.append(f"{rel}: có chuỗi giống key (đuôi ...{m[-4:].decode('utf-8', 'ignore')})")
        if problems:
            print("\n⛔ DỪNG: phát hiện key trong gói, KHÔNG tạo file .ankiaddon:")
            for p in dict.fromkeys(problems):
                print("   -", p)
            print("\nHãy xoá key khỏi file đó rồi chạy lại.")
            if os.path.exists(OUT_FILE):
                os.remove(OUT_FILE)   # không để lại bản cũ có thể lẫn key
            return 2

        # 4. Nén: file nằm ngay gốc gói (AnkiWeb yêu cầu), không kèm __pycache__
        os.makedirs(OUT_DIR, exist_ok=True)
        with zipfile.ZipFile(OUT_FILE, "w", zipfile.ZIP_DEFLATED) as z:
            for root, _, files in os.walk(staging):
                for name in sorted(files):
                    path = os.path.join(root, name)
                    z.write(path, os.path.relpath(path, staging).replace(os.sep, "/"))
        size_mb = os.path.getsize(OUT_FILE) / 1048576
        print(f"\n✅ Sạch key. Đã tạo: {OUT_FILE} ({size_mb:.1f} MB)")
        print("   Trong gói: " + ", ".join(sorted(zipfile.ZipFile(OUT_FILE).namelist())))
        return 0
    finally:
        shutil.rmtree(staging, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
