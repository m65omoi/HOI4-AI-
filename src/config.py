import os
import json

# Model presets - optimized parameters for different model families
MODEL_PRESETS = {
    # Qwen2.5 series - excellent Chinese translation
    "qwen2.5": {
        "temperature": 0.3,
        "num_ctx": 8192,
        "num_predict": 1024,
        "recommended_versions": ["7b-instruct", "7b-instruct-q4_K_M", "14b-instruct"],
        "description": "Qwen2.5 - 中文翻译效果最佳（推荐）"
    },
    # DeepSeek series - strong reasoning + translation
    "deepseek-r1": {
        "temperature": 0.2,
        "num_ctx": 8192,
        "num_predict": 2048,
        "recommended_versions": ["7b", "14b", "7b-q4_K_M", "14b-q4_K_M"],
        "description": "DeepSeek-R1 - 推理能力强，翻译准确",
        "note": "DeepSeek-R1会输出思考过程，系统会自动提取最终翻译"
    },
    "deepseek-v2": {
        "temperature": 0.3,
        "num_ctx": 8192,
        "num_predict": 1024,
        "recommended_versions": ["16b-chat", "16b-chat-q4_K_M"],
        "description": "DeepSeek-V2 - MoE架构，速度快"
    },
    "deepseek-llm": {
        "temperature": 0.3,
        "num_ctx": 4096,
        "num_predict": 1024,
        "recommended_versions": ["7b-chat", "7b-chat-q4_K_M"],
        "description": "DeepSeek-LLM - 经典聊天模型"
    },
    # Other popular models
    "llama3.1": {
        "temperature": 0.3,
        "num_ctx": 8192,
        "num_predict": 1024,
        "recommended_versions": ["8b", "8b-instruct-q4_K_M"],
        "description": "Llama 3.1 - 英文理解优秀"
    },
    "mistral": {
        "temperature": 0.3,
        "num_ctx": 8192,
        "num_predict": 1024,
        "recommended_versions": ["7b", "7b-instruct-v0.3"],
        "description": "Mistral - 速度快"
    },
    "glm4": {
        "temperature": 0.3,
        "num_ctx": 8192,
        "num_predict": 1024,
        "recommended_versions": ["9b", "9b-chat"],
        "description": "GLM-4 - 中文优秀"
    }
}

# Recommended model pull commands for quick setup
RECOMMENDED_MODELS = [
    {
        "name": "qwen2.5:7b-instruct",
        "tag": "Qwen2.5 7B 中文首选",
        "vram": "~5GB (q4) / ~8GB (f16)",
        "description": "中文翻译效果最好，推荐大多数用户使用"
    },
    {
        "name": "deepseek-r1:7b",
        "tag": "DeepSeek-R1 7B",
        "vram": "~5GB (q4) / ~8GB (f16)",
        "description": "推理能力强，翻译准确度高"
    },
    {
        "name": "deepseek-r1:14b",
        "tag": "DeepSeek-R1 14B 高质量",
        "vram": "~9GB (q4) / ~16GB (f16)",
        "description": "更高质量，适合显存充足的用户"
    },
    {
        "name": "qwen2.5:14b-instruct",
        "tag": "Qwen2.5 14B 高质量",
        "vram": "~9GB (q4) / ~16GB (f16)",
        "description": "更大模型，翻译质量更稳定"
    },
    {
        "name": "glm4:9b",
        "tag": "GLM-4 9B",
        "vram": "~6GB (q4) / ~10GB (f16)",
        "description": "智谱AI开源模型，中文效果优秀"
    }
]

# Models that include thinking/reasoning output (like DeepSeek-R1 with </think>)
THINKING_MODELS = ["deepseek-r1"]

DEFAULT_CONFIG = {
    "ollama": {
        "base_url": "http://localhost:11434",
        "model": "qwen2.5:7b-instruct",
        "temperature": 0.3,
        "top_p": 0.9,
        "top_k": 40,
        "repeat_penalty": 1.1,
        "presence_penalty": 0.0,
        "frequency_penalty": 0.0,
        "seed": -1,
        "mirostat": 0,
        "num_ctx": 8192,
        "num_predict": 1024,
        "auto_tune_params": True
    },
    "translation": {
        "source_lang": "english",
        "target_lang": "simp_chinese",
        "batch_size": 10,
        "max_retries": 3,
        "retry_delay": 2,
        "context_window": 5
    },
    "paths": {
        "output_dir": "./output",
        "terminology_file": "./terminology.json",
        "progress_file": "./progress.json"
    }
}

