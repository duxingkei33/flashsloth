"""
Forum Registry — 论坛版块注册表 + 智能FID匹配

功能：
1. 存储各Discuz平台的版块信息（fid + 名称 + 关键词）
2. 根据文章标签/内容自动匹配最合适的版块
3. 支持AI匹配和关键词模糊匹配两种模式
"""
import json, re, os
from typing import Optional

# 内置版块关键词映射
# 每个版块预定义关键词，用于模糊匹配
FORUM_KEYWORDS = {
    "amobbs.com": {
        "3020": {"name": "STM32/8", "keywords": ["stm32", "stm8", "cortex", "hal", "cube", "arm mcu"]},
        "1000": {"name": "AVR", "keywords": ["avr", "atmega", "attiny", "arduino"]},
        "1006": {"name": "51单片机", "keywords": ["51单片机", "8051", "stc", "keil"]},
        "1024": {"name": "机器人", "keywords": ["机器人", "robot", "舵机", "机械臂"]},
        "1025": {"name": "飞行器", "keywords": ["飞行器", "无人机", "飞控", "四轴", "pixhawk"]},
        "1027": {"name": "雕刻机", "keywords": ["雕刻机", "cnc", "grbl"]},
        "1028": {"name": "PIC", "keywords": ["pic", "microchip"]},
        "1029": {"name": "FPGA", "keywords": ["fpga", "verilog", "vhdl", "zynq", "spartan"]},
        "1031": {"name": "电脑综合", "keywords": ["电脑", "pc", "笔记本", "台式机", "cpu", "显卡"]},
        "1032": {"name": "ARM", "keywords": ["arm", "imx", "rk", "全志", "s3c"]},
        "1037": {"name": "电路仿真", "keywords": ["仿真", "simulation", "spice", "multisim", "proteus"]},
        "2060": {"name": "电子综合", "keywords": ["电子", "电路", "元器件", "焊接", "pcb", "layout"]},
        "2070": {"name": "其它MCU", "keywords": ["mcu", "单片机", "微控制器", "esp32", "esp8266"]},
        "3011": {"name": "CortexM3", "keywords": ["cortex-m3", "stm32f1", "lm3s"]},
        "3013": {"name": "瑞萨", "keywords": ["瑞萨", "renesas", "ra", "rl78"]},
        "3021": {"name": "PLC工控", "keywords": ["plc", "工控", "modbus", "西门子", "三菱"]},
        "3032": {"name": "智能小车", "keywords": ["智能车", "小车", "循迹", "避障"]},
        "3042": {"name": "电子产品", "keywords": ["产品", "设计", "量产", "消费电子"]},
        "3045": {"name": "通信、网络", "keywords": ["通信", "网络", "wifi", "蓝牙", "lora", "zigbee", "4g"]},
        "3046": {"name": "Linux", "keywords": ["linux", "ubuntu", "debian", "嵌入式linux", "驱动"]},
        "3054": {"name": "仪表仪器", "keywords": ["示波器", "万用表", "频谱仪", "仪器", "测量"]},
        "3064": {"name": "MSP430", "keywords": ["msp430", "ti", "低功耗"]},
        "3081": {"name": "HiFi与乐器", "keywords": ["hifi", "音频", "功放", "音箱", "dac"]},
        "9897": {"name": "LGT", "keywords": ["lgt", "8位mcu"]},
        "9923": {"name": "海尔单片机", "keywords": ["海尔", "hr"]},
        "9936": {"name": "飞思卡尔", "keywords": ["飞思卡尔", "freescale", "nxp", "kinetis"]},
        "9942": {"name": "深圳嘉立创", "keywords": ["嘉立创", "jlc", "打样", "pcb打样"]},
        "9960": {"name": "VR虚拟现实", "keywords": ["vr", "虚拟现实", "ar", "增强现实"]},
        "9961": {"name": "树莓派", "keywords": ["树莓派", "raspberry pi", "raspberry"]},
        "9966": {"name": "在芯间商城", "keywords": ["在芯间", "元器件商城", "采购"]},
        "9976": {"name": "乐高编程", "keywords": ["乐高", "lego", "ev3", "mindstorm"]},
        "9981": {"name": "童趣DIY", "keywords": ["diy", "手工", "制作", "创客"]},
        "9998": {"name": "论坛建设", "keywords": ["论坛", "建议", "反馈", "bug"]},
        "10004": {"name": "手机综合", "keywords": ["手机", "android", "ios", "刷机"]},
        "10017": {"name": "家电维修", "keywords": ["维修", "家电", "电视", "空调", "冰箱"]},
        "10025": {"name": "嘉立创EDA", "keywords": ["eda", "立创eda", "原理图", "pcb设计"]},
        "10028": {"name": "3D打印", "keywords": ["3d打印", "3d printer", "打印"]},
        "10033": {"name": "电机马达", "keywords": ["电机", "马达", "步进", "伺服", "无刷"]},
        "10038": {"name": "汽车", "keywords": ["汽车", "电动车", "obd", "can"]},
        "10039": {"name": "手机操作系统", "keywords": ["操作系统", "手机os", "鸿蒙"]},
        "10042": {"name": "电源技术", "keywords": ["电源", "开关电源", "buck", "boost", "充电", "电池"]},
        "10045": {"name": "家居装修", "keywords": ["装修家居", "装修", "智能家居"]},
        "10052": {"name": "智能家居", "keywords": ["home assistant", "智能家居系统", "智能灯", "智能开关", "homekit"]},
        "10057": {"name": "生态鱼缸", "keywords": ["鱼缸", "生态", "水族"]},
        "10059": {"name": "电源技术", "keywords": ["电源", "电力", "电池"]},
        "10061": {"name": "AI编程", "keywords": ["ai", "人工智能", "机器学习", "深度学习", "gpt"]},
        "10062": {"name": "AI行业信息", "keywords": ["ai行业", "大模型", "llm", "chatgpt"]},
    },
    "mydigit.cn": {
        "40": {"name": "数码值得买/交易", "keywords": ["数码", "交易", "买卖", "二手", "优惠"]},
        "41": {"name": "数码大家谈", "keywords": ["数码", "讨论", "综合"]},
        "56": {"name": "拆机乐园", "keywords": ["拆机", "拆解", "维修", "内部"]},
        "59": {"name": "我爱单片机", "keywords": ["单片机", "mcu", "arduino", "esp"]},
        "60": {"name": "电脑硬件", "keywords": ["电脑", "硬件", "cpu", "内存", "硬盘"]},
        "38": {"name": "电池/充电器", "keywords": ["电池", "充电", "充电器", "锂电"]},
        "47": {"name": "工具/仪表", "keywords": ["工具", "万用表", "示波器", "电烙铁"]},
        "63": {"name": "电源技术", "keywords": ["电源", "开关电源", "充电"]},
    },
}


