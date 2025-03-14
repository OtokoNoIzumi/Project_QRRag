"""
工具函数模块
"""
import os
import re
import base64
import json
from typing import Dict, Optional, List, Any
from urllib.parse import parse_qs, urlparse


def load_config(config_path: str) -> Dict:
    """
    加载配置文件

    Args:
        config_path: 配置文件路径

    Returns:
        配置字典
    """
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"加载配置文件出错: {str(e)}")
        return {}


def save_config(config_path: str, config: Dict) -> bool:
    """
    保存配置文件

    Args:
        config_path: 配置文件路径
        config: 配置字典

    Returns:
        是否保存成功
    """
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        return True
    except IOError as e:
        print(f"保存配置文件出错: {str(e)}")
        return False


def extract_token_from_url(url: str) -> Optional[str]:
    """
    从URL中提取令牌

    Args:
        url: URL字符串

    Returns:
        令牌ID，如果没有则返回None
    """
    try:
        print(f"DEBUG - 解析URL: {url}")

        # 处理空URL
        if not url or url.strip() == '':
            print("DEBUG - URL为空")
            return None

        # 如果URL是简单字符串且看起来像一个token，直接返回
        if re.match(r'^[a-zA-Z0-9_-]+$', url) and len(url) <= 20:
            print(f"DEBUG - URL本身可能是token: {url}")
            return url

        parsed_url = urlparse(url)
        query_params = parse_qs(parsed_url.query)

        # 从query参数中提取token
        if 'token' in query_params:
            token = query_params['token'][0]
            print(f"DEBUG - 找到token参数: {token}")
            return token

        # 寻找任何可能看起来像token的参数
        for param, values in query_params.items():
            if len(values) > 0 and re.match(r'^[a-zA-Z0-9_-]+$', values[0]):
                print(f"DEBUG - 找到可能的token参数 {param}: {values[0]}")
                return values[0]

        # 如果没有token参数，则检查路径
        path_parts = parsed_url.path.strip('/').split('/')
        for part in path_parts:
            if re.match(r'^[a-zA-Z0-9_-]+$', part) and len(part) >= 4:
                print(f"DEBUG - 从路径找到可能的token: {part}")
                return part

        # 最后尝试检查整个URL中的任何看起来像token的部分
        for match in re.finditer(r'([a-zA-Z0-9_-]{6,20})', url):
            token = match.group(1)
            print(f"DEBUG - 从URL中提取可能的token: {token}")
            return token

        print("DEBUG - 未找到token")
        return None
    except Exception as e:
        print(f"DEBUG - URL解析错误: {str(e)}")
        return None


def format_time_remaining(timestamp: float) -> str:
    """
    格式化剩余时间

    Args:
        timestamp: 目标时间戳

    Returns:
        格式化的剩余时间字符串
    """
    import time

    seconds_remaining = max(0, timestamp - time.time())

    if seconds_remaining <= 0:
        return "已过期"

    days = int(seconds_remaining // 86400)
    hours = int((seconds_remaining % 86400) // 3600)
    minutes = int((seconds_remaining % 3600) // 60)

    if days > 0:
        return f"{days}天{hours}小时"
    elif hours > 0:
        return f"{hours}小时{minutes}分钟"
    else:
        return f"{minutes}分钟"


def create_sample_tokens_file(file_path: str, num_tokens: int = 10) -> None:
    """
    创建样例令牌文件

    Args:
        file_path: 文件路径
        num_tokens: 令牌数量
    """
    import time
    import random
    import string

    tokens = {}
    themes = ["ice", "fire"]

    for i in range(num_tokens):
        token_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))

        now = time.time()
        usage_days = random.randint(1, 30)
        access_days = usage_days + random.randint(0, 30)

        tokens[token_id] = {
            'theme': random.choice(themes),
            'usage_count': 0,
            'max_usage_count': random.randint(1, 5),
            'created_at': now,
            'usage_valid_until': now + usage_days * 86400,
            'access_valid_until': now + access_days * 86400,
            'used_image_hashes': [],
            'used_styles': [],
            'generation_records': []
        }

    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, 'w', encoding='utf-8') as f:
        json.dump(tokens, f, ensure_ascii=False, indent=2)


def encode_image_to_base64(image_path: str) -> Optional[str]:
    """
    将图像编码为Base64字符串

    Args:
        image_path: 图像路径

    Returns:
        Base64编码的图像
    """
    try:
        with open(image_path, "rb") as image_file:
            return base64.b64encode(image_file.read()).decode('utf-8')
    except Exception as e:
        print(f"编码图像出错: {str(e)}")
        return None


