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
    if theme == "ice":
        return """
        body {
            background: linear-gradient(135deg, #e0f7ff 0%, #c0e6ff 50%, #a0d5ff 100%);
            color: #0a1b2a;
        }
        .header {
            background: rgba(168, 218, 255, 0.8);
            border-bottom: 2px solid #7fb9ef;
        }
        .btn-primary {
            background-color: #2b8bc8;
            border-color: #1b6ca8;
        }
        .btn-primary:hover {
            background-color: #1c7aba;
        }
        .card {
            background: rgba(255, 255, 255, 0.85);
            border: 1px solid #a0d5ff;
            box-shadow: 0 4px 12px rgba(160, 213, 255, 0.3);
        }
        .footer {
            background: rgba(168, 218, 255, 0.8);
            color: #0a1b2a;
        }
        """
    elif theme == "fire":
        return """
        body {
            background: linear-gradient(135deg, #fff0e0 0%, #ffd0a0 50%, #ffb060 100%);
            color: #2a140a;
        }
        .header {
            background: rgba(255, 200, 150, 0.8);
            border-bottom: 2px solid #ef9f7f;
        }
        .btn-primary {
            background-color: #c86a2b;
            border-color: #a8581b;
        }
        .btn-primary:hover {
            background-color: #ba5c1c;
        }
        .card {
            background: rgba(255, 255, 255, 0.85);
            border: 1px solid #ffc080;
            box-shadow: 0 4px 12px rgba(255, 192, 128, 0.3);
        }
        .footer {
            background: rgba(255, 200, 150, 0.8);
            color: #2a140a;
        }
        """
    else:
        # 默认样式
        return """
        body {
            background: #f0f0f0;
            color: #333;
        }
        """