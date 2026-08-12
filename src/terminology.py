import json
import os
from typing import Dict, List, Optional


DEFAULT_TERMINOLOGY = {
    "english->simp_chinese": {
        "Political Power": "政治点数",
        "Stability": "稳定度",
        "War Support": "战争支持度",
        "Manpower": "人力",
        "Factory": "工厂",
        "Civilian Factory": "民用工厂",
        "Military Factory": "军用工厂",
        "Naval Dockyard": "海军船坞",
        "Division": "师",
        "Corps": "军",
        "Army": "集团军",
        "Army Group": "集团军群",
        "Navy": "海军",
        "Air Force": "空军",
        "Infantry": "步兵",
        "Cavalry": "骑兵",
        "Armor": "装甲",
        "Artillery": "炮兵",
        "Anti-Air": "防空",
        "Anti-Tank": "反坦克",
        "Fighter": "战斗机",
        "Bomber": "轰炸机",
        "CAS": "近距离支援机",
        "Naval Bomber": "海军轰炸机",
        "Heavy Tank": "重型坦克",
        "Medium Tank": "中型坦克",
        "Light Tank": "轻型坦克",
        "Destroyer": "驱逐舰",
        "Cruiser": "巡洋舰",
        "Battleship": "战列舰",
        "Carrier": "航空母舰",
        "Submarine": "潜艇",
        "Convoy": "运输船",
        "Technology": "科技",
        "Research": "研究",
        "National Focus": "国策",
        "Focus Tree": "国策树",
        "National Spirit": "国家精神",
        "Idea": "理念",
        "Advisor": "顾问",
        "Event": "事件",
        "Decision": "决议",
        "Diplomacy": "外交",
        "Justify War Goal": "制造战争目标",
        "Guarantee Independence": "保障独立",
        "Non-Aggression Pact": "互不侵犯条约",
        "Guarantee": "保证",
        "Faction": "阵营",
        "Alliance": "同盟",
        "Democratic": "民主",
        "Fascist": "法西斯",
        "Communist": "共产",
        "Neutrality": "中立",
        "Non-Aligned": "不结盟",
        "World Tension": "世界紧张度",
        "Trade": "贸易",
        "Resources": "资源",
        "Oil": "石油",
        "Aluminum": "铝",
        "Rubber": "橡胶",
        "Tungsten": "钨",
        "Steel": "钢",
        "Chromium": "铬",
        "Production": "生产",
        "Construction": "建造",
        "Infrastructure": "基础设施",
        "Fort": "要塞",
        "Coastal Fort": "海岸要塞",
        "Air Base": "空军基地",
        "Naval Base": "海军基地",
        "Radar Station": "雷达站",
        "Nuclear Reactor": "核反应堆",
        "Intelligence Agency": "情报机构",
        "Spy": "间谍",
        "Operation": "行动",
        "Collaboration Government": "合作政府",
        "Puppet": "傀儡",
        "Subject": "附属国",
        "Autonomy": "自治度",
        "Civil War": "内战",
        "Capitulate": "投降",
        "Annex": "吞并",
        "Liberate": "解放",
        "Peace Conference": "和平会议",
        "Victory Points": "胜利点",
        "Supply": "补给",
        "Logistics": "后勤",
        "Attrition": "损耗",
        "Organization": "组织度",
        "Strength": "兵力",
        "Equipment": "装备",
        "Soft Attack": "软攻",
        "Hard Attack": "硬攻",
        "Defense": "防御",
        "Breakthrough": "突破",
        "Armor": "装甲",
        "Piercing": "穿甲",
        "Air Superiority": "制空权",
        "Naval Supremacy": "制海权",
        "Interception": "拦截",
        "Strategic Bombing": "战略轰炸",
        "Doctrine": "学说",
        "Land Doctrine": "陆战学说",
        "Naval Doctrine": "海战学说",
        "Air Doctrine": "空战学说",
    }
}


class TerminologyManager:
    """Manages translation terminology / glossary."""
    
    def __init__(self, file_path: str = "terminology.json"):
        self.file_path = file_path
        self.terminology = self._load()
    
    def _load(self) -> Dict[str, Dict[str, str]]:
        """Load terminology from file, or use defaults."""
        if os.path.exists(self.file_path):
            try:
                with open(self.file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                # Merge with defaults
                merged = DEFAULT_TERMINOLOGY.copy()
                for lang_pair, terms in data.items():
                    if lang_pair in merged:
                        merged[lang_pair].update(terms)
                    else:
                        merged[lang_pair] = terms
                return merged
            except Exception:
                pass
        return DEFAULT_TERMINOLOGY.copy()
    
    def save(self):
        """Save terminology to file."""
        os.makedirs(os.path.dirname(os.path.abspath(self.file_path)), exist_ok=True)
        with open(self.file_path, 'w', encoding='utf-8') as f:
            json.dump(self.terminology, f, indent=2, ensure_ascii=False)
    
    def get_terms(self, source_lang: str, target_lang: str) -> Dict[str, str]:
        """Get terminology for a language pair."""
        key = f"{source_lang}->{target_lang}"
        return self.terminology.get(key, {})
    
    def add_term(self, source_lang: str, target_lang: str, source: str, target: str):
        """Add a terminology entry."""
        key = f"{source_lang}->{target_lang}"
        if key not in self.terminology:
            self.terminology[key] = {}
        self.terminology[key][source] = target
    
    def remove_term(self, source_lang: str, target_lang: str, source: str):
        """Remove a terminology entry."""
        key = f"{source_lang}->{target_lang}"
        if key in self.terminology and source in self.terminology[key]:
            del self.terminology[key][source]
    
    def format_for_prompt(self, source_lang: str, target_lang: str) -> str:
        """Format terminology as a string for the system prompt."""
        from .config import TERMINOLOGY_SECTION_TEMPLATE
        terms = self.get_terms(source_lang, target_lang)
        if not terms:
            return ""
        
        term_lines = [f"- {en} -> {cn}" for en, cn in terms.items()]
        return TERMINOLOGY_SECTION_TEMPLATE.format(terminology_list="\n".join(term_lines))
    
    def apply_term_replacements(self, text: str, source_lang: str, target_lang: str) -> str:
        """Apply terminology replacements (post-translation)."""
        terms = self.get_terms(source_lang, target_lang)
        # This is a simple post-processing step - for better results,
        # the terminology is primarily provided in the prompt
        return text
