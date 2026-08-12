import os
import json
import time
import re
from typing import List, Dict, Tuple, Optional, Callable
from .config import Config, LANGUAGE_NAMES, LANGUAGE_HEADERS, SYSTEM_PROMPT_TEMPLATE, MODEL_PRESETS
from .yml_parser import ParadoxYmlParser, YmlEntry
from .ollama_client import OllamaClient
from .terminology import TerminologyManager


class TranslationProgress:
    """Tracks translation progress for resume capability."""
    
    def __init__(self, file_path: str = "progress.json"):
        self.file_path = file_path
        self.data = self._load()
    
    def _load(self) -> Dict:
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        return {"files": {}, "completed_keys": {}}
    
    def save(self):
        os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)
    
    def is_file_completed(self, file_path: str, file_hash: str) -> bool:
        return self.data["files"].get(file_path, {}).get("hash") == file_hash and \
               self.data["files"].get(file_path, {}).get("completed", False)
    
    def mark_file_started(self, file_path: str, file_hash: str, total: int):
        if file_path not in self.data["files"]:
            self.data["files"][file_path] = {}
        self.data["files"][file_path].update({
            "hash": file_hash,
            "total": total,
            "translated": 0,
            "completed": False,
            "started_at": time.time()
        })
        self.save()
    
    def mark_entry_completed(self, file_path: str, key: str, translated_text: str):
        # Don't cache empty or error results
        if not translated_text or translated_text.startswith("[ERROR]"):
            return
        file_key = f"{file_path}:{key}"
        self.data["completed_keys"][file_key] = translated_text
        if file_path in self.data["files"]:
            self.data["files"][file_path]["translated"] = self.data["files"][file_path].get("translated", 0) + 1
        self.save()
    
    def get_cached_translation(self, file_path: str, key: str) -> Optional[str]:
        file_key = f"{file_path}:{key}"
        cached = self.data["completed_keys"].get(file_key)
        # Don't use empty or error cached values
        if cached and not cached.startswith("[ERROR]"):
            return cached
        return None
    
    def mark_file_completed(self, file_path: str):
        if file_path in self.data["files"]:
            self.data["files"][file_path]["completed"] = True
            self.data["files"][file_path]["completed_at"] = time.time()
        self.save()
    
    def reset_file(self, file_path: str):
        if file_path in self.data["files"]:
            del self.data["files"][file_path]
        keys_to_remove = [k for k in self.data["completed_keys"] if k.startswith(f"{file_path}:")]
        for k in keys_to_remove:
            del self.data["completed_keys"][k]
        self.save()
    
    def reset_all(self):
        self.data = {"files": {}, "completed_keys": {}}
        self.save()
    
    def get_file_progress(self, file_path: str) -> Tuple[int, int]:
        """Returns (translated, total) for a file."""
        info = self.data["files"].get(file_path, {})
        return info.get("translated", 0), info.get("total", 0)


