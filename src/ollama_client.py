import os
import sys
import json
import time
import requests
from typing import Optional, Dict, List, Callable


class OllamaClient:
    """Client for interacting with local Ollama API."""
    
    def __init__(self, base_url: str = "http://localhost:11434"):
        self.base_url = base_url.rstrip('/')
        self.session = requests.Session()
    
    def check_connection(self) -> bool:
        """Check if Ollama is running and accessible."""
        try:
            resp = self.session.get(f"{self.base_url}/api/tags", timeout=5)
            return resp.status_code == 200
        except requests.RequestException:
            return False
    
    def list_models(self) -> List[str]:
        """List available models."""
        try:
            resp = self.session.get(f"{self.base_url}/api/tags", timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                return [m["name"] for m in data.get("models", [])]
        except requests.RequestException:
            pass
        return []
    
    def is_model_available(self, model_name: str) -> bool:
        """Check if a specific model is available.
        
        Matching logic:
        - Exact match: "qwen2.5:7b-instruct" == "qwen2.5:7b-instruct"
        - Flexible match: "qwen2.5:7b" matches "qwen2.5:7b-instruct" (same family:tag)
        - Family match: "deepseek-r1" matches any "deepseek-r1:*"
        """
        models = self.list_models()
        if not models:
            return False
        
        model_lower = model_name.lower().strip()
        
        for m in models:
            m_lower = m.lower().strip()
            if m_lower == model_lower:
                return True
        
        # Try flexible matching
        if ':' in model_name:
            model_base, model_tag = model_lower.split(':', 1)
            for m in models:
                m_lower = m.lower().strip()
                if ':' in m_lower:
                    m_base, m_tag = m_lower.split(':', 1)
                    # Same base family
                    if m_base == model_base:
                        # If tag matches (e.g., both 7b) or one is a variant
                        if model_tag.split('-')[0] in m_tag or m_tag.split('-')[0] in model_tag:
                            return True
                        # If requested tag is a prefix of available tag (e.g., "7b" matches "7b-instruct")
                        if m_tag.startswith(model_tag) or model_tag.startswith(m_tag.split('-')[0]):
                            return True
        else:
            # No tag specified - match any model with this base name
            for m in models:
                if m.lower().startswith(model_lower + ':'):
                    return True
        
        return model_lower in [m.lower() for m in models]
    
    def find_best_available_model(self, preferred_models: list = None) -> Optional[str]:
        """Find the best available model from a list of preferred models.
        
        Args:
            preferred_models: List of model names in order of preference.
                            If None, uses common translation models.
        
        Returns:
            Best matching model name, or None if no suitable model found.
        """
        if preferred_models is None:
            preferred_models = [
                "qwen2.5:7b-instruct",
                "qwen2.5:7b",
                "deepseek-r1:14b",
                "deepseek-r1:7b",
                "deepseek-r1:7b-q4_K_M",
                "deepseek-r1:14b-q4_K_M",
                "qwen2.5:14b-instruct",
                "glm4:9b",
                "llama3.1:8b",
                "mistral:7b",
            ]
        
        models = self.list_models()
        if not models:
            return None
        
        models_lower = {m.lower(): m for m in models}
        
        # First try exact matches in preference order
        for preferred in preferred_models:
            if preferred.lower() in models_lower:
                return models_lower[preferred.lower()]
        
        # Then try flexible matching
        for preferred in preferred_models:
            pref_lower = preferred.lower()
            pref_base = pref_lower.split(':')[0] if ':' in pref_lower else pref_lower
            
            for m_lower, m_orig in models_lower.items():
                m_base = m_lower.split(':')[0] if ':' in m_lower else m_lower
                if m_base == pref_base:
                    # Same family - return this one
                    return m_orig
        
        # If any model exists, return the first one that looks like an instruct/chat model
        for m in models:
            m_lower = m.lower()
            if any(k in m_lower for k in ['instruct', 'chat', 'it']):
                return m
        
        # Last resort - return first available model
        if models:
            return models[0]
        
        return None
    
    def pull_model(self, model_name: str, 
                   progress_callback: Optional[Callable[[int, int, str], None]] = None,
                   timeout: int = 1800) -> bool:
        """Pull/download a model from Ollama registry.
        
        Args:
            model_name: Model name (e.g., "qwen2.5:7b-instruct")
            progress_callback: Optional callback(completion_percent, total, status)
            timeout: Total timeout in seconds (default 30 minutes for large models)
            
        Returns:
            True if download succeeded, False otherwise
        """
        url = f"{self.base_url}/api/pull"
        
        payload = {
            "name": model_name,
            "stream": True
        }
        
        try:
            with self.session.post(url, json=payload, stream=True, timeout=timeout) as resp:
                resp.raise_for_status()
                
                completed_layers = set()
                total_layers = 0
                current_status = "开始下载..."
                
                for line in resp.iter_lines():
                    if line:
                        import json as json_mod
                        data = json_mod.loads(line.decode('utf-8'))
                        
                        status = data.get("status", "")
                        current_status = status
                        
                        if "digest" in data:
                            digest = data["digest"]
                            completed = data.get("completed", 0)
                            total = data.get("total", 0)
                            
                            if total > 0:
                                # Track layers
                                if digest not in completed_layers and completed >= total:
                                    completed_layers.add(digest)
                        
                        # Try to calculate overall progress
                        total = data.get("total", 0)
                        completed = data.get("completed", 0)
                        
                        if progress_callback:
                            if total > 0:
                                # Per-file progress as percentage 0-100
                                pct = int((completed / total) * 100)
                                progress_callback(pct, total, current_status)
                            else:
                                # Status-only update
                                progress_callback(-1, 0, current_status)
                
                if progress_callback:
                    progress_callback(100, 0, "下载完成!")
                return True
                
        except Exception as e:
            if progress_callback:
                progress_callback(-1, 0, f"下载错误: {str(e)}")
            return False
    
    def find_ollama_executable(self) -> Optional[str]:
        """Find ollama CLI executable path."""
        import shutil
        path = shutil.which("ollama")
        if path:
            return path
        
        # Check default paths
        possible_paths = [
            os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
            os.path.join(os.environ.get("PROGRAMFILES", ""), "Ollama", "ollama.exe"),
            os.path.expanduser("~\\AppData\\Local\\Programs\\Ollama\\ollama.exe"),
            "/usr/local/bin/ollama",
            "/usr/bin/ollama",
        ]
        
        for p in possible_paths:
            if os.path.isfile(p):
                return p
        
        return None
    
    def start_ollama(self, wait_timeout: int = 30) -> bool:
        """Start Ollama server if not running.
        
        Args:
            wait_timeout: Seconds to wait for Ollama to start
            
        Returns:
            True if Ollama is running (was already running or successfully started)
        """
        # First check if already running
        if self.check_connection():
            return True
        
        ollama_path = self.find_ollama_executable()
        if not ollama_path:
            return False
        
        try:
            import subprocess
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = 0x08000000  # CREATE_NO_WINDOW
            
            # Start ollama serve
            popen_kwargs = {
                "stdout": subprocess.DEVNULL,
                "stderr": subprocess.DEVNULL,
            }
            if sys.platform == "win32":
                popen_kwargs["creationflags"] = creation_flags
            
            subprocess.Popen(
                [ollama_path, "serve"],
                **popen_kwargs
            )
            
            # Wait for it to start
            start_time = time.time()
            while time.time() - start_time < wait_timeout:
                if self.check_connection():
                    return True
                time.sleep(1)
            
            return self.check_connection()
            
        except Exception:
            return False
    
    def ensure_model_available(self, model_name: str, auto_pull: bool = False,
                               progress_callback: Optional[Callable[[int, int, str], None]] = None) -> bool:
        """Ensure a model is available, optionally pulling it if missing.
        
        Args:
            model_name: Model to check
            auto_pull: If True, automatically pull the model if missing
            progress_callback: Callback for pull progress
            
        Returns:
            True if model is available
        """
        if self.is_model_available(model_name):
            return True
        
        if auto_pull:
            return self.pull_model(model_name, progress_callback)
        
        return False
    
    def pull_model_cli(self, model_name: str,
                       progress_callback: Optional[Callable[[str], None]] = None,
                       timeout: int = 1800) -> bool:
        """Pull model using ollama CLI as fallback (better progress output).
        
        Args:
            model_name: Model to pull
            progress_callback: Optional callback with status line
            timeout: Timeout in seconds
        """
        ollama_path = self.find_ollama_executable()
        if not ollama_path:
            return False
        
        try:
            import subprocess
            creation_flags = 0
            if sys.platform == "win32":
                creation_flags = 0x08000000  # CREATE_NO_WINDOW
            
            process = subprocess.Popen(
                [ollama_path, "pull", model_name],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=creation_flags
            )
            
            start_time = time.time()
            while process.poll() is None:
                if time.time() - start_time > timeout:
                    process.kill()
                    return False
                
                line = process.stdout.readline()
                if line and progress_callback:
                    progress_callback(line.strip())
                time.sleep(0.1)
            
            return process.returncode == 0
            
        except Exception:
            return False
    
    def chat(self, 
             model: str, 
             messages: List[Dict[str, str]], 
             temperature: float = 0.3,
             num_ctx: int = 4096,
             num_predict: int = 1024,
             top_p: float = 0.9,
             top_k: int = 40,
             repeat_penalty: float = 1.1,
             presence_penalty: float = 0.0,
             frequency_penalty: float = 0.0,
             seed: int = -1,
             mirostat: int = 0,
             stream_callback: Optional[Callable[[str], None]] = None,
             timeout: int = 120) -> Optional[str]:
        """Send a chat request to Ollama.
        
        Args:
            model: Model name (e.g., "qwen2.5:7b-instruct")
            messages: List of {"role": "...", "content": "..."} messages
            temperature: Sampling temperature (0.0-2.0). Lower = more deterministic, higher = more creative
            num_ctx: Context window size (tokens)
            num_predict: Maximum tokens to generate
            top_p: Top-p sampling (nucleus sampling), 0.0-1.0
            top_k: Top-k sampling, 0-100
            repeat_penalty: Penalize repeated tokens (1.0 = no penalty, 1.1-1.5 recommended)
            presence_penalty: Presence penalty (-2.0 to 2.0)
            frequency_penalty: Frequency penalty (-2.0 to 2.0)
            seed: Random seed (-1 = random)
            mirostat: Mirostat sampling mode (0=disabled, 1=enabled, 2=enabled with tweaks)
            stream_callback: Optional callback for streaming output
            timeout: Request timeout in seconds
            
        Returns:
            Generated text, or None on error
        """
        url = f"{self.base_url}/api/chat"
        
        options = {
            "temperature": temperature,
            "num_ctx": num_ctx,
            "num_predict": num_predict,
            "top_p": top_p,
            "top_k": top_k,
            "repeat_penalty": repeat_penalty,
        }
        
        # Only add optional parameters if they differ from defaults
        if presence_penalty != 0.0:
            options["presence_penalty"] = presence_penalty
        if frequency_penalty != 0.0:
            options["frequency_penalty"] = frequency_penalty
        if seed >= 0:
            options["seed"] = seed
        if mirostat > 0:
            options["mirostat"] = mirostat
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": stream_callback is not None,
            "options": options
        }
        
        try:
            if stream_callback:
                return self._chat_stream(url, payload, stream_callback, timeout)
            else:
                return self._chat_sync(url, payload, timeout)
        except requests.RequestException as e:
            raise ConnectionError(f"Ollama API error: {e}")
    
    def _chat_sync(self, url: str, payload: Dict, timeout: int) -> Optional[str]:
        """Non-streaming chat request."""
        resp = self.session.post(url, json=payload, timeout=timeout)
        if resp.status_code == 200:
            data = resp.json()
            return data.get("message", {}).get("content", "")
        return None
    
    def _chat_stream(self, url: str, payload: Dict, callback: Callable[[str], None], timeout: int) -> Optional[str]:
        """Streaming chat request."""
        full_response = []
        
        resp = self.session.post(url, json=payload, stream=True, timeout=timeout)
        if resp.status_code != 200:
            return None
        
        for line in resp.iter_lines():
            if line:
                try:
                    data = json.loads(line.decode('utf-8'))
                    if "message" in data and "content" in data["message"]:
                        chunk = data["message"]["content"]
                        full_response.append(chunk)
                        callback(chunk)
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue
        
        return "".join(full_response)
    
    def translate(self,
                  model: str,
                  system_prompt: str,
                  text: str,
                  temperature: float = 0.3,
                  num_ctx: int = 4096,
                  num_predict: int = 1024,
                  top_p: float = 0.9,
                  top_k: int = 40,
                  repeat_penalty: float = 1.1,
                  presence_penalty: float = 0.0,
                  frequency_penalty: float = 0.0,
                  seed: int = -1,
                  mirostat: int = 0,
                  context_messages: Optional[List[Dict[str, str]]] = None,
                  stream_callback: Optional[Callable[[str], None]] = None) -> str:
        """Translate a single text.
        
        Args:
            model: Model name
            system_prompt: System prompt with translation instructions
            text: Text to translate
            temperature: Sampling temperature
            num_ctx: Context window
            num_predict: Max tokens
            top_p: Nucleus sampling
            top_k: Top-k sampling
            repeat_penalty: Repetition penalty
            presence_penalty: Presence penalty
            frequency_penalty: Frequency penalty
            seed: Random seed (-1 = random)
            mirostat: Mirostat mode
            context_messages: Previous translations for context
            stream_callback: Streaming callback
            
        Returns:
            Translated text
        """
        messages = [{"role": "system", "content": system_prompt}]
        
        if context_messages:
            messages.extend(context_messages)
        
        messages.append({"role": "user", "content": text})
        
        result = self.chat(
            model=model,
            messages=messages,
            temperature=temperature,
            num_ctx=num_ctx,
            num_predict=num_predict,
            top_p=top_p,
            top_k=top_k,
            repeat_penalty=repeat_penalty,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            seed=seed,
            mirostat=mirostat,
            stream_callback=stream_callback
        )
        
        return result or ""
