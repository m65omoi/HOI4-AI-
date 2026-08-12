import re
import os
from typing import List, Dict, Tuple, Optional


class YmlEntry:
    """Represents a single localization entry in a Paradox YML file."""
    def __init__(self, key: str, value: str, version: int = 0, indent: str = " ", comment: str = ""):
        self.key = key
        self.value = value
        self.version = version
        self.indent = indent
        self.comment = comment

    def to_line(self, lang_header: str) -> str:
        line = f"{self.indent}{self.key}:{self.version} \"{self.value}\""
        if self.comment:
            line += f" {self.comment}"
        return line

    def __repr__(self):
        return f"YmlEntry(key={self.key!r}, value={self.value!r})"


class ParadoxYmlParser:
    """Parser for Paradox localization YML files.
    
    Format:
        l_english:
         KEY:0 "Value text"
         KEY2:1 "Another value with §Ycolors§! and [?variables]"
    
    This is NOT standard YAML - it uses a custom format that must be preserved exactly.
    """

    LINE_PATTERN = re.compile(
        r'^(?P<indent>\s*)(?P<key>[\w\.\-]+):(?P<version>\d+)\s+"(?P<value>(?:[^"\\]|\\.)*)"\s*(?P<comment>#.*)?\s*$'
    )
    
    # Fallback pattern that's more lenient (handles edge cases in some mod files)
    LINE_PATTERN_LENIENT = re.compile(
        r'^(?P<indent>\s*)(?P<key>[^:]+?):(?P<version>\d+)\s+"(?P<value>(?:[^"\\]|\\.)*)"\s*(?P<comment>#.*)?\s*$'
    )
    
    COLOR_CODES = re.compile(r'§[a-zA-Z!]|§!|\\n')
    VARIABLE_PATTERN = re.compile(r'\[[^\]]+\]')

    @staticmethod
    def detect_encoding(file_path: str) -> str:
        """Try to detect file encoding - Paradox files often use UTF-8 with BOM."""
        with open(file_path, 'rb') as f:
            raw = f.read(4)
        if raw.startswith(b'\xff\xfe'):
            return 'utf-16-le'
        if raw.startswith(b'\xfe\xff'):
            return 'utf-16-be'
        if raw.startswith(b'\xef\xbb\xbf'):
            return 'utf-8-sig'
        return 'utf-8'

    @classmethod
    def parse_file(cls, file_path: str) -> Tuple[str, List[YmlEntry], List[str]]:
        """Parse a Paradox YML file.
        
        Returns:
            (language_header, entries, raw_lines)
            - language_header: e.g. "l_english"
            - entries: list of YmlEntry objects
            - raw_lines: all lines (for preserving comments/blanks)
        """
        encoding = cls.detect_encoding(file_path)
        entries = []
        raw_lines = []
        lang_header = None
        unparsed_count = 0

        try:
            with open(file_path, 'r', encoding=encoding) as f:
                content = f.read()
        except UnicodeDecodeError:
            # Fallback encodings
            for enc in ['utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1252', 'gbk', 'latin-1']:
                try:
                    with open(file_path, 'r', encoding=enc) as f:
                        content = f.read()
                    encoding = enc
                    break
                except UnicodeDecodeError:
                    continue
            else:
                raise ValueError(f"Cannot decode file: {file_path}")

        lines = content.splitlines()
        
        for line_num, line in enumerate(lines, 1):
            line_clean = line.rstrip('\r\n')
            raw_lines.append(line_clean)
            
            stripped = line.strip()
            
            # Check for language header - very lenient match
            if lang_header is None:
                # Match patterns like: l_english:, l_simp_chinese:,  L_ENGLISH:, etc.
                header_match = re.match(r'^\s*(l_[a-zA-Z0-9_]+)\s*:\s*$', stripped)
                if header_match:
                    lang_header = header_match.group(1).lower()
                    continue

            # Check for comment-only lines or empty lines
            if not stripped or stripped.startswith('#'):
                continue

            # Try multiple patterns to parse localization entries
            # Pattern 1: Standard HOI4 format with version: key:0 "value"
            match = re.match(
                r'^(?P<indent>\s*)(?P<key>[^:]+?):(?P<version>\d+)\s+"(?P<value>(?:[^"\\]|\\.)*)"\s*(?P<comment>#.*)?\s*$',
                line_clean
            )
            
            if not match:
                # Pattern 2: NO version number (some mods use this): key: "value"
                match = re.match(
                    r'^(?P<indent>\s*)(?P<key>[^:]+?):\s+"(?P<value>(?:[^"\\]|\\.)*)"\s*(?P<comment>#.*)?\s*$',
                    line_clean
                )
                if match:
                    # Version defaults to 0
                    match_groups = match.groupdict()
                    match_groups['version'] = '0'
                    # Reconstruct match (simpler way: just use the groups directly)
                    indent = match_groups['indent']
                    key = match_groups['key'].strip()
                    version = 0
                    value = match_groups['value']
                    comment = match_groups.get('comment') or ""
                    entries.append(YmlEntry(key, value, version, indent, comment))
                    continue
            
            if not match:
                # Pattern 3: Single-quoted with version: key:0 'value'
                match = re.match(
                    r"^(?P<indent>\s*)(?P<key>[^:]+?):(?P<version>\d+)\s+'(?P<value>(?:[^'\\]|\\.)*)'\s*(?P<comment>#.*)?\s*$",
                    line_clean
                )
            
            if not match:
                # Pattern 4: Single-quoted without version: key: 'value'
                match = re.match(
                    r"^(?P<indent>\s*)(?P<key>[^:]+?):\s+'(?P<value>(?:[^'\\]|\\.)*)'\s*(?P<comment>#.*)?\s*$",
                    line_clean
                )
                if match:
                    match_groups = match.groupdict()
                    indent = match_groups['indent']
                    key = match_groups['key'].strip()
                    version = 0
                    value = match_groups['value']
                    comment = match_groups.get('comment') or ""
                    entries.append(YmlEntry(key, value, version, indent, comment))
                    continue
            
            if not match:
                # Pattern 5: Unquoted values (last resort)
                match = re.match(
                    r'^(?P<indent>\s*)(?P<key>[^:]+?):(?P<version>\d+)?\s+(?P<value>[^#]+?)\s*(?P<comment>#.*)?\s*$',
                    line_clean
                )
                if match:
                    match_groups = match.groupdict()
                    indent = match_groups['indent']
                    key = match_groups['key'].strip()
                    version = int(match_groups['version']) if match_groups.get('version') else 0
                    value = match_groups['value']
                    comment = match_groups.get('comment') or ""
                    entries.append(YmlEntry(key, value, version, indent, comment))
                    continue
            
            if match:
                indent = match.group('indent')
                key = match.group('key').strip()
                version = int(match.group('version'))
                value = match.group('value')
                comment = match.group('comment') or ""
                entries.append(YmlEntry(key, value, version, indent, comment))
            else:
                unparsed_count += 1

        # If no language header was found, try to guess from filename or default to english
        if lang_header is None:
            # Try to detect from filename patterns like "*_l_english.yml"
            basename = os.path.basename(file_path)
            m = re.search(r'_l_([a-z_]+)\.yml$', basename, re.IGNORECASE)
            if m:
                lang_header = f"l_{m.group(1).lower()}"
            else:
                lang_header = "l_english"

        return lang_header, entries, raw_lines

    @classmethod
    def extract_texts_to_translate(cls, entries: List[YmlEntry]) -> List[Tuple[int, str]]:
        """Extract translatable text from entries, skipping pure code/variable entries."""
        to_translate = []
        for i, entry in enumerate(entries):
            text = entry.value
            # Skip entries that are just variables, bars, or empty
            if not text:
                continue
            # Skip if it looks like a code-only entry (bars for UI, script references)
            if re.match(r'^[\|§!\\\s]+$', text):
                continue
            if re.match(r'^\[Get[A-Za-z]+\]$', text):
                continue
            if re.match(r'^§[Gg]\|+§[gG]\|+§!$', text):
                continue
            to_translate.append((i, text))
        return to_translate

    @classmethod
    def protect_special_tokens(cls, text: str) -> Tuple[str, Dict[str, str]]:
        """Replace color codes, variables, and newlines with placeholders.
        
        Returns:
            (protected_text, placeholder_map)
        """
        placeholder_map = {}
        counter = [0]

        def make_placeholder(prefix: str) -> str:
            counter[0] += 1
            return f"__{prefix}_{counter[0]}__"

        # Protect script variables [?xxx], [GetXxx], [Root.GetXxx], etc.
        def replace_var(m):
            original = m.group(0)
            ph = make_placeholder("VAR")
            placeholder_map[ph] = original
            return ph

        text = cls.VARIABLE_PATTERN.sub(replace_var, text)

        # Protect color codes
        def replace_color(m):
            original = m.group(0)
            ph = make_placeholder("COL")
            placeholder_map[ph] = original
            return ph

        text = re.sub(r'§[a-zA-Z!]|§!', replace_color, text)

        # Protect newlines (\n in YML strings represent literal newlines in-game)
        def replace_newline(m):
            ph = make_placeholder("NL")
            placeholder_map[ph] = '\\n'
            return ph
        
        text = re.sub(r'\\n', replace_newline, text)

        return text, placeholder_map

    @classmethod
    def restore_special_tokens(cls, text: str, placeholder_map: Dict[str, str]) -> str:
        """Restore protected tokens from placeholders."""
        for ph, original in placeholder_map.items():
            text = text.replace(ph, original)
        return text

    @classmethod
    def clean_translation(cls, translated: str) -> str:
        """Clean up AI translation output - remove quotes, fix escaped characters,
        filter thinking/reasoning blocks from models like DeepSeek-R1."""
        text = translated.strip()
        
        # Remove thinking/reasoning blocks (DeepSeek-R1, o1-like models)
        # Handle <think>...</think> tags (with or without attributes)
        text = re.sub(r'<think[^>]*>.*?</think>', '', text, flags=re.DOTALL | re.IGNORECASE)
        # Handle unclosed <think> tags (remove from <think to end)
        text = re.sub(r'<think[^>]*>.*$', '', text, flags=re.DOTALL | re.IGNORECASE)
        
        # Handle common AI prefixes that the model might add
        for prefix in ['翻译结果：', '翻译:', '翻译：', '译文:', '译文：', 'Translation:', 'Result:',
                      '中文翻译：', '英文原文：']:
            if text.startswith(prefix):
                text = text[len(prefix):].strip()
        
        # Remove surrounding quotes if present
        if len(text) >= 2 and text.startswith('"') and text.endswith('"'):
            text = text[1:-1]
        elif text.startswith('"'):
            text = text[1:]
        elif text.endswith('"'):
            text = text[:-1]
        
        # Fix common AI mistakes with newlines
        text = text.replace(' \\n', '\\n')
        text = text.replace('\\n ', '\\n')
        
        # If multiple lines, try to extract the most likely translation
        lines = text.split('\n')
        if len(lines) > 1:
            # Filter out commentary/thinking lines and collect valid translation lines
            commentary_prefixes = ('Note:', '注意:', '说明:', 'Explanation:', '解释:',
                                  '思考:', '分析:', 'Thinking:', '因为', '由于', '首先',
                                  '好的', '嗯', '我需要', '让我', 'Okay', 'Let me', 'First',
                                  '我来', '翻译', '译文', 'Translation', 'Result', '原文',
                                  '英文', '中文', 'Original', 'Translated')
            
            valid_lines = []
            for line in lines:
                stripped = line.strip()
                if not stripped:
                    continue
                # Skip commentary lines
                skip = False
                for prefix in commentary_prefixes:
                    if stripped.startswith(prefix):
                        # Check if it looks like "翻译结果：xxx" - extract xxx
                        if ':' in stripped or '：' in stripped:
                            parts = re.split(r'[:：]', stripped, 1)
                            if len(parts) == 2 and parts[1].strip():
                                # There might be translation after the prefix
                                stripped = parts[1].strip()
                                skip = False
                                break
                        skip = True
                        break
                if not skip and stripped:
                    valid_lines.append(stripped)
            
            if valid_lines:
                # Join valid lines with newlines (to preserve intentional line breaks)
                text = '\n'.join(valid_lines)
            else:
                # Fallback: take the first non-empty line
                for line in lines:
                    stripped = line.strip()
                    if stripped:
                        text = stripped
                        break
        
        return text.strip()

    @classmethod
    def write_file(cls, file_path: str, lang_header: str, entries: List[YmlEntry], 
                  output_lang_header: Optional[str] = None,
                  encoding: str = 'utf-8-sig'):
        """Write entries to a Paradox YML file.
        
        Args:
            file_path: Output path
            lang_header: Original language header (e.g. "l_english")
            entries: List of YmlEntry objects
            output_lang_header: New language header for translated output
            encoding: Output encoding
        """
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        
        header = output_lang_header or lang_header
        if not header.endswith(':'):
            header += ':'
        
        with open(file_path, 'w', encoding=encoding) as f:
            f.write(header + '\n')
            for entry in entries:
                f.write(entry.to_line(header[:-1]) + '\n')

    @classmethod
    def get_output_filename(cls, input_filename: str, source_lang: str, target_lang: str) -> str:
        """Convert filename to target language naming convention.
        
        e.g.:
        - meo_l_english.yml -> meo_l_simp_chinese.yml (if replacing language suffix)
        - If already target language, keep as-is
        """
        name = input_filename
        source_suffix = f"_l_{source_lang}"
        target_suffix = f"_l_{target_lang}"
        
        if source_suffix in name:
            name = name.replace(source_suffix, target_suffix)
        elif f"_{source_lang}" in name:
            name = name.replace(f"_{source_lang}", f"_{target_lang}")
        else:
            # No source lang in filename - append target suffix before .yml
            base, ext = os.path.splitext(name)
            name = f"{base}_l_{target_lang}{ext}"
        
        return name
