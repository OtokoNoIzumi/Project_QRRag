"""
认证服务模块，用于QR码验证和访问控制
"""
import os
import json
import time
from typing import Dict, Optional, Tuple, List
from dataclasses import dataclass
from datetime import datetime


@dataclass
class AccessToken:
    """访问令牌数据类"""
    token_id: str
    theme: str  # "ice" 或 "fire"
    usage_count: int
    max_usage_count: int
    created_at: float
    usage_valid_until: float  # 可用有效期（生成图片）
    access_valid_until: float  # 可访问有效期（只能查看）
    used_image_hashes: List[str]  # 已使用的图片哈希列表
    used_styles: List[str]  # 已使用的风格列表
    generation_records: List[Dict]  # 生成记录列表

    @property
    def is_usage_valid(self) -> bool:
        """检查是否在使用有效期内"""
        return (time.time() < self.usage_valid_until and
                self.usage_count < self.max_usage_count)

    @property
    def is_access_valid(self) -> bool:
        """检查是否在访问有效期内"""
        return time.time() < self.access_valid_until

    @property
    def can_use_more_styles(self) -> bool:
        """检查是否可以使用更多的风格"""
        # 令牌可以对同一张图片使用多种风格，最多3种不同风格
        return len(self.used_styles) < 3

    def has_used_image(self, image_hash: str) -> bool:
        """检查是否已使用过该图片"""
        return image_hash in self.used_image_hashes

    def add_image_hash(self, image_hash: str) -> None:
        """添加已使用的图片哈希"""
        if image_hash not in self.used_image_hashes:
            self.used_image_hashes.append(image_hash)

    def add_used_style(self, style: str) -> None:
        """添加已使用的风格"""
        if style not in self.used_styles and self.can_use_more_styles:
            self.used_styles.append(style)

    def add_generation_record(self, record: Dict) -> None:
        """添加生成记录"""
        self.generation_records.append(record)
        self.usage_count += 1