def decode_base64_to_image(base64_string: str, output_path: str) -> bool:
    """
    将Base64字符串解码为图像

    Args:
        base64_string: Base64编码的图像
        output_path: 输出路径

    Returns:
        是否解码成功
    """
    try:
        image_data = base64.b64decode(base64_string)
        with open(output_path, "wb") as f:
            f.write(image_data)
        return True
    except Exception as e:
        print(f"解码图像出错: {str(e)}")
        return False


def get_css_for_theme(theme: str) -> str:
    """
    获取主题的CSS样式

    Args:
        theme: 主题名称

    Returns:
        CSS样式字符串
    """
    # 基础样式
    base_css = """
    body {
        margin: 0;
        padding: 0;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
    }
    .gradio-container {
        margin: 0 auto;
    }
    .main-container {
        padding: 20px;
        border-radius: 10px;
        margin: 10px;
    }
    h1, h2, h3 {
        font-weight: 600;
    }
    .gradio-button {
        padding: 10px 20px !important;
        font-weight: 600 !important;
        border-radius: 8px !important;
        cursor: pointer !important;
        transition: all 0.3s ease !important;
        border: none !important;
        margin: 10px 0 !important;
    }
    .gallery-item {
        border-radius: 8px;
        overflow: hidden;
        box-shadow: 0 4px 10px rgba(0,0,0,0.1);
        margin: 10px;
    }
    .gradio-gallery {
        margin-top: 20px;
    }
    """

    # 主题特定样式
    if theme == "ice":
        theme_css = """
        body {
            background: linear-gradient(135deg, #e8f4fc 0%, #d1e6f9 100%);
            color: #2c3e50;
        }
        .main-container {
            background-color: rgba(255, 255, 255, 0.8);
            box-shadow: 0 5px 20px rgba(84, 165, 255, 0.2);
        }
        h1, h2, h3 {
            color: #3498db;
        }
        .gradio-button {
            background-color: #3498db !important;
            color: white !important;
        }
        .gradio-button:hover {
            background-color: #2980b9 !important;
            box-shadow: 0 5px 15px rgba(52, 152, 219, 0.3) !important;
        }
        .gradio-button[disabled], .gradio-button.svelte-cmf5ev[disabled] {
            background-color: #bdc3c7 !important;
            cursor: not-allowed !important;
        }
        .gallery-item {
            border: 2px solid #3498db;
        }
        .gradio-dropdown {
            border: 2px solid #3498db !important;
        }
        """
    elif theme == "fire":
        theme_css = """
        body {
            background: linear-gradient(135deg, #fff4e8 0%, #ffedd1 100%);
            color: #7f4330;
        }
        .main-container {
            background-color: rgba(255, 255, 255, 0.8);
            box-shadow: 0 5px 20px rgba(255, 165, 84, 0.2);
        }
        h1, h2, h3 {
            color: #e74c3c;
        }
        .gradio-button {
            background-color: #e74c3c !important;
            color: white !important;
        }
        .gradio-button:hover {
            background-color: #c0392b !important;
            box-shadow: 0 5px 15px rgba(231, 76, 60, 0.3) !important;
        }
        .gradio-button[disabled], .gradio-button.svelte-cmf5ev[disabled] {
            background-color: #bdc3c7 !important;
            cursor: not-allowed !important;
        }
        .gallery-item {
            border: 2px solid #e74c3c;
        }
        .gradio-dropdown {
            border: 2px solid #e74c3c !important;
        }
        """
    else:
        theme_css = """
        body {
            background: linear-gradient(135deg, #f5f7fa 0%, #e4e8eb 100%);
            color: #34495e;
        }
        .main-container {
            background-color: rgba(255, 255, 255, 0.8);
            box-shadow: 0 5px 20px rgba(0, 0, 0, 0.1);
        }
        h1, h2, h3 {
            color: #2ecc71;
        }
        .gradio-button {
            background-color: #2ecc71 !important;
            color: white !important;
        }
        .gradio-button:hover {
            background-color: #27ae60 !important;
            box-shadow: 0 5px 15px rgba(46, 204, 113, 0.3) !important;
        }
        .gradio-button[disabled], .gradio-button.svelte-cmf5ev[disabled] {
            background-color: #bdc3c7 !important;
            cursor: not-allowed !important;
        }
        .gallery-item {
            border: 2px solid #2ecc71;
        }
        .gradio-dropdown {
            border: 2px solid #2ecc71 !important;
        }
        """

    return f"<style>{base_css}{theme_css}</style>"