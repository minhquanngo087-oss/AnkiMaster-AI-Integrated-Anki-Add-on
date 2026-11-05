# Gemini Flashcard Generator for Anki

A powerful Anki add-on that leverages Google's Gemini AI and multiple image generation engines to automate the creation of high-quality, comprehensive flashcards for language learners.

## Project Overview

*   **Purpose:** Automatically generate rich flashcard content including definitions (EN/VI), IPA/Pinyin, examples, word families, collocations, exercises, and mnemonic stories.
*   **Target Audience:** Vietnamese learners of English, Chinese, Japanese, Korean, and German.
*   **Key Technologies:** 
    *   **Core:** Python, Anki Add-on API (`aqt`).
    *   **AI Models:** Google Gemini (Flash/Pro), Hugging Face Inference (FLUX.1-dev, Stable Diffusion XL).
    *   **Image Generation:** Pollinations.ai, Hugging Face, Google Custom Search, Google Imagen, and local Stable Diffusion (via `diffusers`).
    *   **UI:** Qt6 (PyQt6) via Anki's framework.

## Project Structure

*   `main.py`: The heart of the add-on. Contains over 9,000 lines of code handling UI components, API integrations, data parsing (robust JSON handling), and Anki note manipulation.
*   `__init__.py`: Standard Anki add-on entry point; initializes the `main` module.
*   `gemini_image.py`: A specialized script for local image generation using `torch` and `diffusers`. Designed to run within the project's `venv`.
*   `config.json`: Stores user configurations like API keys, preferred models, and generation settings.
*   `meta.json`: Anki add-on metadata (name, version, etc.).
*   `venv/`: A local Python virtual environment containing heavy dependencies like `torch`, `transformers`, and `scipy`.

## Key Features

1.  **Smart Field Filling:** Automatically fills Anki fields based on a keyword. Supports "Context" and "Part of Speech" hints (e.g., `run [noun]`).
2.  **Image Generation Suite:** Multi-engine support with automatic fallback. Specifically optimized prompts for high-quality visual aids.
3.  **Batch Processing:** 
    *   **Batch Add:** Create hundreds of cards from a word list.
    *   **Batch Fill:** Update existing cards in the Anki Browser.
4.  **Reading Analysis:** Generates short stories using the target word and extracts related vocabulary and grammar structures.
5.  **API Key Rotation:** Robustly handles Google Gemini rate limits (429 errors) by automatically cycling through a list of provided API keys.
6.  **Interactive Practice:** Includes JavaScript-based features in card templates for checking user-generated sentences and providing AI feedback.

## Building and Running

### For Users
1.  Copy the `auto_vocab_gemini` folder into your Anki add-ons directory.
2.  Restart Anki.
3.  Configure your Google Gemini API key(s) in `Tools -> Gemini Editor Settings`.

### For Developers
*   **Environment:** The project uses a local `venv`. Ensure all dependencies in `venv/Lib/site-packages` are present if migrating.
*   **Dependencies:** Primarily `requests` for API calls, and `torch`/`diffusers` for local image generation.
*   **Testing:** Test within Anki by using the "Debug Console" or by reloading the add-on after changes.

## Development Conventions

*   **Async Operations:** Always use `mw.taskman.run_in_background` for API calls to keep the Anki UI responsive.
*   **UI/UX:** Adheres to Anki's Qt-based styling. Uses `tooltip`, `showInfo`, and `showCritical` for user feedback.
*   **JSON Handling:** Uses `safe_json_parse` and multiple regex-based fallback methods to handle varied AI response formats.
*   **Configuration:** Always use `load_config()` and `save_config(config)` which wrap Anki's `mw.addonManager`.
*   **Error Logging:** Critical errors are logged to `editor_error_log.txt` within the add-on directory.

## TODO / Roadmap
- [ ] Optimize the 9k+ line `main.py` by refactoring into smaller modules (e.g., `api_client.py`, `ui_components.py`, `image_engine.py`).
- [ ] Improve local `venv` portability.
- [ ] Enhance mobile compatibility for interactive card features.