def discover_forums(platform: str, site_url: str, cookies: list) -> dict:
    """使用 Playwright 探索论坛版块（缓存到文件）
    
    返回: {fid: {"name": str, "can_post": bool}}
    """
    from playwright.sync_api import sync_playwright
    import re
    
    cache_path = os.path.expanduser(f"~/.hermes/flashsloth/forum_cache_{platform.replace('.', '_')}.json")
    
    # 检查缓存
    if os.path.exists(cache_path):
        with open(cache_path) as f:
            cached = json.load(f)
        if cached.get("site_url") == site_url:
            return cached["forums"]
    
    forums = {}
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True, args=['--no-sandbox', '--disable-setuid-sandbox'])
        ctx = browser.new_context()
        if cookies:
            ctx.add_cookies(cookies)
        page = ctx.new_page()
        
        try:
            page.goto(f"{site_url}/forum.php", wait_until="domcontentloaded", timeout=20000)
            page.wait_for_timeout(3000)
            
            links = page.query_selector_all("a[href*='forumdisplay'], a[href*='forum-']")
            seen = set()
            for a in links:
                href = a.get_attribute("href") or ""
                text = a.inner_text().strip()
                fid_m = re.search(r'fid=(\d+)', href) or re.search(r'forum-(\d+)', href)
                if fid_m and text and text not in seen and len(text) < 50:
                    seen.add(text)
                    fid = fid_m.group(1)
                    if fid not in forums:
                        forums[fid] = {"name": text, "can_post": None}
            
            # 抽样测试发帖权限（前30个）
            test_list = list(forums.keys())[:30]
            for fid in test_list:
                try:
                    page.goto(f"{site_url}/forum.php?mod=post&action=newthread&fid={fid}", 
                             wait_until="domcontentloaded", timeout=8000)
                    page.wait_for_timeout(1000)
                    has_form = page.query_selector("input[name='subject']") is not None
                    body = page.inner_text("body")[:100] or ""
                    forums[fid]["can_post"] = has_form and "抱歉" not in body
                except:
                    forums[fid]["can_post"] = False
        except:
            pass
        
        browser.close()
    
    # 缓存到文件
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    with open(cache_path, "w") as f:
        json.dump({"site_url": site_url, "forums": forums}, f, ensure_ascii=False)
    
    return forums


def match_forum(platform: str, tags: list, title: str, body: str = "") -> Optional[str]:
    """根据文章标签+标题+正文，匹配最佳版块FID
    
    策略：
    1. 关键词精确匹配（预定义关键词库）
    2. 标签分词匹配
    3. 标题关键词匹配
    4. 回退到最通用的版块
    
    Returns: fid (str) 或 None
    """
    domain = platform
    if domain not in FORUM_KEYWORDS:
        return None
    
    forums = FORUM_KEYWORDS[domain]
    text = " ".join(tags) + " " + title + " " + body
    text_lower = text.lower()
    
    # 计分：每个标签/关键词命中加分
    scores = {}
    for fid, info in forums.items():
        score = 0
        for kw in info["keywords"]:
            if kw.lower() in text_lower:
                score += 1
        if score > 0:
            scores[fid] = score
    
    if scores:
        # 返回得分最高的
        best = max(scores, key=lambda k: scores[k])
        return best
    
    # 无匹配：根据平台返回默认版块
    defaults = {
        "amobbs.com": "3020",     # STM32/8（通用电子技术）
        "mydigit.cn": "41",       # 数码大家谈
    }
    return defaults.get(domain)


def register_forum_match(platform: str, site_url: str, tags: list, 
                         title: str = "", body: str = "") -> dict:
    """一站式：探索+匹配
    
    先尝试从预定义关键词匹配，失败则探索论坛
    """
    fid = match_forum(platform, tags, title, body)
    if fid:
        return {"fid": fid, "source": "keyword", "name": FORUM_KEYWORDS.get(platform, {}).get(fid, {}).get("name", "")}
    
    # 探索模式——需要cookie，由上层调用
    return {"fid": None, "source": "need_explore"}