# Parameter presets for different translation styles
PARAM_PRESETS = {
    "balanced": {
        "name": "均衡翻译 (推荐)",
        "description": "平衡准确度和流畅度，适合大多数情况",
        "params": {
            "temperature": 0.3,
            "top_p": 0.9,
            "top_k": 40,
            "repeat_penalty": 1.1,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "mirostat": 0,
            "num_predict": 1024,
        }
    },
    "literal": {
        "name": "直译/精确",
        "description": "更保守的参数，严格遵循原文，减少创造性发挥",
        "params": {
            "temperature": 0.1,
            "top_p": 0.7,
            "top_k": 20,
            "repeat_penalty": 1.15,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.1,
            "mirostat": 0,
            "num_predict": 1024,
        }
    },
    "natural": {
        "name": "自然流畅",
        "description": "更自然意译，适合剧情、事件描述等长文本",
        "params": {
            "temperature": 0.5,
            "top_p": 0.95,
            "top_k": 60,
            "repeat_penalty": 1.05,
            "presence_penalty": 0.1,
            "frequency_penalty": 0.1,
            "mirostat": 0,
            "num_predict": 2048,
        }
    },
    "creative": {
        "name": "创意翻译",
        "description": "更高创造性，适合需要意译的梗、俚语、特殊表述",
        "params": {
            "temperature": 0.7,
            "top_p": 0.95,
            "top_k": 80,
            "repeat_penalty": 1.0,
            "presence_penalty": 0.2,
            "frequency_penalty": 0.2,
            "mirostat": 1,
            "num_predict": 2048,
        }
    },
    "deterministic": {
        "name": "完全确定",
        "description": "固定随机种子，结果完全可复现",
        "params": {
            "temperature": 0.0,
            "top_p": 1.0,
            "top_k": 1,
            "repeat_penalty": 1.1,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "seed": 42,
            "mirostat": 0,
            "num_predict": 1024,
        }
    }
}

LANGUAGE_NAMES = {
    "english": "English",
    "simp_chinese": "简体中文",
    "trad_chinese": "繁體中文",
    "russian": "Русский",
    "german": "Deutsch",
    "french": "Français",
    "spanish": "Español",
    "japanese": "日本語",
    "korean": "한국어",
    "polish": "Polski",
    "braz_por": "Português (Brasil)"
}

LANGUAGE_HEADERS = {
    "english": "l_english",
    "simp_chinese": "l_simp_chinese",
    "trad_chinese": "l_trad_chinese",
    "russian": "l_russian",
    "german": "l_german",
    "french": "l_french",
    "spanish": "l_spanish",
    "japanese": "l_japanese",
    "korean": "l_korean",
    "polish": "l_polish",
    "braz_por": "l_braz_por"
}

SYSTEM_PROMPT_TEMPLATE = """You are a professional game localizer specializing in Paradox Interactive games (Hearts of Iron IV, Europa Universalis, Crusader Kings, etc.).

RULES (MUST follow):
1. Translate from {source_lang_name} to {target_lang_name}.
2. PRESERVE ALL formatting codes exactly as-is: §Y, §y, §R, §r, §G, §g, §B, §b, §W, §w, §!, §H, §M, §L, §l, §O, §o, §S, §s, §T, §t, §g, \\n.
3. PRESERVE ALL variables and script functions exactly as-is: [?variable_name], [GetFunction], [Root.GetName], [From.GetFlag], etc.
4. PRESERVE ALL numbers, icons, and special characters.
5. Keep the translation concise and natural for game UI.
6. For military/political terms, use the standard HOI4 community translation terminology.
7. For country names, use established historical or mod-specific names.
8. DO NOT add any explanation or commentary - just output the translated text.
9. DO NOT translate text that is already in the target language.
{terminology_section}

Translate the following text:"""

TERMINOLOGY_SECTION_TEMPLATE = """
TERMINOLOGY (use these exact translations):
{terminology_list}
"""


class Config:
    def __init__(self, config_path="config.json"):
        self.config_path = config_path
        # Resolve to absolute path based on config file location
        self.config_dir = os.path.dirname(os.path.abspath(config_path))
        self.data = DEFAULT_CONFIG.copy()
        # Convert default relative paths to absolute
        self._resolve_paths()
        self.load()
        self._resolve_paths()  # Resolve again after loading saved config

    def _resolve_paths(self):
        """Convert relative paths to absolute paths based on config directory."""
        for key in ["output_dir", "terminology_file", "progress_file"]:
            path = self.data.get("paths", {}).get(key)
            if path and not os.path.isabs(path):
                self.data["paths"][key] = os.path.join(self.config_dir, path)

    def load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                self._deep_update(self.data, saved)
            except Exception:
                pass

    def save(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def _deep_update(self, base, update):
        for k, v in update.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                self._deep_update(base[k], v)
            else:
                base[k] = v

    def get(self, section, key=None):
        if key is None:
            return self.data.get(section, {})
        return self.data.get(section, {}).get(key)

    def set(self, section, key, value):
        if section not in self.data:
            self.data[section] = {}
        self.data[section][key] = value
