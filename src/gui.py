import os
import sys
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
from typing import Optional

from .config import Config, LANGUAGE_NAMES, LANGUAGE_HEADERS
from .translator import Translator
from .hardware import HardwareInfo, recommend_models, get_best_model


class HOI4TranslatorGUI:
    """Main GUI for HOI4 AI Translator."""
    
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("钢铁雄心4 AI自动汉化助手 v1.0")
        self.root.geometry("900x700")
        self.root.minsize(800, 600)
        
        # Set working directory to the script's directory
        if getattr(sys, 'frozen', False):
            self.app_dir = os.path.dirname(sys.executable)
        else:
            self.app_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        
        os.chdir(self.app_dir)
        
        self.config = Config(os.path.join(self.app_dir, "config.json"))
        self.translator = Translator(self.config)
        
        self.translation_thread: Optional[threading.Thread] = None
        self.is_translating = False
        
        self._build_ui()
        self._check_ollama_connection()
    
    def _build_ui(self):
        """Build the user interface."""
        # Style
        style = ttk.Style()
        style.theme_use('clam')
        
        # Main container
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)
        
        # Title
        title_label = ttk.Label(
            main_frame,
            text="🎮 钢铁雄心4 AI自动汉化助手",
            font=("Microsoft YaHei UI", 16, "bold")
        )
        title_label.pack(pady=(0, 10))
        
        # Notebook for tabs
        self.notebook = ttk.Notebook(main_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True)
        
        # Tab 1: Translation
        self._build_translation_tab()
        
        # Tab 2: Settings
        self._build_settings_tab()
        
        # Tab 3: Terminology
        self._build_terminology_tab()
        
        # Tab 4: Model Assistant
        self._build_model_tab()
        
        # Tab 5: Log
        self._build_log_tab()
        
        # Status bar
        status_frame = ttk.Frame(main_frame)
        status_frame.pack(fill=tk.X, pady=(10, 0))
        
        self.status_var = tk.StringVar(value="就绪")
        status_label = ttk.Label(status_frame, textvariable=self.status_var, anchor=tk.W)
        status_label.pack(side=tk.LEFT, fill=tk.X, expand=True)
        
        self.progress = ttk.Progressbar(status_frame, mode='determinate', length=300)
        self.progress.pack(side=tk.RIGHT, padx=(10, 0))
    
    def _build_translation_tab(self):
        """Build the translation tab."""
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text=" 翻译 ")
        
        # Source selection
        source_frame = ttk.LabelFrame(tab, text="源文件/目录", padding=10)
        source_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.source_path_var = tk.StringVar()
        source_entry = ttk.Entry(source_frame, textvariable=self.source_path_var)
        source_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(source_frame, text="选择文件", command=self._select_file).pack(side=tk.LEFT, padx=2)
        ttk.Button(source_frame, text="选择目录", command=self._select_directory).pack(side=tk.LEFT, padx=2)
        
        # Output selection
        output_frame = ttk.LabelFrame(tab, text="输出目录", padding=10)
        output_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.output_path_var = tk.StringVar(value=self.config.get("paths", "output_dir"))
        output_entry = ttk.Entry(output_frame, textvariable=self.output_path_var)
        output_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        ttk.Button(output_frame, text="浏览", command=self._select_output_dir).pack(side=tk.LEFT)
        
        # Language selection
        lang_frame = ttk.LabelFrame(tab, text="语言设置", padding=10)
        lang_frame.pack(fill=tk.X, pady=(0, 10))
        
        lang_grid = ttk.Frame(lang_frame)
        lang_grid.pack(fill=tk.X)
        
        ttk.Label(lang_grid, text="源语言:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.source_lang_var = tk.StringVar(value=self.config.get("translation", "source_lang"))
        source_lang_combo = ttk.Combobox(
            lang_grid, textvariable=self.source_lang_var,
            values=list(LANGUAGE_NAMES.keys()), state="readonly", width=20
        )
        source_lang_combo.grid(row=0, column=1, padx=5, pady=5)
        
        ttk.Label(lang_grid, text="目标语言:").grid(row=0, column=2, padx=5, pady=5, sticky=tk.W)
        self.target_lang_var = tk.StringVar(value=self.config.get("translation", "target_lang"))
        target_lang_combo = ttk.Combobox(
            lang_grid, textvariable=self.target_lang_var,
            values=list(LANGUAGE_NAMES.keys()), state="readonly", width=20
        )
        target_lang_combo.grid(row=0, column=3, padx=5, pady=5)
        
        # Model info
        ttk.Label(lang_grid, text="模型:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.model_var = tk.StringVar(value=self.config.get("ollama", "model"))
        self.model_combo = ttk.Combobox(
            lang_grid, textvariable=self.model_var, width=25, state="readonly"
        )
        self.model_combo.grid(row=1, column=1, padx=5, pady=5, sticky=tk.W)
        self.model_combo.bind("<<ComboboxSelected>>", self._on_model_changed)
        
        # Refresh models button
        ttk.Button(lang_grid, text="🔄 刷新", command=self._refresh_models, width=6).grid(
            row=1, column=2, padx=(0, 5), pady=5
        )
        
        self.model_status_var = tk.StringVar(value="检查中...")
        model_status_label = ttk.Label(lang_grid, textvariable=self.model_status_var, foreground="gray")
        model_status_label.grid(row=1, column=3, padx=5, pady=5, sticky=tk.W)
        
        ttk.Button(lang_grid, text="测试连接", command=self._check_ollama_connection).grid(
            row=1, column=4, padx=5, pady=5
        )
        
        # Progress info
        progress_frame = ttk.LabelFrame(tab, text="翻译进度", padding=10)
        progress_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        self.current_file_var = tk.StringVar(value="等待开始...")
        ttk.Label(progress_frame, textvariable=self.current_file_var, wraplength=800).pack(fill=tk.X)
        
        self.current_entry_var = tk.StringVar(value="")
        ttk.Label(progress_frame, textvariable=self.current_entry_var, wraplength=800, foreground="gray").pack(
            fill=tk.X, pady=5
        )
        
        self.log_text = scrolledtext.ScrolledText(progress_frame, height=12, wrap=tk.WORD, font=("Consolas", 9))
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        
        # Control buttons
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X)
        
        self.start_btn = ttk.Button(btn_frame, text="▶ 开始翻译", command=self._start_translation)
        self.start_btn.pack(side=tk.LEFT, padx=5)
        
        self.stop_btn = ttk.Button(btn_frame, text="⏹ 停止", command=self._stop_translation, state=tk.DISABLED)
        self.stop_btn.pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="清空进度缓存", command=self._clear_progress).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="打开输出目录", command=self._open_output_dir).pack(side=tk.RIGHT, padx=5)
    
    def _build_settings_tab(self):
        """Build the settings tab."""
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text=" 设置 ")
        
        # Ollama settings
        ollama_frame = ttk.LabelFrame(tab, text="Ollama 设置", padding=10)
        ollama_frame.pack(fill=tk.X, pady=(0, 10))
        
        grid = ttk.Frame(ollama_frame)
        grid.pack(fill=tk.X)
        
        ttk.Label(grid, text="Ollama 地址:").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.ollama_url_var = tk.StringVar(value=self.config.get("ollama", "base_url"))
        ttk.Entry(grid, textvariable=self.ollama_url_var, width=40).grid(row=0, column=1, padx=5, pady=5, columnspan=3)
        
        # Preset buttons row
        preset_frame = ttk.LabelFrame(ollama_frame, text="⚡ 快速预设", padding=5)
        preset_frame.pack(fill=tk.X, pady=(5, 10))
        
        from .config import PARAM_PRESETS
        self.preset_var = tk.StringVar(value="balanced")
        preset_col = 0
        for preset_id, preset_info in PARAM_PRESETS.items():
            btn = ttk.Radiobutton(
                preset_frame, 
                text=preset_info["name"],
                variable=self.preset_var,
                value=preset_id,
                command=lambda pid=preset_id: self._apply_param_preset(pid)
            )
            btn.grid(row=0, column=preset_col, padx=5, pady=3)
            preset_col += 1
        
        # Parameter controls - organized in two columns
        params_frame = ttk.Frame(ollama_frame)
        params_frame.pack(fill=tk.X)
        
        # Left column - core sampling params
        left_col = ttk.LabelFrame(params_frame, text="采样参数", padding=5)
        left_col.grid(row=0, column=0, padx=(0, 5), sticky=tk.NSEW)
        
        # Row 0: Temperature
        ttk.Label(left_col, text="Temperature (温度):", width=20).grid(row=0, column=0, padx=3, pady=3, sticky=tk.W)
        self.temp_var = tk.DoubleVar(value=self.config.get("ollama", "temperature"))
        temp_scale = ttk.Scale(left_col, from_=0.0, to=2.0, variable=self.temp_var, orient=tk.HORIZONTAL, length=150)
        temp_scale.grid(row=0, column=1, padx=3, pady=3)
        self.temp_label = ttk.Label(left_col, text=f"{self.temp_var.get():.1f}", width=4)
        self.temp_label.grid(row=0, column=2, padx=3, pady=3)
        self.temp_var.trace_add("write", lambda *a: self.temp_label.config(text=f"{self.temp_var.get():.1f}"))
        
        # Row 1: Top-P
        ttk.Label(left_col, text="Top-P (核采样):", width=20).grid(row=1, column=0, padx=3, pady=3, sticky=tk.W)
        self.top_p_var = tk.DoubleVar(value=self.config.get("ollama", "top_p"))
        top_p_scale = ttk.Scale(left_col, from_=0.1, to=1.0, variable=self.top_p_var, orient=tk.HORIZONTAL, length=150)
        top_p_scale.grid(row=1, column=1, padx=3, pady=3)
        self.top_p_label = ttk.Label(left_col, text=f"{self.top_p_var.get():.2f}", width=4)
        self.top_p_label.grid(row=1, column=2, padx=3, pady=3)
        self.top_p_var.trace_add("write", lambda *a: self.top_p_label.config(text=f"{self.top_p_var.get():.2f}"))
        
        # Row 2: Top-K
        ttk.Label(left_col, text="Top-K (Top-K采样):", width=20).grid(row=2, column=0, padx=3, pady=3, sticky=tk.W)
        self.top_k_var = tk.IntVar(value=self.config.get("ollama", "top_k"))
        ttk.Spinbox(left_col, from_=1, to=100, textvariable=self.top_k_var, width=8).grid(
            row=2, column=1, padx=3, pady=3, sticky=tk.W
        )
        
        # Row 3: Repeat Penalty
        ttk.Label(left_col, text="Repeat Penalty (重复惩罚):", width=20).grid(row=3, column=0, padx=3, pady=3, sticky=tk.W)
        self.repeat_penalty_var = tk.DoubleVar(value=self.config.get("ollama", "repeat_penalty"))
        repeat_scale = ttk.Scale(left_col, from_=1.0, to=2.0, variable=self.repeat_penalty_var, orient=tk.HORIZONTAL, length=150)
        repeat_scale.grid(row=3, column=1, padx=3, pady=3)
        self.repeat_label = ttk.Label(left_col, text=f"{self.repeat_penalty_var.get():.2f}", width=4)
        self.repeat_label.grid(row=3, column=2, padx=3, pady=3)
        self.repeat_penalty_var.trace_add("write", lambda *a: self.repeat_label.config(text=f"{self.repeat_penalty_var.get():.2f}"))
        
        # Right column - advanced params
        right_col = ttk.LabelFrame(params_frame, text="高级参数", padding=5)
        right_col.grid(row=0, column=1, padx=(5, 0), sticky=tk.NSEW)
        
        # Row 0: Context length
        ttk.Label(right_col, text="上下文长度:", width=20).grid(row=0, column=0, padx=3, pady=3, sticky=tk.W)
        self.ctx_var = tk.IntVar(value=self.config.get("ollama", "num_ctx"))
        ttk.Spinbox(right_col, from_=2048, to=32768, increment=512, textvariable=self.ctx_var, width=8).grid(
            row=0, column=1, padx=3, pady=3, sticky=tk.W
        )
        
        # Row 1: Max predict
        ttk.Label(right_col, text="最大生成长度:", width=20).grid(row=1, column=0, padx=3, pady=3, sticky=tk.W)
        self.predict_var = tk.IntVar(value=self.config.get("ollama", "num_predict"))
        ttk.Spinbox(right_col, from_=256, to=8192, increment=128, textvariable=self.predict_var, width=8).grid(
            row=1, column=1, padx=3, pady=3, sticky=tk.W
        )
        
        # Row 2: Presence penalty
        ttk.Label(right_col, text="Presence Penalty:", width=20).grid(row=2, column=0, padx=3, pady=3, sticky=tk.W)
        self.presence_penalty_var = tk.DoubleVar(value=self.config.get("ollama", "presence_penalty"))
        presence_scale = ttk.Scale(right_col, from_=-2.0, to=2.0, variable=self.presence_penalty_var, orient=tk.HORIZONTAL, length=150)
        presence_scale.grid(row=2, column=1, padx=3, pady=3)
        self.presence_label = ttk.Label(right_col, text=f"{self.presence_penalty_var.get():.1f}", width=4)
        self.presence_label.grid(row=2, column=2, padx=3, pady=3)
        self.presence_penalty_var.trace_add("write", lambda *a: self.presence_label.config(text=f"{self.presence_penalty_var.get():.1f}"))
        
        # Row 3: Frequency penalty
        ttk.Label(right_col, text="Frequency Penalty:", width=20).grid(row=3, column=0, padx=3, pady=3, sticky=tk.W)
        self.frequency_penalty_var = tk.DoubleVar(value=self.config.get("ollama", "frequency_penalty"))
        freq_scale = ttk.Scale(right_col, from_=-2.0, to=2.0, variable=self.frequency_penalty_var, orient=tk.HORIZONTAL, length=150)
        freq_scale.grid(row=3, column=1, padx=3, pady=3)
        self.freq_label = ttk.Label(right_col, text=f"{self.frequency_penalty_var.get():.1f}", width=4)
        self.freq_label.grid(row=3, column=2, padx=3, pady=3)
        self.frequency_penalty_var.trace_add("write", lambda *a: self.freq_label.config(text=f"{self.frequency_penalty_var.get():.1f}"))
        
        # Row 4: Seed and Mirostat
        seed_miro_frame = ttk.Frame(right_col)
        seed_miro_frame.grid(row=4, column=0, columnspan=3, padx=3, pady=3, sticky=tk.W)
        ttk.Label(seed_miro_frame, text="随机种子(-1=随机):").pack(side=tk.LEFT)
        self.seed_var = tk.IntVar(value=self.config.get("ollama", "seed"))
        ttk.Spinbox(seed_miro_frame, from_=-1, to=999999, textvariable=self.seed_var, width=8).pack(side=tk.LEFT, padx=5)
        ttk.Label(seed_miro_frame, text="Mirostat:").pack(side=tk.LEFT, padx=(10, 0))
        self.mirostat_var = tk.IntVar(value=self.config.get("ollama", "mirostat"))
        ttk.Combobox(seed_miro_frame, textvariable=self.mirostat_var, values=[0, 1, 2], width=3, state="readonly").pack(side=tk.LEFT, padx=5)
        
        # Parameter help text
        help_text = (
            "💡 参数说明:\n"
            "• Temperature: 越低越精确/稳定，越高越有创意/多变 (翻译推荐0.1-0.5)\n"
            "• Top-P/Top-K: 控制采样范围，越小越保守，越大越多样\n"
            "• Repeat Penalty: 防止重复生成，1.0-1.2适合翻译\n"
            "• Presence/Frequency Penalty: 鼓励话题多样性，翻译一般用0\n"
            "• Mirostat: 困惑度感知采样 (0=关闭, 1=Mirostat, 2=Mirostat 2.0)\n"
            "• 随机种子: 固定为某个数字可让翻译结果可复现"
        )
        help_label = ttk.Label(ollama_frame, text=help_text, justify=tk.LEFT, foreground="gray", font=("", 8))
        help_label.pack(fill=tk.X, pady=(5, 5))
        
        # Auto-tune checkbox
        auto_tune_frame = ttk.Frame(ollama_frame)
        auto_tune_frame.pack(fill=tk.X)
        self.auto_tune_var = tk.BooleanVar(value=self.config.get("ollama", "auto_tune_params"))
        ttk.Checkbutton(auto_tune_frame, text="根据模型自动优化基础参数 (推荐勾选，将覆盖Temperature/Top-P/Repeat Penalty为模型推荐值)",
                       variable=self.auto_tune_var).pack(anchor=tk.W)
        
        # Translation settings
        trans_frame = ttk.LabelFrame(tab, text="翻译设置", padding=10)
        trans_frame.pack(fill=tk.X, pady=(0, 10))
        
        grid2 = ttk.Frame(trans_frame)
        grid2.pack(fill=tk.X)
        
        ttk.Label(grid2, text="上下文窗口(前后条目数):").grid(row=0, column=0, padx=5, pady=5, sticky=tk.W)
        self.context_window_var = tk.IntVar(value=self.config.get("translation", "context_window"))
        ttk.Spinbox(grid2, from_=0, to=20, increment=1, textvariable=self.context_window_var, width=10).grid(
            row=0, column=1, padx=5, pady=5, sticky=tk.W
        )
        
        ttk.Label(grid2, text="重试次数:").grid(row=1, column=0, padx=5, pady=5, sticky=tk.W)
        self.retries_var = tk.IntVar(value=self.config.get("translation", "max_retries"))
        ttk.Spinbox(grid2, from_=1, to=10, increment=1, textvariable=self.retries_var, width=10).grid(
            row=1, column=1, padx=5, pady=5, sticky=tk.W
        )
        
        # Save button
        ttk.Button(tab, text="💾 保存设置", command=self._save_settings).pack(pady=10)
        
        # Recommended models
        help_frame = ttk.LabelFrame(tab, text="推荐模型 (使用 ollama pull 下载)", padding=10)
        help_frame.pack(fill=tk.X)
        
        models_text = (
            "=== 中文翻译首选 ===\n"
            "• qwen2.5:7b-instruct        - 中文翻译效果最好 (推荐)\n"
            "• deepseek-r1:7b               - DeepSeek-R1 推理强，翻译准确\n"
            "• deepseek-r1:14b              - DeepSeek-R1 更高质量 (需更多显存)\n"
            "• qwen2.5:14b-instruct       - 更大模型，更稳定\n"
            "• glm4:9b                         - 智谱GLM-4，中文优秀\n"
            "\n=== 其他模型 ===\n"
            "• llama3.1:8b                    - 英文理解优秀\n"
            "• mistral:7b                       - 速度快\n"
            "\n=== 显存不足? 量化版本 ===\n"
            "• qwen2.5:7b-instruct-q4_K_M     (~5GB显存)\n"
            "• deepseek-r1:7b-q4_K_M          (~5GB显存)\n"
            "• deepseek-r1:14b-q4_K_M         (~9GB显存)\n"
            "\n提示: 选择不同模型后系统会自动调优参数 (temperature/ctx等)"
        )
        ttk.Label(help_frame, text=models_text, justify=tk.LEFT, font=("Consolas", 9)).pack(anchor=tk.W)
    
    def _build_terminology_tab(self):
        """Build the terminology management tab."""
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text=" 术语表 ")
        
        ttk.Label(
            tab,
            text="术语表用于统一特定词汇的翻译（如国家名、军事术语等）",
            wraplength=800
        ).pack(pady=(0, 10))
        
        # Terminology list
        list_frame = ttk.Frame(tab)
        list_frame.pack(fill=tk.BOTH, expand=True)
        
        columns = ("source", "target")
        self.term_tree = ttk.Treeview(list_frame, columns=columns, show="headings", height=15)
        self.term_tree.heading("source", text="原文 (English)")
        self.term_tree.heading("target", text="译文 (简体中文)")
        self.term_tree.column("source", width=300)
        self.term_tree.column("target", width=300)
        
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.term_tree.yview)
        self.term_tree.configure(yscrollcommand=scrollbar.set)
        
        self.term_tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Load terminology
        self._load_terminology_list()
        
        # Add/Remove frame
        btn_frame = ttk.Frame(tab)
        btn_frame.pack(fill=tk.X, pady=10)
        
        ttk.Label(btn_frame, text="原文:").pack(side=tk.LEFT)
        self.term_source_var = tk.StringVar()
        ttk.Entry(btn_frame, textvariable=self.term_source_var, width=25).pack(side=tk.LEFT, padx=5)
        
        ttk.Label(btn_frame, text="译文:").pack(side=tk.LEFT)
        self.term_target_var = tk.StringVar()
        ttk.Entry(btn_frame, textvariable=self.term_target_var, width=25).pack(side=tk.LEFT, padx=5)
        
        ttk.Button(btn_frame, text="添加/更新", command=self._add_term).pack(side=tk.LEFT, padx=5)
        ttk.Button(btn_frame, text="删除选中", command=self._remove_term).pack(side=tk.LEFT, padx=5)
    
    def _build_model_tab(self):
        """Build the model assistant tab - hardware detection + model recommendations."""
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text=" 🖥️ 模型助手 ")
        
        # Hardware info section
        hw_frame = ttk.LabelFrame(tab, text="💻 硬件检测", padding=10)
        hw_frame.pack(fill=tk.X, pady=(0, 10))
        
        self.hw_info_text = tk.Text(hw_frame, height=5, wrap=tk.WORD, font=("Consolas", 10))
        self.hw_info_text.pack(fill=tk.X)
        self.hw_info_text.config(state=tk.DISABLED)
        
        btn_row = ttk.Frame(hw_frame)
        btn_row.pack(fill=tk.X, pady=(5, 0))
        ttk.Button(btn_row, text="🔄 重新检测硬件", command=self._detect_hardware).pack(side=tk.LEFT, padx=5)
        
        # Recommended models section
        rec_frame = ttk.LabelFrame(tab, text="🎯 根据你的硬件推荐模型", padding=10)
        rec_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))
        
        # Create a frame with scrollable area for model cards
        self.model_canvas = tk.Canvas(rec_frame, highlightthickness=0)
        scrollbar = ttk.Scrollbar(rec_frame, orient=tk.VERTICAL, command=self.model_canvas.yview)
        self.model_list_frame = ttk.Frame(self.model_canvas)
        
        self.model_list_frame.bind(
            "<Configure>",
            lambda e: self.model_canvas.configure(scrollregion=self.model_canvas.bbox("all"))
        )
        
        self.model_canvas.create_window((0, 0), window=self.model_list_frame, anchor="nw")
        self.model_canvas.configure(yscrollcommand=scrollbar.set)
        
        self.model_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        
        # Download progress section
        dl_frame = ttk.LabelFrame(tab, text="⬇️ 下载进度", padding=10)
        dl_frame.pack(fill=tk.X)
        
        self.download_progress = ttk.Progressbar(dl_frame, mode='determinate', maximum=100)
        self.download_progress.pack(fill=tk.X, pady=(0, 5))
        
        self.download_status_var = tk.StringVar(value="等待下载...")
        ttk.Label(dl_frame, textvariable=self.download_status_var).pack(fill=tk.X)
        
        # Store model recommendation widgets for later updates
        self.model_rec_widgets = []
        
        # Detect hardware on tab creation (will run in background)
        self.hardware_info: Optional[HardwareInfo] = None
        self._detect_hardware()
    
    def _detect_hardware(self):
        """Detect hardware and update recommendations."""
        self.hw_info_text.config(state=tk.NORMAL)
        self.hw_info_text.delete(1.0, tk.END)
        self.hw_info_text.insert(tk.END, "正在检测硬件...\n")
        self.hw_info_text.config(state=tk.DISABLED)
        
        def detect():
            hw = HardwareInfo()
            models = self.translator.get_available_models()
            recommendations = recommend_models(hw.best_vram_gb, models)
            best = get_best_model(hw.best_vram_gb, models)
            
            def update_ui():
                # Update hardware info
                self.hardware_info = hw
                self.hw_info_text.config(state=tk.NORMAL)
                self.hw_info_text.delete(1.0, tk.END)
                summary = hw.get_summary()
                if best:
                    summary += f"\n\n🎯 推荐模型: {best['name']} ({best['model']})"
                    if best.get("installed"):
                        summary += " [已安装]"
                self.hw_info_text.insert(tk.END, summary)
                self.hw_info_text.config(state=tk.DISABLED)
                
                # Clear old recommendations
                for w in self.model_list_frame.winfo_children():
                    w.destroy()
                
                # Add model cards
                for i, rec in enumerate(recommendations):
                    self._add_model_card(rec, i == 0 and rec.get("fits_best"))
            
            self.root.after(0, update_ui)
        
        threading.Thread(target=detect, daemon=True).start()
    
    def _add_model_card(self, rec: dict, is_best: bool = False):
        """Add a model recommendation card to the list."""
        has_warning = rec.get("vram_warning", False)
        bg_color = "#fff3e0" if has_warning else ("#e8f5e9" if is_best else "#f5f5f5")
        
        card = tk.Frame(self.model_list_frame, bg=bg_color, bd=2, relief=tk.GROOVE, padx=10, pady=8)
        card.pack(fill=tk.X, padx=5, pady=5)
        
        # Top row: name + quality badge
        top_row = tk.Frame(card, bg=bg_color)
        top_row.pack(fill=tk.X)
        
        best_tag = " ⭐ 最佳匹配" if is_best else ""
        installed_tag = " ✓ 已安装" if rec.get("installed") else ""
        warning_tag = " ⚠️ 显存可能不足" if has_warning else ""
        
        name_label = tk.Label(
            top_row, text=f"{rec['name']}{best_tag}{installed_tag}{warning_tag}",
            font=("Microsoft YaHei UI", 10, "bold"), bg=bg_color,
            anchor=tk.W,
            fg="#e65100" if has_warning else None
        )
        name_label.pack(side=tk.LEFT)
        
        quality_label = tk.Label(
            top_row, text=rec["quality"],
            font=("Consolas", 11), bg=bg_color, fg="#f9a825"
        )
        quality_label.pack(side=tk.RIGHT)
        
        # Model ID
        model_label = tk.Label(
            card, text=f"模型ID: {rec['model']}",
            font=("Consolas", 9), bg=bg_color, fg="#616161",
            anchor=tk.W
        )
        model_label.pack(fill=tk.X)
        
        # Description and specs
        desc_text = rec['description']
        if has_warning:
            desc_text += f"\n⚠️ 注意: 此模型建议{rec['min_vram']}GB显存，你的显存可能刚好够用，如遇卡顿建议用量化版"
        specs = f"{desc_text}\n最小显存: {rec['min_vram']}GB | 速度: {rec['speed']} | 量化: {rec.get('quant', 'f16')}"
        desc_label = tk.Label(
            card, text=specs,
            font=("Microsoft YaHei UI", 9), bg=bg_color, fg="#424242",
            justify=tk.LEFT, anchor=tk.W, wraplength=600
        )
        desc_label.pack(fill=tk.X, pady=(3, 5))
        
        # Action buttons
        btn_row = tk.Frame(card, bg=bg_color)
        btn_row.pack(fill=tk.X)
        
        if rec.get("installed"):
            def select_model(model=rec['model']):
                self.model_var.set(model)
                self.translator.set_model(model)
                self._log(f"[模型] 已选择: {model}")
                self.model_combo['values'] = self.translator.get_available_models()
                messagebox.showinfo("成功", f"已选择模型: {model}")
            
            tk.Button(
                btn_row, text="✅ 使用此模型", command=select_model,
                bg="#4caf50", fg="white", font=("Microsoft YaHei UI", 9),
                padx=15, relief=tk.RAISED, cursor="hand2"
            ).pack(side=tk.LEFT)
        else:
            def download_model(model=rec['model']):
                self._download_model(model)
            
            tk.Button(
                btn_row, text="⬇️ 下载此模型", command=download_model,
                bg="#2196f3", fg="white", font=("Microsoft YaHei UI", 9),
                padx=15, relief=tk.RAISED, cursor="hand2"
            ).pack(side=tk.LEFT)
    
    def _download_model(self, model_name: str):
        """Download a model with progress display."""
        confirm = messagebox.askyesno(
            "下载模型",
            f"确定要下载模型 {model_name} 吗?\n\n"
            "下载时间取决于你的网络速度，7B模型约4-5GB，14B模型约8-9GB。\n"
            "下载期间可以关闭此窗口，但不要关闭Ollama。"
        )
        if not confirm:
            return
        
        self.download_progress['value'] = 0
        self.download_status_var.set(f"正在下载 {model_name}...")
        self._log(f"[下载] 开始下载模型: {model_name}")
        
        def do_download():
            def on_progress(pct, status):
                def update():
                    if pct >= 0:
                        self.download_progress['value'] = pct
                    self.download_status_var.set(f"{model_name}: {status}")
                self.root.after(0, update)
            
            success = self.translator.pull_model(model_name, on_progress)
            
            def finish():
                if success:
                    self.download_progress['value'] = 100
                    self.download_status_var.set(f"✓ {model_name} 下载完成!")
                    self._log(f"[下载] 模型 {model_name} 下载完成!")
                    # Refresh model list
                    models = self.translator.get_available_models()
                    self.model_combo['values'] = models
                    self.model_var.set(model_name)
                    self.translator.set_model(model_name)
                    # Refresh recommendations
                    self._detect_hardware()
                    messagebox.showinfo("下载完成", f"模型 {model_name} 下载完成!")
                else:
                    self.download_status_var.set(f"✗ 下载失败，请检查网络或手动运行: ollama pull {model_name}")
                    self._log(f"[下载] 模型 {model_name} 下载失败")
            
            self.root.after(0, finish)
        
        threading.Thread(target=do_download, daemon=True).start()
    
    def _build_log_tab(self):
        """Build the log tab."""
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text=" 日志 ")
        
        self.full_log = scrolledtext.ScrolledText(tab, wrap=tk.WORD, font=("Consolas", 9))
        self.full_log.pack(fill=tk.BOTH, expand=True)
        
        ttk.Button(tab, text="清空日志", command=lambda: self.full_log.delete(1.0, tk.END)).pack(pady=5)
    
    def _log(self, message: str):
        """Add a message to the log."""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.full_log.insert(tk.END, message + "\n")
        self.full_log.see(tk.END)
        self.root.update_idletasks()
    
    def _on_model_changed(self, event=None):
        """Called when user selects a model from dropdown."""
        selected = self.model_var.get()
        if selected:
            self.translator.set_model(selected)
            self._log(f"[模型] 已切换为: {selected}")
    
    def _refresh_models(self):
        """Refresh the model dropdown list from Ollama."""
        def refresh():
            try:
                models = self.translator.get_available_models()
                current_model = self.model_var.get()
                
                def update_ui():
                    if models:
                        self.model_combo['values'] = models
                        # If current model is in list, keep it; otherwise select first/best
                        if current_model not in models:
                            # Auto-select best available
                            best = self.translator.ollama.find_best_available_model()
                            if best:
                                self.model_var.set(best)
                                self.translator.set_model(best)
                            else:
                                self.model_var.set(models[0])
                                self.translator.set_model(models[0])
                        self.model_status_var.set(f"✓ {len(models)} 个模型可用")
                        self._log(f"[模型] 已刷新，找到 {len(models)} 个模型: {', '.join(models[:5])}")
                    else:
                        self.model_status_var.set("✗ 无可用模型")
                        self._log("[模型] 未找到任何模型，请运行 ollama pull 下载模型")
                
                self.root.after(0, update_ui)
            except Exception as e:
                self.root.after(0, lambda: self.model_status_var.set("✗ 刷新失败"))
                self._log(f"[错误] 刷新模型列表失败: {e}")
        
        self.model_status_var.set("刷新中...")
        threading.Thread(target=refresh, daemon=True).start()
    
    def _check_ollama_connection(self):
        """Check Ollama connection status, auto-start if needed."""
        def check():
            # Use ensure_ready to auto-start Ollama if possible
            ok, msg = self.translator.ensure_ready(auto_start=True)
            models = []
            if ok:
                models = self.translator.get_available_models()
            
            def update_ui():
                if ok:
                    self.model_status_var.set("✓ 已连接")
                    self._log(f"[连接] {msg}")
                    if models:
                        self.model_combo['values'] = models
                        current = self.model_var.get()
                        if current not in models:
                            best = self.translator.ollama.find_best_available_model()
                            if best:
                                self.model_var.set(best)
                                self.translator.set_model(best)
                        self.model_status_var.set(f"✓ {len(models)} 个模型可用")
                else:
                    self.model_status_var.set("✗ 未就绪")
                    self._log(f"[连接] {msg}")
            
            self.root.after(0, update_ui)
        
        threading.Thread(target=check, daemon=True).start()
    
    def _select_file(self):
        path = filedialog.askopenfilename(
            title="选择YML文件",
            filetypes=[("YML文件", "*.yml"), ("所有文件", "*.*")]
        )
        if path:
            self.source_path_var.set(path)
    
    def _select_directory(self):
        path = filedialog.askdirectory(title="选择本地化目录")
        if path:
            self.source_path_var.set(path)
    
    def _select_output_dir(self):
        path = filedialog.askdirectory(title="选择输出目录")
        if path:
            self.output_path_var.set(path)
    
    def _open_output_dir(self):
        output_dir = self.output_path_var.get()
        if os.path.exists(output_dir):
            os.startfile(output_dir)
        else:
            messagebox.showinfo("提示", "输出目录不存在，翻译时会自动创建")
    
    def _apply_param_preset(self, preset_id: str):
        """Apply a parameter preset to the UI controls."""
        from .config import PARAM_PRESETS
        if preset_id not in PARAM_PRESETS:
            return
        params = PARAM_PRESETS[preset_id]["params"]
        
        self.temp_var.set(params.get("temperature", 0.3))
        self.top_p_var.set(params.get("top_p", 0.9))
        self.top_k_var.set(params.get("top_k", 40))
        self.repeat_penalty_var.set(params.get("repeat_penalty", 1.1))
        self.presence_penalty_var.set(params.get("presence_penalty", 0.0))
        self.frequency_penalty_var.set(params.get("frequency_penalty", 0.0))
        self.seed_var.set(params.get("seed", -1))
        self.mirostat_var.set(params.get("mirostat", 0))
        self.predict_var.set(params.get("num_predict", 1024))
        
        self._log(f"[预设] 已应用参数预设: {PARAM_PRESETS[preset_id]['name']}")
    
    def _save_settings(self):
        """Save settings to config."""
        self.config.set("ollama", "base_url", self.ollama_url_var.get())
        self.config.set("ollama", "model", self.model_var.get())
        self.config.set("ollama", "temperature", round(self.temp_var.get(), 2))
        self.config.set("ollama", "top_p", round(self.top_p_var.get(), 2))
        self.config.set("ollama", "top_k", self.top_k_var.get())
        self.config.set("ollama", "repeat_penalty", round(self.repeat_penalty_var.get(), 2))
        self.config.set("ollama", "presence_penalty", round(self.presence_penalty_var.get(), 2))
        self.config.set("ollama", "frequency_penalty", round(self.frequency_penalty_var.get(), 2))
        self.config.set("ollama", "seed", self.seed_var.get())
        self.config.set("ollama", "mirostat", self.mirostat_var.get())
        self.config.set("ollama", "num_ctx", self.ctx_var.get())
        self.config.set("ollama", "num_predict", self.predict_var.get())
        self.config.set("ollama", "auto_tune_params", self.auto_tune_var.get())
        self.config.set("translation", "context_window", self.context_window_var.get())
        self.config.set("translation", "max_retries", self.retries_var.get())
        self.config.set("translation", "source_lang", self.source_lang_var.get())
        self.config.set("translation", "target_lang", self.target_lang_var.get())
        self.config.set("paths", "output_dir", self.output_path_var.get())
        self.config.save()
        
        # Recreate translator with new config
        self.translator = Translator(self.config)
        messagebox.showinfo("成功", "设置已保存！")
        self._log("[设置] 配置已保存")
    
    def _clear_progress(self):
        """Clear translation progress cache."""
        if messagebox.askyesno("确认", "确定要清空翻译进度缓存吗？这将导致所有文件重新翻译。"):
            self.translator.progress.reset_all()
            self._log("[进度] 缓存已清空")
            messagebox.showinfo("完成", "进度缓存已清空")
    
    def _load_terminology_list(self):
        """Load terminology into the treeview."""
        for item in self.term_tree.get_children():
            self.term_tree.delete(item)
        
        terms = self.translator.terminology.get_terms("english", "simp_chinese")
        for src, tgt in sorted(terms.items()):
            self.term_tree.insert("", tk.END, values=(src, tgt))
    
    def _add_term(self):
        """Add a terminology entry."""
        src = self.term_source_var.get().strip()
        tgt = self.term_target_var.get().strip()
        if src and tgt:
            self.translator.terminology.add_term("english", "simp_chinese", src, tgt)
            self.translator.terminology.save()
            self._load_terminology_list()
            self.term_source_var.set("")
            self.term_target_var.set("")
            self._log(f"[术语] 添加: {src} -> {tgt}")
    
    def _remove_term(self):
        """Remove selected terminology entry."""
        selected = self.term_tree.selection()
        if selected:
            item = self.term_tree.item(selected[0])
            src = item["values"][0]
            self.translator.terminology.remove_term("english", "simp_chinese", src)
            self.translator.terminology.save()
            self._load_terminology_list()
            self._log(f"[术语] 删除: {src}")
    
    def _start_translation(self):
        """Start translation in a background thread."""
        source = self.source_path_var.get().strip()
        output = self.output_path_var.get().strip()
        source_lang = self.source_lang_var.get()
        target_lang = self.target_lang_var.get()
        
        if not source:
            messagebox.showerror("错误", "请先选择源文件或目录")
            return
        
        if not os.path.exists(source):
            messagebox.showerror("错误", "源路径不存在")
            return
        
        # Save current settings first
        self._save_settings()
        
        self.is_translating = True
        self.start_btn.config(state=tk.DISABLED)
        self.stop_btn.config(state=tk.NORMAL)
        self.log_text.delete(1.0, tk.END)
        
        self.translation_thread = threading.Thread(
            target=self._run_translation,
            args=(source, output, source_lang, target_lang),
            daemon=True
        )
        self.translation_thread.start()
    
    def _stop_translation(self):
        """Stop the current translation."""
        if self.is_translating:
            self.translator.stop()
            self.status_var.set("正在停止...")
            self._log("[控制] 正在停止翻译...")
    
    def _run_translation(self, source: str, output: str, source_lang: str, target_lang: str):
        """Run the translation (called in background thread)."""
        try:
            self.root.after(0, lambda: self.status_var.set("检查Ollama连接..."))
            self.root.after(0, lambda: self._log("[准备] 正在检查Ollama和模型状态..."))
            
            # Ensure Ollama is running and model is ready BEFORE starting translation
            ok, msg = self.translator.ensure_ready(auto_start=True)
            if not ok:
                self.root.after(0, lambda: self._log(f"[错误] {msg}"))
                self.root.after(0, lambda: self.status_var.set("就绪 - 模型未就绪"))
                self.root.after(0, lambda: messagebox.showerror("模型未就绪", msg))
                return
            
            self.root.after(0, lambda: self._log(f"[就绪] {msg}"))
            
            # Refresh model list
            models = self.translator.get_available_models()
            def update_models():
                self.model_combo['values'] = models
            self.root.after(0, update_models)
            
            self.root.after(0, lambda: self.status_var.set("正在翻译..."))
            self.root.after(0, lambda: self._log(f"[开始] 源: {source}"))
            self.root.after(0, lambda: self._log(f"[开始] 目标语言: {LANGUAGE_NAMES.get(target_lang, target_lang)}"))
            self.root.after(0, lambda: self._log(f"[开始] 模型: {self.config.get('ollama', 'model')}"))
            
            def on_entry_progress(file_path, file_num, total_files, entry_num, total_entries):
                pct = int((file_num - 1 + entry_num / max(total_entries, 1)) / max(total_files, 1) * 100)
                filename = os.path.basename(file_path)
                
                self.root.after(0, lambda p=pct: self.progress.config(value=p))
                self.root.after(0, lambda f=file_num, tf=total_files, fn=filename: self.current_file_var.set(
                    f"文件 {f}/{tf}: {fn}"
                ))
                self.root.after(0, lambda e=entry_num, te=total_entries, p=pct: self.current_entry_var.set(
                    f"条目 {e}/{te} ({p}%)"
                ))
            
            def on_file_done(input_path, output_path, success):
                filename = os.path.basename(input_path)
                if success:
                    self.root.after(0, lambda: self._log(f"[完成] {filename} -> {output_path}"))
                else:
                    self.root.after(0, lambda: self._log(f"[失败] {filename}: {output_path}"))
            
            if os.path.isfile(source):
                # Single file - calculate output path using user-selected output dir
                from .yml_parser import ParadoxYmlParser
                input_dir = os.path.dirname(source)
                input_filename = os.path.basename(source)
                output_filename = ParadoxYmlParser.get_output_filename(input_filename, source_lang, target_lang)
                if output and os.path.isdir(output):
                    file_output_path = os.path.join(output, target_lang, output_filename)
                else:
                    file_output_path = None  # Use default from config
                
                # Log parse info first
                def log_parse_info():
                    from .yml_parser import ParadoxYmlParser
                    lang_h, entries, raw_lines = ParadoxYmlParser.parse_file(source)
                    to_trans = ParadoxYmlParser.extract_texts_to_translate(entries)
                    self._log(f"[文件] 检测到语言: {lang_h}")
                    self._log(f"[文件] 总行数: {len(raw_lines)}, 解析条目: {len(entries)}, 需翻译: {len(to_trans)}")
                    self._log(f"[文件] 输出路径: {file_output_path or '(默认目录)'}")
                    if len(entries) == 0:
                        self._log(f"[错误] 未能解析到任何条目！文件前5行内容：")
                        for i, line in enumerate(raw_lines[:10], 1):
                            if line.strip():
                                self._log(f"  行{i}: {repr(line[:100])}")
                    elif len(to_trans) == 0:
                        self._log(f"[警告] 没有需要翻译的条目（可能都是代码/变量）")
                self.root.after(0, log_parse_info)
                
                output_path = self.translator.translate_file(
                    source,
                    output_path=file_output_path,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    progress_callback=lambda c, t, k, tx: self.root.after(0, lambda: self._log(f"  [{c}/{t}] {k}: {str(tx)[:60]}"))
                )
                self.root.after(0, lambda: self._log(f"[完成] 翻译完成! 输出文件: {output_path}"))
                # Verify file was written and has content
                def verify_file():
                    if os.path.exists(output_path):
                        size = os.path.getsize(output_path)
                        self._log(f"[验证] 文件已写入，大小: {size} 字节")
                        if size < 50:
                            self._log(f"[警告] 文件可能过小，请检查内容！")
                    else:
                        self._log(f"[错误] 输出文件未创建！")
                self.root.after(0, verify_file)
            else:
                # Directory
                output_paths = self.translator.translate_directory(
                    source,
                    output_dir=output,
                    source_lang=source_lang,
                    target_lang=target_lang,
                    progress_callback=on_entry_progress,
                    file_callback=on_file_done
                )
                self.root.after(0, lambda: self._log(f"[完成] 全部翻译完成! 共处理 {len(output_paths)} 个文件"))
            
            self.root.after(0, lambda: self.status_var.set("翻译完成!"))
            self.root.after(0, lambda: self.current_entry_var.set("✓ 翻译完成!"))
            self.root.after(0, lambda: self.progress.config(value=100))
            
            # Show completion
            self.root.after(0, lambda: messagebox.showinfo("完成", "翻译已完成！"))
            
            # Auto-open output directory
            def open_output():
                out_dir = self.output_path_var.get().strip()
                target = self.target_lang_var.get()
                if out_dir and os.path.isdir(out_dir):
                    target_dir = os.path.join(out_dir, target)
                    os.makedirs(target_dir, exist_ok=True)
                    os.startfile(target_dir)
                else:
                    # Open default output dir
                    default_out = os.path.join(self.app_dir, "output", target)
                    os.makedirs(default_out, exist_ok=True)
                    if os.path.exists(default_out):
                        os.startfile(default_out)
            self.root.after(0, open_output)
            
        except Exception as e:
            self.root.after(0, lambda: self._log(f"[错误] {str(e)}"))
            self.root.after(0, lambda: self.status_var.set("错误"))
            self.root.after(0, lambda: messagebox.showerror("错误", f"翻译出错: {str(e)}"))
        finally:
            self.is_translating = False
            self.root.after(0, lambda: self.start_btn.config(state=tk.NORMAL))
            self.root.after(0, lambda: self.stop_btn.config(state=tk.DISABLED))
    
    def run(self):
        """Run the GUI."""
        self.root.mainloop()


def launch_gui():
    """Launch the GUI application."""
    app = HOI4TranslatorGUI()
    app.run()


if __name__ == "__main__":
    launch_gui()
