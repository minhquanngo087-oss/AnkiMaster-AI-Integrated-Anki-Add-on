# ✨ Gemini Flashcard Generator for Anki

Gemini Flashcard Generator is an **Anki add-on** that helps you create and improve flashcards with AI. Simply enter a vocabulary item, and the add-on can generate its meaning, pronunciation, examples, related words, practice exercises, and other useful learning content.

In addition to generating learning content, the add-on can create illustrative images and pronunciation audio, and provide reading, sentence-writing, and translation practice.

It is designed primarily for **Vietnamese learners of English**. Beside, Japanese, Korean, and German language support is currently under development.

## 📚 Table of Contents

- [✨ Gemini Flashcard Generator for Anki](#-gemini-flashcard-generator-for-anki)
  - [📚 Table of Contents](#-table-of-contents)
  - [🚀 Key Features](#-key-features)
  - [📥 Installation](#-installation)
  - [⚡ Quick Start](#-quick-start)
  - [⚙️ Add-on Settings](#️-add-on-settings)
    - [🔑 AI Provider and API Key Setup](#-ai-provider-and-api-key-setup)
    - [🖼️ Image Generation Settings](#️-image-generation-settings)
    - [🔊 Text-to-Speech Settings](#-text-to-speech-settings)
  - [🎯 How to Use](#-how-to-use)
    - [🔘 Buttons in the Card Editor](#-buttons-in-the-card-editor)
    - [🧰 Tools Menu](#-tools-menu)
    - [🖱️ Anki Browser Context Menu](#️-anki-browser-context-menu)
  - [🧭 Using Context to Guide Results](#-using-context-to-guide-results)
  - [🔄 API Key and Usage Limit Management](#-api-key-and-usage-limit-management)
  - [🗂️ Starter Deck and Card Design](#️-starter-deck-and-card-design)
  - [📦 Publishing to AnkiWeb (for the developer)](#-publishing-to-ankiweb-for-the-developer)
  - [📖 Offline Dictionary](#-offline-dictionary)

## 🚀 Key Features

- **Automatic flashcard content generation:** Enter a vocabulary item, and the add-on uses AI to generate information such as pronunciation, part of speech, English and Vietnamese definitions, example sentences, synonyms, antonyms, word families, collocations, phrasal verbs, idioms, and exercises.
- **Context-based meaning guidance:** Provide a topic or part of speech to help the AI identify the meaning you want to study. For example, `run [verb]` asks the AI to explain *run* as a verb.
- **Spelling error detection:** Identifies genuine spelling mistakes, such as `ohld` instead of `hold`. It does not incorrectly change valid plural forms, past-tense forms, or capitalization.
- **Image generation:** Creates images related to vocabulary to make words easier to visualize and remember.
- **Pronunciation audio:** Generates spoken audio for words or learning content. Supported languages include English, Vietnamese, Chinese, Japanese, Korean, and German.
- **Bulk card creation:** Paste a vocabulary list to create multiple flashcards at once instead of entering each word individually.
- **Duplicate check before using AI:** Words that already exist in your deck are detected first, so no AI quota is spent on them. You will see: *"Từ vựng [word] này đã tồn tại trong bộ thẻ [deck], vui lòng thêm từ khác."* In bulk adding, existing words (and repeated words in the list) are skipped and listed for you.
- **Bulk card updates:** Select existing cards in Anki Browser to add missing information or improve their content.
- **Reading passage generation:** Creates a short passage using the target vocabulary, then identifies related vocabulary and grammar structures in the passage.
- **Sentence practice:** Checks sentences you write and suggests ways to make them more natural and accurate. Feedback is provided in Vietnamese.
- **Translation and interpreting practice:** Generates translation or interpreting exercises across different fields, including business, law, medicine, and technology.
- **Automatic API Key switching:** If an API Key reaches its usage limit or becomes unavailable, the add-on can switch to another configured key and continue processing.
- **Usage tracking:** Estimates how many requests or flashcards you can generate each day for each AI model.
- **Offline dictionary:** Quickly looks up common English words without contacting an AI service or using API quota.
- **Remembering your edits:** The add-on saves pronunciation and Vietnamese definitions that you have edited manually, so they can be prioritized when generating future cards.

## 📥 Installation

1. Copy the add-on folder into Anki's add-ons directory:
   - **Windows:** `%APPDATA%\Anki2\addons21\`
   - **macOS:** `~/Library/Application Support/Anki2/addons21/`
   - **Linux:** `~/.local/share/Anki2/addons21/`
2. Restart Anki.
3. Open **Tools → Gemini Editor Settings…** and configure your API Key before using the add-on.

## ⚡ Quick Start

1. Open the **Add** window in Anki and choose the deck and note type **Gemini Vocabulary** (created automatically on first run), or open the card editor in **Browser**.
2. Enter the word you want to study in the **Word** field. For example: `stakeholder`.
3. Press **Ctrl + G** or click the ✨ button on the toolbar.
4. The add-on analyzes the word and fills in the relevant information. If automatic image generation is enabled, it will also create an illustration.
5. Review the content, make any changes you need, and save the flashcard.

## ⚙️ Add-on Settings

You can find all settings under **Tools → Gemini Editor Settings…**.

### 🔑 AI Provider and API Key Setup

- **Google Gemini API Keys:** Nhập một hoặc nhiều API Key, mỗi Key nằm trên một dòng. Tiện ích sẽ tự động luân phiên sử dụng các Key khi cần. Bạn có thể tạo API Key miễn phí tại [Google AI Studio](https://aistudio.google.com/api-keys). Hạn mức miễn phí tính theo dự án Google, nên các key cùng một dự án dùng chung một hạn mức; hãy tạo mỗi key ở một dự án khác nhau để tăng lượt dùng thật sự.
- **Gemini Model:** Chọn mô hình Gemini dùng để tạo nội dung. Mô hình mặc định là `gemini-3.8-flash`. Nếu mô hình này không khả dụng, tiện ích sẽ thử các mô hình dự phòng đã được thiết lập.
- **Timeout:** Thiết lập thời gian tối đa chờ AI phản hồi, tính bằng giây. Mặc định là 300 giây.
- **Groq Cloud:** Bạn có thể chọn Groq làm nhà cung cấp AI thay thế. Để sử dụng, chọn Provider là `groq`, nhập API Key lấy từ [Groq Console](https://console.groq.com/keys) và chọn mô hình phù hợp, ví dụ `llama-3.3-70b-versatile` (xem [danh sách mô hình](https://console.groq.com/docs/models)).

### 🖼️ Image Generation Settings

Tiện ích có hai nguồn tạo hình minh họa. Bạn có thể để hệ thống tự chọn (khuyên dùng) hoặc chọn một nguồn cố định.

| Image source | Cost / requirements | Description |
| --- | --- | --- |
| **Pollinations (Flux)** | **Paid with "Pollen"**, requires a secret key (`sk_…`) | Beautiful, fast images. Each image costs a small amount of Pollen. Get a key at [enter.pollinations.ai/keys](https://enter.pollinations.ai/keys). You can top up, or complete the **Quests** on that site to earn free Pollen. When the Pollen runs out the service answers with error 402 and the add-on moves on to AI Horde. |
| **AI Horde** | Free, no account needed | Uses community GPU resources. Stable, but an image can take 30–90 seconds. |

- **Auto (recommended):** uses Pollinations first if you entered a valid key, otherwise goes straight to AI Horde. If Pollinations fails (for example, no Pollen left), it falls back to AI Horde.
- Keys that are masked (contain `****`) are ignored.
- You can turn automatic image generation on or off in the same settings group.

### 🔊 Text-to-Speech Settings

- **TTS API Key:** Leave this blank to reuse the main Gemini API Key.
- **TTS Model:** Select the model used to generate speech. The default is `gemini-2.5-flash-preview-tts`.
- The voice is chosen automatically from the language of the text.

### 🃏 Keys for Practice Buttons on the Card

The sentence-practice buttons (and 🔊) run inside the card itself, including on your phone, where the add-on does not run. So the add-on writes the keys into a small media file (`_avg_card_keys.js`), which Anki syncs to your phone.

- **You only need to enter your Gemini key once** in the top box. If the "API dùng cho luyện câu" box or the TTS box is empty, the add-on reuses the top key.
- After changing keys: press **Save** in Settings, then **Sync** on the computer, then **Sync** on the phone.
- Fill these boxes only if you want separate keys (for example, to keep some daily quota for practice on your phone).
- Do not share the media file when you share a deck, because it contains your keys.

## 🎯 How to Use

### 🔘 Buttons in the Card Editor

| Button / shortcut | Function |
| --- | --- |
| ✨ **Ctrl + G** | Automatically fills in flashcard fields based on the word in the **Word** field. It can also generate an illustration if the feature is enabled. |
| 🚀 | Opens the optimized bulk vocabulary creation feature. |
| ✅ | Checks a sentence you wrote using the vocabulary item you are studying. |
| 💡 | Suggests edits to make your sentence clearer and more natural. |
| 📖 | Generates vocabulary content based on the passage in the **Reading** field. |
| 🔗 | Finds and generates additional vocabulary related to the reading passage. |
| 🔊 **Ctrl + Alt + Q** | Generates pronunciation audio using Gemini TTS. |
| 🖼️ **Ctrl + Alt + I** | Generates an illustration only, without regenerating the entire flashcard. |
| 🏷️ | Automatically tags vocabulary by subject area and difficulty. |
| 📝 | Creates translation exercises for the selected topic or field. |
| 🎧 | Creates interpreting or listen-and-repeat (shadowing) exercises. |

### 🧰 Tools Menu

| Feature | Description |
| --- | --- |
| **Gemini Editor Settings…** | Opens settings for configuring the AI provider, API Keys, models, and other options. |
| **📊 Token Usage Statistics** | Shows usage statistics and the status of your API Keys. |
| **🩺 Kiểm tra API key Gemini** | Checks which keys are active, have reached their usage limits, or are unavailable, and estimates the remaining capacity. |
| **✨ Thêm hàng loạt từ Gemini…** | Creates multiple flashcards from a vocabulary list. |
| **🚀 Thêm hàng loạt tối ưu…** | Creates flashcards in batches with options such as the number of words per batch, delay between batches, and shared context. |
| **🔄 Tiếp tục tiến trình bị gián đoạn** | Resumes a bulk flashcard creation process that did not finish. |
| **🔗 Tạo từ vựng liên quan từ bài đọc** | Finds and creates related vocabulary based on the current flashcard's reading passage. |
| **📝 Cập nhật template cho tab Áp dụng** | Adds fields for displaying vocabulary extracted from a reading passage to the current card template. |
| **🔄 Thêm nút bài tập dịch vào template** | Adds buttons for accessing translation and interpreting exercises to the card template. |
| **⬆️ Upgrade Note Type** | Adds the fields needed for specialized content, such as translation and interpreting exercises, subject areas, and difficulty levels. |
| **📚 Hướng dẫn sử dụng add-on** | Opens a plain-language user guide with tabs: getting started, adding words, buttons, context hints, Tools menu and troubleshooting. The text lives in `guide_content.py`. |

### 🖱️ Anki Browser Context Menu

Trong **Browser**, chọn một hoặc nhiều flashcard, sau đó nhấn chuột phải để sử dụng:

- **✨ Thêm chi tiết với Gemini:** Adds missing information or improves the content of the selected flashcards.
- **🔗 Tạo từ vựng liên quan:** Extracts and creates additional related vocabulary from each flashcard's reading passage.
- **🚀 Add optimized vocabulary list:** Runs the optimized bulk vocabulary creation process on the selected cards.

## 🧭 Using Context to Guide Results

**Context** lets you provide additional information about a word's topic or usage situation. This helps the AI identify the meaning you want to study and generate more relevant content.

You can enter context in the **Context** field or add a hint directly after the vocabulary item.

Here are some examples:

- **By situation:** `business meeting`, `medical terminology` — asks the AI to explain the word in a business-meeting or medical-terminology context.
- **By topic:** `technology`, `medical`, `education` — guides the content toward technology, medicine, or education.
- **By part of speech:** `run [verb]`, `light [noun]`, `fast [adj]`, `quickly [adv]` — asks the AI to focus on a specific part of speech.
- **Combining context and part of speech:** `business meeting [noun]` — guides the result using both a context and a part of speech.

Common part-of-speech abbreviations:

- `n` or `noun`: noun
- `v` or `verb`: verb
- `adj` or `adjective`: adjective
- `adv` or `adverb`: adverb

## 🗂️ Starter Deck and Card Design

The first time you open Anki after installing the add-on, it creates a ready-to-use note type and deck, both named **Gemini Vocabulary**:

- 37 fields (word, pronunciation, meanings, examples, exercises, reading, translation drills, tags, ...).
- Front template, back template and the full card styling (CSS), taken from `front template.txt`, `back_template.txt` and `styling.txt`.
- It runs only once per collection. If your collection already has a note type with the fields `Word`, `Definition_VI` and `Exercises`, nothing is created, so existing setups are never duplicated.
- Translation-drill buttons are not part of the starter back template; add them with **Tools → 🔄 Thêm nút bài tập dịch vào template** if you want them.

## 📦 Publishing to AnkiWeb (for the developer)

Never zip the add-on folder by hand: it contains `meta.json` (your settings, including API keys), `.bak` backups and `user_files/`. Instead run:

```bash
python build_ankiaddon.py
```

The script copies only an allow-list of files, forces `config.json` to contain no keys, then scans the whole package for your real keys (taken from `meta.json`, `.bak` files and `user_files/`) and for anything that looks like an API key. If it finds one it stops and creates nothing. On success the package is `dist/auto_vocab_gemini.ankiaddon`, which is the only file to upload.

## 🔄 API Key and Usage Limit Management

If you configure multiple API Keys, the add-on can automatically switch to another key when the current one encounters an error or reaches its usage limit. This helps reduce interruptions while generating flashcards.

Here are some common situations:

- **Invalid API Key:** The unavailable key is skipped for the current session.
- **Usage limit reached or model access unavailable:** The add-on tries another API Key.
- **Model overloaded:** The add-on may try a fallback model.
- **Network error:** The add-on automatically retries the connection, with progressively longer intervals between attempts.

The add-on also tracks daily usage for each API Key and model, helping estimate how many requests you have left. Default free-tier limits vary by model and can be configured in the add-on settings. Usage limits reset at midnight Pacific Time.

## 📖 Offline Dictionary

The add-on includes a built-in English–Vietnamese dictionary for looking up common words without connecting to an AI service.

If a word is available in the dictionary and you have not provided additional context, the add-on can create a basic flashcard instantly without using an API Key or AI quota.

If a word is not in the dictionary, or you provide additional context, the add-on uses AI to generate more suitable content.

**Note:** The offline dictionary mainly covers common English words. For less common words or explanations that depend on a specific context, use the AI content-generation feature.