class AuthService:
    """认证服务类"""

    def __init__(self, tokens_file_path: str):
        """
        初始化认证服务

        Args:
            tokens_file_path: 令牌配置文件路径
        """
        self.tokens_file_path = tokens_file_path
        self.tokens: Dict[str, AccessToken] = {}
        self._load_tokens()

    def _load_tokens(self) -> None:
        """从文件加载令牌"""
        if os.path.exists(self.tokens_file_path):
            try:
                with open(self.tokens_file_path, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                for token_id, token_data in data.items():
                    self.tokens[token_id] = AccessToken(
                        token_id=token_id,
                        theme=token_data.get('theme', 'ice'),
                        usage_count=token_data.get('usage_count', 0),
                        max_usage_count=token_data.get('max_usage_count', 3),
                        created_at=token_data.get('created_at', time.time()),
                        usage_valid_until=token_data.get('usage_valid_until', time.time() + 86400),
                        access_valid_until=token_data.get('access_valid_until', time.time() + 604800),
                        used_image_hashes=token_data.get('used_image_hashes', []),
                        used_styles=token_data.get('used_styles', []),
                        generation_records=token_data.get('generation_records', [])
                    )
            except (json.JSONDecodeError, IOError) as e:
                print(f"加载令牌文件出错: {str(e)}")

    def _save_tokens(self) -> None:
        """保存令牌到文件"""
        try:
            data = {}
            for token_id, token in self.tokens.items():
                data[token_id] = {
                    'theme': token.theme,
                    'usage_count': token.usage_count,
                    'max_usage_count': token.max_usage_count,
                    'created_at': token.created_at,
                    'usage_valid_until': token.usage_valid_until,
                    'access_valid_until': token.access_valid_until,
                    'used_image_hashes': token.used_image_hashes,
                    'used_styles': token.used_styles,
                    'generation_records': token.generation_records
                }

            os.makedirs(os.path.dirname(self.tokens_file_path), exist_ok=True)
            with open(self.tokens_file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except IOError as e:
            print(f"保存令牌文件出错: {str(e)}")

    def validate_token(self, token_id: str) -> Tuple[bool, Optional[str], Optional[AccessToken]]:
        """
        验证令牌

        Args:
            token_id: 令牌ID

        Returns:
            元组: (是否可访问, 错误消息, 令牌对象)
        """
        if token_id not in self.tokens:
            return False, "无效的访问令牌", None

        token = self.tokens[token_id]

        if not token.is_access_valid:
            return False, "令牌已过期", None

        return True, None, token

    def can_generate_image(self, token_id: str) -> Tuple[bool, Optional[str], Optional[AccessToken]]:
        """
        检查是否可以生成图片

        Args:
            token_id: 令牌ID

        Returns:
            元组: (是否可以生成, 错误消息, 令牌对象)
        """
        valid, error_msg, token = self.validate_token(token_id)
        if not valid:
            return False, error_msg, None

        if not token.is_usage_valid:
            if token.usage_count >= token.max_usage_count:
                return False, "已达到最大使用次数", token
            else:
                return False, "使用期已过期", token

        return True, None, token

    def validate_image_hash(self, token_id: str, image_hash: str) -> Tuple[bool, Optional[str]]:
        """
        验证令牌图像使用状态

        Args:
            token_id: 令牌ID
            image_hash: 图像哈希

        Returns:
            元组: (是否可以使用, 错误消息)
        """
        valid, error_msg, token = self.validate_token(token_id)
        if not valid:
            return False, error_msg

        # 检查令牌是否已使用过任何图片
        if len(token.used_image_hashes) > 0:
            # 如果令牌已经使用过图片，检查是否是同一张图片
            if image_hash in token.used_image_hashes:
                # 如果是同一张图片，允许继续使用
                return True, None
            else:
                # 如果是不同图片，拒绝使用
                return False, "此令牌已用于其他图片，不能使用新图片"

        # 如果令牌尚未使用过任何图片，允许使用
        return True, None

    def record_image_usage(self, token_id: str, image_hash: str, style: str, output_images: List[str]) -> bool:
        """
        记录图像使用

        Args:
            token_id: 令牌ID
            image_hash: 图像哈希
            style: 使用的风格
            output_images: 输出图像列表

        Returns:
            是否成功记录
        """
        valid, _, token = self.validate_token(token_id)
        if not valid or token is None:
            return False

        # 添加图像哈希
        token.add_image_hash(image_hash)

        # 添加使用的风格
        token.add_used_style(style)

        # 确保output_images只包含字符串路径
        safe_output_images = []
        for img in output_images:
            # 如果是PIL图像对象，获取其文件路径
            if hasattr(img, 'filename') and img.filename:
                safe_output_images.append(img.filename)
            # 如果已经是字符串路径
            elif isinstance(img, str):
                safe_output_images.append(img)
            # 其他情况，跳过
            else:
                print(f"警告: 跳过不可序列化的图像对象类型: {type(img)}")

        # 添加生成记录
        record = {
            "timestamp": time.time(),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "image_hash": image_hash,
            "style": style,
            "output_files": safe_output_images
        }
        token.add_generation_record(record)

        # 保存令牌
        self._save_tokens()

        return True

    def get_available_styles(self, token_id: str, all_styles: List[str]) -> Dict:
        """
        获取可用的风格列表

        Args:
            token_id: 令牌ID
            all_styles: 所有风格的列表

        Returns:
            风格状态字典
        """
        valid, _, token = self.validate_token(token_id)
        if not valid or token is None:
            return {style: False for style in all_styles}

        # 如果令牌没有使用过任何图片，所有风格都可以使用
        if len(token.used_image_hashes) == 0:
            return {style: None for style in all_styles}  # None表示可用但未使用

        result = {}
        for style in all_styles:
            # 已经使用过的风格设为True
            if style in token.used_styles:
                result[style] = True
            # 如果还可以使用更多风格，设置为可用
            elif token.can_use_more_styles:
                result[style] = None  # None表示可以选择但未使用
            # 否则设为不可用
            else:
                result[style] = False

        return result

    def get_token_data(self, token_id: str) -> Dict:
        """
        获取令牌的数据

        Args:
            token_id: 令牌ID

        Returns:
            令牌数据
        """
        valid, _, token = self.validate_token(token_id)
        if not valid or token is None:
            return {}

        return {
            "theme": token.theme,
            "usage_count": token.usage_count,
            "max_usage_count": token.max_usage_count,
            "is_usage_valid": token.is_usage_valid,
            "is_access_valid": token.is_access_valid,
            "used_styles": token.used_styles,
            "can_use_more_styles": token.can_use_more_styles,
            "generation_records": token.generation_records
        }