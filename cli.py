#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
命令行版本 - 钢铁雄心4 AI自动汉化助手
适合批量处理和脚本调用
"""

import argparse
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'src'))

from src.config import Config, LANGUAGE_NAMES
from src.translator import Translator


def main():
    parser = argparse.ArgumentParser(
        description="钢铁雄心4 AI自动汉化助手 - CLI版本",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 翻译单个文件
  python cli.py --file "mod/localisation/english/file_l_english.yml" --target simp_chinese
  
  # 翻译整个目录
  python cli.py --dir "mod/localisation/english" --target simp_chinese --output "./output"
  
  # 使用其他模型
  python cli.py --file test.yml --target russian --model qwen2.5:7b-instruct
        """
    )
    
    parser.add_argument("--file", "-f", help="输入YML文件路径")
    parser.add_argument("--dir", "-d", help="输入目录（递归翻译所有YML文件）")
    parser.add_argument("--output", "-o", help="输出目录", default="./output")
    parser.add_argument("--source", "-s", help="源语言", default="english")
    parser.add_argument("--target", "-t", help="目标语言",
                       choices=list(LANGUAGE_NAMES.keys()))
    parser.add_argument("--model", "-m", help="Ollama模型名称", default=None)
    parser.add_argument("--ollama-url", help="Ollama地址", default=None)
    parser.add_argument("--temperature", type=float, help="温度参数", default=None)
    parser.add_argument("--batch-size", type=int, help="批处理大小", default=None)
    parser.add_argument("--list-languages", action="store_true", help="列出支持的语言")
    
    args = parser.parse_args()
    
    if args.list_languages:
        print("支持的语言:")
        for code, name in LANGUAGE_NAMES.items():
            print(f"  {code:15s} - {name}")
        return
    
    if not args.target:
        parser.print_help()
        print("\n错误: 请指定 --target/-t 目标语言")
        sys.exit(1)
    
    if not args.file and not args.dir:
        parser.print_help()
        print("\n错误: 请指定 --file 或 --dir")
        sys.exit(1)
    
    # Load config
    config = Config()
    
    # Override config with CLI args
    if args.model:
        config.set("ollama", "model", args.model)
    if args.ollama_url:
        config.set("ollama", "base_url", args.ollama_url)
    if args.temperature is not None:
        config.set("ollama", "temperature", args.temperature)
    if args.batch_size is not None:
        config.set("translation", "batch_size", args.batch_size)
    
    translator = Translator(config)
    
    # Test connection
    print("[检查] 正在连接Ollama...")
    ok, msg = translator.test_connection()
    print(f"[检查] {msg}")
    if not ok:
        sys.exit(1)
    
    def on_progress(file_path, file_num, total_files, entry_num, total_entries):
        filename = os.path.basename(file_path)
        pct = int((file_num - 1 + entry_num / max(total_entries, 1)) / max(total_files, 1) * 100)
        print(f"\r[进度] 文件 {file_num}/{total_files} | 条目 {entry_num}/{total_entries} | {pct}% | {filename[:40]}", end="", flush=True)
    
    def on_file_done(input_path, output_path, success):
        if success:
            print(f"\n[完成] {os.path.basename(input_path)} -> {output_path}")
        else:
            print(f"\n[失败] {os.path.basename(input_path)}: {output_path}")
    
    try:
        if args.file:
            print(f"[开始] 翻译文件: {args.file}")
            print(f"[开始] 目标语言: {LANGUAGE_NAMES[args.target]}")
            output_path = translator.translate_file(
                args.file,
                source_lang=args.source,
                target_lang=args.target
            )
            print(f"\n[完成] 输出文件: {output_path}")
        else:
            print(f"[开始] 翻译目录: {args.dir}")
            print(f"[开始] 目标语言: {LANGUAGE_NAMES[args.target]}")
            print(f"[开始] 输出目录: {args.output}")
            output_paths = translator.translate_directory(
                args.dir,
                output_dir=args.output,
                source_lang=args.source,
                target_lang=args.target,
                progress_callback=on_progress,
                file_callback=on_file_done
            )
            print(f"\n[完成] 全部完成! 共处理 {len(output_paths)} 个文件")
    except KeyboardInterrupt:
        print("\n[中断] 用户停止")
        translator.stop()
    except Exception as e:
        print(f"\n[错误] {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