class Translator:
    """Main translation engine for HOI4 YML files."""
    
    def __init__(self, config: Config):
        self.config = config
        self.ollama = OllamaClient(config.get("ollama", "base_url"))
        self.terminology = TerminologyManager(config.get("paths", "terminology_file"))
        self.progress = TranslationProgress(config.get("paths", "progress_file"))
        self._stop_requested = False
    
    def stop(self):
        """Request translation to stop."""
        self._stop_requested = True
    
    def _simple_file_hash(self, file_path: str) -> str:
        """Generate a simple hash based on file size and modification time."""
        stat = os.stat(file_path)
        return f"{stat.st_size}_{stat.st_mtime_ns}"
    
    def _get_model_params(self, model_name: str) -> Dict:
        """Get optimized parameters for a model based on its family."""
        params = {
            "temperature": self.config.get("ollama", "temperature"),
            "top_p": self.config.get("ollama", "top_p"),
            "top_k": self.config.get("ollama", "top_k"),
            "repeat_penalty": self.config.get("ollama", "repeat_penalty"),
            "presence_penalty": self.config.get("ollama", "presence_penalty"),
            "frequency_penalty": self.config.get("ollama", "frequency_penalty"),
            "seed": self.config.get("ollama", "seed"),
            "mirostat": self.config.get("ollama", "mirostat"),
            "num_ctx": self.config.get("ollama", "num_ctx"),
            "num_predict": self.config.get("ollama", "num_predict"),
        }
        
        # Auto-tune only applies to core sampling params when enabled
        if self.config.get("ollama", "auto_tune_params"):
            # Detect model family from model name (e.g., "qwen2.5:7b-instruct" -> "qwen2.5")
            model_base = model_name.split(':')[0].lower() if ':' in model_name else model_name.lower()
            
            # Check against known model families
            for family, preset in MODEL_PRESETS.items():
                if model_base.startswith(family) or family in model_base:
                    # Only auto-tune temperature and context for model families, 
                    # respect user settings for other params
                    params["temperature"] = preset["temperature"]
                    params["num_ctx"] = preset["num_ctx"]
                    params["num_predict"] = preset["num_predict"]
                    break
        
        return params
    
    def _get_model_family(self, model_name: str) -> str:
        """Detect the model family from model name."""
        model_base = model_name.split(':')[0].lower() if ':' in model_name else model_name.lower()
        for family in MODEL_PRESETS.keys():
            if model_base.startswith(family) or family in model_base:
                return family
        return "unknown"
    
    def _build_system_prompt(self, source_lang: str, target_lang: str) -> str:
        """Build the system prompt for translation."""
        source_name = LANGUAGE_NAMES.get(source_lang, source_lang)
        target_name = LANGUAGE_NAMES.get(target_lang, target_lang)
        terminology_section = self.terminology.format_for_prompt(source_lang, target_lang)
        
        return SYSTEM_PROMPT_TEMPLATE.format(
            source_lang_name=source_name,
            target_lang_name=target_name,
            terminology_section=terminology_section
        )
    
    def translate_entry(self, text: str, source_lang: str, target_lang: str,
                        context_messages: Optional[List[Dict[str, str]]] = None,
                        stream_callback: Optional[Callable[[str], None]] = None) -> str:
        """Translate a single text entry."""
        system_prompt = self._build_system_prompt(source_lang, target_lang)
        model = self.config.get("ollama", "model")
        
        # Get auto-tuned parameters for this model
        model_params = self._get_model_params(model)
        
        max_retries = self.config.get("translation", "max_retries")
        retry_delay = self.config.get("translation", "retry_delay")
        
        # Protect special tokens
        protected_text, placeholder_map = ParadoxYmlParser.protect_special_tokens(text)
        
        for attempt in range(max_retries):
            if self._stop_requested:
                return text
            
            try:
                result = self.ollama.translate(
                    model=model,
                    system_prompt=system_prompt,
                    text=protected_text,
                    temperature=model_params["temperature"],
                    top_p=model_params["top_p"],
                    top_k=model_params["top_k"],
                    repeat_penalty=model_params["repeat_penalty"],
                    presence_penalty=model_params["presence_penalty"],
                    frequency_penalty=model_params["frequency_penalty"],
                    seed=model_params["seed"],
                    mirostat=model_params["mirostat"],
                    num_ctx=model_params["num_ctx"],
                    num_predict=model_params["num_predict"],
                    context_messages=context_messages,
                    stream_callback=stream_callback
                )
                
                # Clean and restore (filters thinking blocks for reasoning models)
                translated = ParadoxYmlParser.clean_translation(result)
                translated = ParadoxYmlParser.restore_special_tokens(translated, placeholder_map)
                
                # Validate: if result is empty or looks wrong, retry
                if translated and len(translated) > 0:
                    return translated
                
            except Exception as e:
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                    continue
                else:
                    raise
        
        return text  # Return original if all retries fail
    
    def translate_file(self, input_path: str, output_path: Optional[str] = None,
                       source_lang: Optional[str] = None, target_lang: Optional[str] = None,
                       base_input_dir: Optional[str] = None,
                       progress_callback: Optional[Callable[[int, int, str, str], None]] = None,
                       entry_callback: Optional[Callable[[str, str, str], None]] = None) -> str:
        """Translate a single YML file.
        
        Args:
            input_path: Path to input YML file
            output_path: Explicit output path (overrides output_dir calculation)
            source_lang: Source language (auto-detected if None)
            target_lang: Target language (from config if None)
            base_input_dir: Base directory for calculating relative output paths
            progress_callback: Called with (current, total, key, translated_text)
            entry_callback: Called per entry with (key, original, translated)
            
        Returns:
            Path to output file
        """
        self._stop_requested = False
        
        source_lang = source_lang or self.config.get("translation", "source_lang")
        target_lang = target_lang or self.config.get("translation", "target_lang")
        output_dir = self.config.get("paths", "output_dir")
        context_window = self.config.get("translation", "context_window")
        
        # Parse file
        lang_header, entries, raw_lines = ParadoxYmlParser.parse_file(input_path)
        
        # Safety check: if no entries parsed, raise error with diagnostic info
        if len(entries) == 0:
            # Show first few non-empty lines for debugging
            sample_lines = []
            for line in raw_lines[:15]:
                if line.strip():
                    sample_lines.append(repr(line[:120]))
            raise ValueError(
                f"未能从文件解析到任何本地化条目！\n"
                f"文件: {input_path}\n"
                f"检测到语言头: {lang_header}\n"
                f"文件前几行:\n" + "\n".join(sample_lines)
            )
        
        # Auto-detect source language from header
        detected_source = lang_header.replace("l_", "")
        if source_lang == "english" and detected_source != "english":
            source_lang = detected_source
        
        # Get texts to translate
        to_translate = ParadoxYmlParser.extract_texts_to_translate(entries)
        total = len(to_translate)
        
        # Setup output path
        input_filename = os.path.basename(input_path)
        output_filename = ParadoxYmlParser.get_output_filename(input_filename, source_lang, target_lang)
        
        if output_path is None:
            # Calculate relative path
            if base_input_dir:
                rel_path = os.path.relpath(input_path, base_input_dir)
                rel_dir = os.path.dirname(rel_path)
                output_path = os.path.join(output_dir, target_lang, rel_dir, output_filename)
            else:
                output_path = os.path.join(output_dir, target_lang, output_filename)
        
        # Check for existing progress
        file_hash = self._simple_file_hash(input_path)
        cached_count = 0
        
        # Translate entries
        context_messages = []  # Rolling context for better consistency
        translated_count = 0
        
        for idx, (entry_idx, original_text) in enumerate(to_translate):
            if self._stop_requested:
                break
            
            entry = entries[entry_idx]
            
            # Check cache
            cached = self.progress.get_cached_translation(input_path, entry.key)
            if cached is not None:
                entry.value = cached
                translated_count += 1
                if progress_callback:
                    progress_callback(translated_count, total, entry.key, cached)
                if entry_callback:
                    entry_callback(entry.key, original_text, cached)
                continue
            
            # Build context from previous translations
            context_msgs = context_messages[-context_window*2:] if context_window > 0 else []
            
            try:
                translated = self.translate_entry(
                    original_text, source_lang, target_lang,
                    context_messages=context_msgs
                )
                
                # Update entry
                entry.value = translated
                translated_count += 1
                
                # Save to progress
                self.progress.mark_entry_completed(input_path, entry.key, translated)
                
                # Update rolling context
                context_messages.append({"role": "user", "content": original_text})
                context_messages.append({"role": "assistant", "content": translated})
                
                # Callbacks
                if progress_callback:
                    progress_callback(translated_count, total, entry.key, translated)
                if entry_callback:
                    entry_callback(entry.key, original_text, translated)
                
            except Exception as e:
                # Keep original text on error
                if progress_callback:
                    progress_callback(translated_count, total, entry.key, f"[ERROR] {e}")
        
        # Write output
        output_lang_header = LANGUAGE_HEADERS.get(target_lang, f"l_{target_lang}")
        
        # Create translated entries copy
        translated_entries = []
        for entry in entries:
            new_entry = YmlEntry(
                entry.key, entry.value, entry.version, entry.indent, entry.comment
            )
            translated_entries.append(new_entry)
        
        ParadoxYmlParser.write_file(output_path, lang_header, translated_entries, output_lang_header)
        
        if not self._stop_requested:
            self.progress.mark_file_completed(input_path)
        
        return output_path
    
    def translate_directory(self, input_dir: str, output_dir: Optional[str] = None,
                           source_lang: Optional[str] = None, target_lang: Optional[str] = None,
                           file_pattern: str = "*.yml",
                           progress_callback: Optional[Callable[[str, int, int, int, int], None]] = None,
                           file_callback: Optional[Callable[[str, str, bool], None]] = None) -> List[str]:
        """Translate all YML files in a directory (recursively).
        
        Args:
            input_dir: Input directory
            output_dir: Output directory (base for mirrored structure)
            source_lang: Source language
            target_lang: Target language
            file_pattern: File pattern to match (default: *.yml)
            progress_callback: Called with (current_file, file_num, total_files, entry_num, total_entries)
            file_callback: Called per file with (input_path, output_path, success)
            
        Returns:
            List of output file paths
        """
        import glob
        
        source_lang = source_lang or self.config.get("translation", "source_lang")
        target_lang = target_lang or self.config.get("translation", "target_lang")
        output_dir = output_dir or self.config.get("paths", "output_dir")
        
        # Override config output_dir temporarily
        old_output_dir = self.config.get("paths", "output_dir")
        self.config.set("paths", "output_dir", output_dir)
        
        try:
            # Find all YML files
            pattern = os.path.join(input_dir, "**", file_pattern)
            yml_files = glob.glob(pattern, recursive=True)
            
            # Filter: only translate localization files
            # HOI4 localization files follow the pattern: *_l_<language>.yml
            source_files = []
            skipped_files = []
            for f in yml_files:
                basename = os.path.basename(f).lower()
                # Skip target language files
                if f"_l_{target_lang}" in basename:
                    continue
                # Must look like a localization file (contains "_l_" pattern)
                # Or be inside a "localisation" directory
                is_localization_file = "_l_" in basename or \
                                       ("localisation" in f.replace("\\", "/").lower())
                if is_localization_file:
                    source_files.append(f)
                else:
                    skipped_files.append(f)
            
            total_files = len(source_files)
            output_paths = []
            
            for file_num, input_path in enumerate(source_files, 1):
                if self._stop_requested:
                    break
                
                try:
                    def on_entry_progress(current, total_entries, key, text):
                        if progress_callback:
                            progress_callback(input_path, file_num, total_files, current, total_entries)
                    
                    output_path = self.translate_file(
                        input_path,
                        source_lang=source_lang,
                        target_lang=target_lang,
                        base_input_dir=input_dir,
                        progress_callback=on_entry_progress
                    )
                    output_paths.append(output_path)
                    
                    if file_callback:
                        file_callback(input_path, output_path, True)
                        
                except Exception as e:
                    if file_callback:
                        file_callback(input_path, str(e), False)
            
            return output_paths
        finally:
            self.config.set("paths", "output_dir", old_output_dir)
    
    def test_connection(self) -> Tuple[bool, str]:
        """Test connection to Ollama and model availability.
        Automatically switches to an available model if configured model is not found.
        """
        if not self.ollama.check_connection():
            return False, "无法连接到Ollama，请确保Ollama正在运行 (默认地址: http://localhost:11434)"
        
        model = self.config.get("ollama", "model")
        models = self.ollama.list_models()
        
        if not models:
            return False, "Ollama已连接，但未找到任何模型。请使用 ollama pull 命令下载模型。\n推荐: ollama pull deepseek-r1:7b"
        
        if not self.ollama.is_model_available(model):
            # Auto-select best available model
            best_model = self.ollama.find_best_available_model()
            if best_model:
                self.config.set("ollama", "model", best_model)
                self.config.save()
                return True, (f"配置的模型 '{model}' 未找到，已自动切换到 '{best_model}'。\n"
                            f"可用模型: {len(models)} 个 (已选择最优模型)")
            else:
                available = ", ".join(models[:10])
                return False, f"模型 '{model}' 未找到。可用模型: {available}\n请运行: ollama pull deepseek-r1:7b"
        
        return True, f"Ollama连接正常，模型 '{model}' 已就绪。可用模型: {len(models)} 个"
    
    def ensure_ready(self, auto_start: bool = True) -> Tuple[bool, str]:
        """Ensure Ollama is running and model is ready before translation.
        
        Args:
            auto_start: If True, automatically try to start Ollama if not running
            
        Returns:
            (success, message) tuple
        """
        # First check connection
        if self.ollama.check_connection():
            return self.test_connection()
        
        # Try to start Ollama if auto_start is enabled
        if auto_start:
            if self.ollama.start_ollama():
                return self.test_connection()
            else:
                return False, ("无法连接到Ollama，且自动启动失败。\n"
                              "请手动启动Ollama后重试，或访问 https://ollama.com 下载安装。")
        
        return False, "Ollama未运行，请先启动Ollama服务。"
    
    def get_available_models(self) -> List[str]:
        """Get list of available models from Ollama."""
        return self.ollama.list_models()
    
    def set_model(self, model_name: str):
        """Set the model to use for translation."""
        self.config.set("ollama", "model", model_name)
        self.config.save()
    
    def pull_model(self, model_name: str,
                   progress_callback: Optional[Callable[[int, str], None]] = None) -> bool:
        """Download/pull a model.
        
        Args:
            model_name: Model to download
            progress_callback: Callback(percent, status_message)
            
        Returns:
            True if successful
        """
        def on_progress(pct, total, status):
            if progress_callback:
                if pct >= 0:
                    progress_callback(pct, f"{status} ({pct}%)")
                else:
                    progress_callback(-1, status)
        
        # Try CLI method first (nicer progress), fallback to API
        try:
            def cli_progress(line):
                # Parse ollama CLI output lines for progress
                if progress_callback:
                    # Try to extract percentage
                    import re
                    pct_match = re.search(r'(\d+)%', line)
                    if pct_match:
                        pct = int(pct_match.group(1))
                        progress_callback(pct, line)
                    else:
                        progress_callback(-1, line)
            
            success = self.ollama.pull_model_cli(model_name, cli_progress)
            if success:
                if progress_callback:
                    progress_callback(100, "下载完成!")
                return True
        except Exception:
            pass
        
        # Fallback to API method
        return self.ollama.pull_model(model_name, on_progress)
