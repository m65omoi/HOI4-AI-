# -*- coding: utf-8 -*-
"""
Hardware detection module - Detect GPU VRAM and system memory
to recommend optimal models for the user's computer.
"""
import os
import sys
import subprocess
import re
import ctypes
from typing import Dict, List, Optional, Tuple


class HardwareInfo:
    """Detect and store hardware information."""
    
    def __init__(self):
        self.gpus: List[Dict] = []
        self.total_memory_gb: float = 0
        self.cpu_name: str = ""
        self.has_nvidia: bool = False
        self.has_amd: bool = False
        self.has_apple_silicon: bool = False
        self.best_vram_gb: float = 0
        self._detect()
    
    def _detect(self):
        """Run all detection methods."""
        self._detect_system_memory()
        self._detect_cpu()
        self._detect_gpus()
        self._calculate_best_vram()
    
    def _detect_system_memory(self):
        """Detect total system RAM in GB."""
        try:
            if sys.platform == "win32":
                kernel32 = ctypes.windll.kernel32
                c_ulonglong = ctypes.c_ulonglong
                class MEMORYSTATUSEX(ctypes.Structure):
                    _fields_ = [
                        ("dwLength", ctypes.c_ulong),
                        ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", c_ulonglong),
                        ("ullAvailPhys", c_ulonglong),
                        ("ullTotalPageFile", c_ulonglong),
                        ("ullAvailPageFile", c_ulonglong),
                        ("ullTotalVirtual", c_ulonglong),
                        ("ullAvailVirtual", c_ulonglong),
                        ("ullAvailExtendedVirtual", c_ulonglong),
                    ]
                memory_status = MEMORYSTATUSEX()
                memory_status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
                kernel32.GlobalMemoryStatusEx(ctypes.byref(memory_status))
                self.total_memory_gb = round(memory_status.ullTotalPhys / (1024**3), 1)
            elif sys.platform == "darwin":
                result = subprocess.run(["sysctl", "-n", "hw.memsize"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.total_memory_gb = round(int(result.stdout.strip()) / (1024**3), 1)
            else:  # Linux
                result = subprocess.run(["free", "-g"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    lines = result.stdout.strip().split('\n')
                    for line in lines:
                        if line.startswith("Mem:"):
                            parts = line.split()
                            if len(parts) >= 2:
                                self.total_memory_gb = float(parts[1])
        except Exception:
            self.total_memory_gb = 0
    
    def _detect_cpu(self):
        """Detect CPU name."""
        try:
            if sys.platform == "win32":
                result = subprocess.run(
                    ["wmic", "cpu", "get", "name"],
                    capture_output=True, text=True, timeout=10
                )
                if result.returncode == 0:
                    lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                    if len(lines) >= 2:
                        self.cpu_name = lines[1]
            elif sys.platform == "darwin":
                result = subprocess.run(["sysctl", "-n", "machdep.cpu.brand_string"],
                                      capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    self.cpu_name = result.stdout.strip()
                # Check for Apple Silicon
                result2 = subprocess.run(["sysctl", "-n", "hw.optional.arm64"],
                                       capture_output=True, text=True, timeout=5)
                if result2.returncode == 0 and result2.stdout.strip() == "1":
                    self.has_apple_silicon = True
            else:  # Linux
                result = subprocess.run(["cat", "/proc/cpuinfo"], capture_output=True, text=True, timeout=5)
                if result.returncode == 0:
                    for line in result.stdout.split('\n'):
                        if line.startswith("model name"):
                            self.cpu_name = line.split(':')[1].strip()
                            break
        except Exception:
            self.cpu_name = "Unknown CPU"
    
    def _detect_gpus(self):
        """Detect GPUs using multiple methods."""
        # Method 1: Try nvidia-smi for NVIDIA GPUs
        self._detect_nvidia_smi()
        
        # Method 2: Windows WMI for display adapters
        if sys.platform == "win32":
            self._detect_windows_gpu_wmi()
        
        # Method 3: Apple Silicon unified memory
        if self.has_apple_silicon and self.total_memory_gb > 0:
            # Apple Silicon shares RAM with GPU
            self.gpus.append({
                "name": "Apple Silicon (Unified Memory)",
                "vram_gb": self.total_memory_gb,
                "vendor": "apple",
                "is_unified": True
            })
    
    def _detect_nvidia_smi(self):
        """Detect NVIDIA GPUs using nvidia-smi."""
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                for line in lines:
                    parts = [p.strip() for p in line.split(',')]
                    if len(parts) >= 2:
                        name = parts[0]
                        try:
                            vram_mb = int(parts[1])
                            vram_gb = round(vram_mb / 1024, 1)
                        except ValueError:
                            vram_gb = 0
                        self.gpus.append({
                            "name": name,
                            "vram_gb": vram_gb,
                            "vendor": "nvidia",
                            "is_unified": False
                        })
                        self.has_nvidia = True
        except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
            pass
    
    def _detect_windows_gpu_wmi(self):
        """Detect GPUs on Windows using WMI as fallback."""
        try:
            result = subprocess.run(
                ["wmic", "path", "win32_VideoController", "get", "name,AdapterRAM"],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                lines = [l.strip() for l in result.stdout.strip().split('\n') if l.strip()]
                # Skip header
                for line in lines[1:]:
                    # WMI output format: AdapterRAM  Name
                    parts = line.split(None, 1)
                    if len(parts) >= 1:
                        # Name is the longer part
                        name = parts[-1] if len(parts) > 1 else parts[0]
                        vram_gb = 0
                        
                        # Try to parse AdapterRAM
                        if len(parts) >= 2:
                            try:
                                vram_bytes = int(parts[0])
                                if vram_bytes > 0:
                                    vram_gb = round(vram_bytes / (1024**3), 1)
                            except ValueError:
                                pass
                        
                        # Detect vendor from name
                        name_lower = name.lower()
                        vendor = "unknown"
                        if "nvidia" in name_lower or "geforce" in name_lower or "rtx" in name_lower or "gtx" in name_lower:
                            vendor = "nvidia"
                            self.has_nvidia = True
                        elif "amd" in name_lower or "radeon" in name_lower or "rx" in name_lower:
                            vendor = "amd"
                            self.has_amd = True
                        elif "intel" in name_lower and ("uhd" in name_lower or "iris" in name_lower or "hd graphics" in name_lower):
                            vendor = "intel"
                        
                        # Skip if already detected via nvidia-smi
                        already_detected = any(
                            g["name"].lower() in name.lower() or name.lower() in g["name"].lower()
                            for g in self.gpus if g["vendor"] == "nvidia"
                        )
                        
                        if not already_detected:
                            # If VRAM is 0 (WMI often doesn't report it for integrated), estimate
                            if vram_gb == 0:
                                vram_gb = self._estimate_vram_from_name(name)
                            
                            self.gpus.append({
                                "name": name,
                                "vram_gb": vram_gb,
                                "vendor": vendor,
                                "is_unified": False
                            })
        except Exception:
            pass
    
    def _estimate_vram_from_name(self, gpu_name: str) -> float:
        """Estimate VRAM based on GPU model name (fallback when WMI doesn't report it)."""
        name_lower = gpu_name.lower()
        
        # Common NVIDIA GPUs with their typical VRAM
        nvidia_vram = {
            "rtx 4090": 24, "rtx 4080": 16, "rtx 4070 ti": 12, "rtx 4070": 12,
            "rtx 4060 ti": 8, "rtx 4060": 8, "rtx 3090": 24, "rtx 3080 ti": 12,
            "rtx 3080": 10, "rtx 3070 ti": 8, "rtx 3070": 8, "rtx 3060 ti": 8,
            "rtx 3060": 12, "rtx 3050": 8, "rtx 2080 ti": 11, "rtx 2080": 8,
            "rtx 2070": 8, "rtx 2060": 6, "gtx 1660": 6, "gtx 1650": 4,
            "gtx 1080 ti": 11, "gtx 1080": 8, "gtx 1070": 8, "gtx 1060": 6,
            "gtx 1050 ti": 4, "gtx 1050": 4,
        }
        
        for pattern, vram in nvidia_vram.items():
            if pattern in name_lower:
                return vram
        
        # Common AMD GPUs
        amd_vram = {
            "rx 7900 xtx": 24, "rx 7900 xt": 20, "rx 7800 xt": 16, "rx 7700 xt": 12,
            "rx 7600": 8, "rx 6800 xt": 16, "rx 6800": 16, "rx 6700 xt": 12,
            "rx 6600 xt": 8, "rx 6600": 8, "rx 5700 xt": 8, "rx 5700": 8,
        }
        
        for pattern, vram in amd_vram.items():
            if pattern in name_lower:
                return vram
        
        # Intel integrated - usually shares system RAM, assume 2GB available
        if "intel" in name_lower and ("uhd" in name_lower or "hd" in name_lower or "iris" in name_lower):
            return min(4, self.total_memory_gb / 4) if self.total_memory_gb > 0 else 2
        
        # Unknown GPU - conservative estimate
        return 4
    
    def _calculate_best_vram(self):
        """Determine the best available VRAM for LLM inference."""
        if not self.gpus:
            # No dedicated GPU detected - CPU mode, estimate from RAM
            self.best_vram_gb = max(0, min(self.total_memory_gb - 4, self.total_memory_gb * 0.5))
            return
        
        # Find the GPU with most VRAM
        max_vram = 0
        for gpu in self.gpus:
            if gpu["vram_gb"] > max_vram:
                max_vram = gpu["vram_gb"]
        
        self.best_vram_gb = max_vram
    
    def get_summary(self) -> str:
        """Get a human-readable hardware summary."""
        lines = []
        lines.append(f"CPU: {self.cpu_name or 'Unknown'}")
        lines.append(f"系统内存: {self.total_memory_gb} GB")
        
        if self.gpus:
            for i, gpu in enumerate(self.gpus):
                unified_tag = " (统一内存)" if gpu.get("is_unified") else ""
                lines.append(f"GPU {i+1}: {gpu['name']} - {gpu['vram_gb']} GB 显存{unified_tag}")
        else:
            lines.append("GPU: 未检测到独立显卡 (将使用CPU运行)")
        
        lines.append(f"可用于模型的显存: ~{self.best_vram_gb} GB")
        return "\n".join(lines)


# Model recommendation table based on available VRAM
# Format: (model_name, display_name, vram_required_gb, quant_level, quality, description)
MODEL_RECOMMENDATIONS = [
    # Tier 1: Best quality for high VRAM (16GB+)
    {
        "model": "qwen2.5:14b-instruct",
        "name": "Qwen2.5 14B (高质量)",
        "min_vram": 9,
        "recommended_vram": 16,
        "quant": "f16",
        "quality": "★★★★★",
        "description": "最高质量中文翻译，适合显存充足用户",
        "speed": "中等"
    },
    {
        "model": "deepseek-r1:14b",
        "name": "DeepSeek-R1 14B (高质量推理)",
        "min_vram": 9,
        "recommended_vram": 16,
        "quant": "f16",
        "quality": "★★★★★",
        "description": "推理能力极强，翻译准确，适合显存充足",
        "speed": "较慢"
    },
    # Tier 2: Good balance (8-10GB)
    {
        "model": "qwen2.5:14b-instruct-q4_K_M",
        "name": "Qwen2.5 14B (Q4量化)",
        "min_vram": 8,
        "recommended_vram": 10,
        "quant": "q4_K_M",
        "quality": "★★★★☆",
        "description": "14B模型量化版，质量接近原版",
        "speed": "较快"
    },
    {
        "model": "deepseek-r1:14b-q4_K_M",
        "name": "DeepSeek-R1 14B (Q4量化)",
        "min_vram": 8,
        "recommended_vram": 10,
        "quant": "q4_K_M",
        "quality": "★★★★☆",
        "description": "14B量化版，质量损失很小",
        "speed": "较快"
    },
    # Tier 3: Recommended for most users (5-8GB)
    {
        "model": "qwen2.5:7b-instruct",
        "name": "Qwen2.5 7B (推荐)",
        "min_vram": 5,
        "recommended_vram": 8,
        "quant": "f16",
        "quality": "★★★★☆",
        "description": "中文翻译效果最佳，速度与质量平衡",
        "speed": "快"
    },
    {
        "model": "deepseek-r1:7b",
        "name": "DeepSeek-R1 7B",
        "min_vram": 5,
        "recommended_vram": 8,
        "quant": "f16",
        "quality": "★★★★☆",
        "description": "推理能力强，翻译准确",
        "speed": "快"
    },
    # Tier 4: Low VRAM (4-5GB)
    {
        "model": "qwen2.5:7b-instruct-q4_K_M",
        "name": "Qwen2.5 7B (Q4量化)",
        "min_vram": 4,
        "recommended_vram": 5,
        "quant": "q4_K_M",
        "quality": "★★★☆☆",
        "description": "7B量化版，适合显存较小的显卡",
        "speed": "很快"
    },
    {
        "model": "deepseek-r1:7b-q4_K_M",
        "name": "DeepSeek-R1 7B (Q4量化)",
        "min_vram": 4,
        "recommended_vram": 5,
        "quant": "q4_K_M",
        "quality": "★★★☆☆",
        "description": "7B量化版，适合显存较小的显卡",
        "speed": "很快"
    },
    # Tier 5: Very low VRAM / CPU (3-4GB)
    {
        "model": "qwen2.5:3b-instruct",
        "name": "Qwen2.5 3B",
        "min_vram": 2,
        "recommended_vram": 4,
        "quant": "f16",
        "quality": "★★★☆☆",
        "description": "小模型，速度快，适合CPU或小显存",
        "speed": "非常快"
    },
]


def recommend_models(vram_gb: float, available_models: List[str] = None) -> List[Dict]:
    """Get model recommendations based on available VRAM.
    
    Args:
        vram_gb: Available VRAM in GB
        available_models: List of already installed models (to mark as installed)
    
    Returns:
        List of recommended model dicts sorted by quality (best first)
    """
    if available_models is None:
        available_models = []
    
    available_lower = [m.lower() for m in available_models]
    recommendations = []
    
    for model_info in MODEL_RECOMMENDATIONS:
        can_run = vram_gb >= model_info["min_vram"]
        installed = model_info["model"].lower() in available_lower
        
        # Always include installed models, even if VRAM is slightly low
        include = can_run or installed
        
        if include:
            rec = model_info.copy()
            rec["installed"] = installed
            rec["can_run"] = can_run
            rec["fits_best"] = vram_gb >= model_info["recommended_vram"]
            rec["vram_warning"] = installed and not can_run
            recommendations.append(rec)
    
    # Sort: installed first, then by quality, then by best fit
    def sort_key(r):
        # Installed models come first
        installed_priority = 0 if r["installed"] else 1
        # Then by quality (more stars first)
        quality = r["quality"].count("★")
        # Then by recommended fit
        fit = 0 if r["fits_best"] else 1
        return (installed_priority, -quality, fit)
    
    recommendations.sort(key=sort_key)
    
    return recommendations


def get_best_model(vram_gb: float, available_models: List[str] = None) -> Optional[Dict]:
    """Get the single best model recommendation for the hardware."""
    recommendations = recommend_models(vram_gb, available_models)
    
    # First check if any recommended model is already installed
    for rec in recommendations:
        if rec["installed"] and rec["fits_best"]:
            return rec
    
    for rec in recommendations:
        if rec["installed"]:
            return rec
    
    # Return the best quality that fits
    for rec in recommendations:
        if rec["fits_best"]:
            return rec
    
    # Return first that can run
    if recommendations:
        return recommendations[0]
    
    # Absolute fallback
    return {
        "model": "qwen2.5:3b-instruct",
        "name": "Qwen2.5 3B (CPU模式)",
        "min_vram": 2,
        "quality": "★★☆☆☆",
        "description": "最小可用模型",
        "installed": False
    }


if __name__ == "__main__":
    # Test hardware detection
    hw = HardwareInfo()
    print(hw.get_summary())
    print()
    print("Recommended models:")
    for rec in recommend_models(hw.best_vram_gb):
        status = "✓ 已安装" if rec["installed"] else "○ 未安装"
        best = "  ← 最佳匹配" if rec["fits_best"] else ""
        print(f"  [{status}] {rec['name']} ({rec['model']})")
        print(f"       {rec['description']} | 需要{rec['min_vram']}GB+ | 质量:{rec['quality']} | 速度:{rec['speed']}{best}")
        print()
