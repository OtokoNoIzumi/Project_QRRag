"""
管理员服务模块，用于处理管理员相关功能
"""
import os
import json
import time
from datetime import datetime, timedelta
from typing import List, Optional
from dataclasses import dataclass
import qrcode
from PIL import Image, ImageDraw, ImageFont


@dataclass
class TokenConfig:
    """Token配置数据类"""
    token_id: str
    theme: str
    max_usage_count: int
    usage_valid_until: float
    access_valid_until: float
    prefix: str
    sequence: int


class AdminService:
    """管理员服务类"""

    def __init__(self, storage_dir: str, tokens_file: str):
        """
        初始化管理员服务

        Args:
            storage_dir: 存储目录路径
            tokens_file: 令牌文件路径
        """
        self.storage_dir = storage_dir
        self.tokens_file = tokens_file
        self.qr_codes_dir = os.path.join(storage_dir, "qrcodes")
        self.posters_dir = os.path.join(storage_dir, "posters")
        os.makedirs(self.qr_codes_dir, exist_ok=True)
        os.makedirs(self.posters_dir, exist_ok=True)

    def generate_tokens(
        self,
        count: int,
        theme: str,
        prefix: str = "",
        max_usage_count: int = 10,
        usage_valid_days: int = 2,
        access_valid_days: int = 9
    ) -> List[TokenConfig]:
        """
        生成令牌

        Args:
            count: 生成数量
            theme: 主题
            prefix: 令牌前缀
            max_usage_count: 最大使用次数
            usage_valid_days: 使用有效期天数
            access_valid_days: 访问有效期天数

        Returns:
            生成的令牌配置列表
        """
        # 验证参数
        if count < 1 or count > 100:
            raise ValueError("生成数量必须在1-100之间")

        # 计算有效期
        now = time.time()
        usage_valid_until = (datetime.now() + timedelta(days=usage_valid_days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()
        access_valid_until = (datetime.now() + timedelta(days=access_valid_days)).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).timestamp()

        # 生成令牌
        tokens = []
        for i in range(count):
            # 生成令牌ID
            token_id = f"{prefix}{int(now) + i}"

            # 创建令牌配置
            token_config = TokenConfig(
                token_id=token_id,
                theme=theme,
                max_usage_count=max_usage_count,
                usage_valid_until=usage_valid_until,
                access_valid_until=access_valid_until,
                prefix=prefix,
                sequence=i + 1
            )
            tokens.append(token_config)

        return tokens

    def save_tokens(self, tokens: List[TokenConfig]) -> bool:
        """
        保存令牌到文件

        Args:
            tokens: 令牌配置列表

        Returns:
            是否成功保存
        """
        try:
            # 读取现有令牌
            existing_tokens = {}
            if os.path.exists(self.tokens_file):
                with open(self.tokens_file, 'r', encoding='utf-8') as f:
                    existing_tokens = json.load(f)

            # 添加新令牌
            for token in tokens:
                existing_tokens[token.token_id] = {
                    "theme": token.theme,
                    "usage_count": 0,
                    "max_usage_count": token.max_usage_count,
                    "created_at": time.time(),
                    "usage_valid_until": token.usage_valid_until,
                    "access_valid_until": token.access_valid_until,
                    "used_image_hashes": [],
                    "used_styles": [],
                    "generation_records": []
                }

            # 保存更新后的令牌
            with open(self.tokens_file, 'w', encoding='utf-8') as f:
                json.dump(existing_tokens, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"保存令牌出错: {str(e)}")
            return False

    def generate_qr_codes(self, tokens: List[TokenConfig]) -> List[str]:
        """
        生成二维码

        Args:
            tokens: 令牌配置列表

        Returns:
            生成的二维码文件路径列表
        """
        qr_files = []
        # 从配置文件中读取URL
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(self.storage_dir))), "style", "nezha", "config.json")
        with open(config_path, 'r', encoding='utf-8') as config_file:
            config = json.load(config_file)

        # 构建基础URL
        base_url = config.get('base_url', 'http://localhost:7860')

        for token in tokens:
            # 创建二维码
            qr = qrcode.QRCode(
                version=1,
                error_correction=qrcode.constants.ERROR_CORRECT_L,
                box_size=10,
                border=4,
            )

            # 生成访问URL，使用配置中的URL
            url = f"{base_url}/?token={token.token_id}"
            qr.add_data(url)
            qr.make(fit=True)

            # 创建二维码图片
            qr_image = qr.make_image(fill_color="black", back_color="white")

            # 保存二维码
            qr_file = os.path.join(self.qr_codes_dir, f"{token.token_id}.png")
            qr_image.save(qr_file)
            qr_files.append(qr_file)

        return qr_files

    def create_poster(
        self,
        qr_file: str,
        template_file: str,
        sequence_prefix: str,
        sequence_number: int
    ) -> Optional[str]:
        """
        创建海报

        Args:
            qr_file: 二维码文件路径
            template_file: 模板文件路径
            sequence_prefix: 序列号前缀
            sequence_number: 序列号

        Returns:
            生成的海报文件路径
        """
        try:
            # 打开模板和二维码
            template = Image.open(template_file)
            qr = Image.open(qr_file)

            # 获取模板尺寸
            template_width, template_height = template.size

            # 调整二维码大小，使其不会占据太多海报空间
            # 将二维码调整为海报高度的30%
            qr_size = int(template_height * 0.3)
            qr_resized = qr.resize((qr_size, qr_size), Image.LANCZOS)

            # 创建海报副本
            poster = template.copy()
            draw = ImageDraw.Draw(poster)

            # 添加序列号
            try:
                font = ImageFont.truetype("arial.ttf", 36)
            except:
                font = ImageFont.load_default()

            sequence_text = f"{sequence_prefix}{sequence_number}"
            draw.text((10, 10), sequence_text, font=font, fill="black")

            # 将二维码粘贴到海报左下角
            # 计算左下角位置，留出10像素的边距
            qr_position = (10, template_height - qr_size - 10)
            poster.paste(qr_resized, qr_position)

            # 保存海报
            poster_file = os.path.join(
                self.posters_dir,
                f"poster_{sequence_prefix}{sequence_number}.png"
            )
            poster.save(poster_file)

            return poster_file
        except Exception as e:
            print(f"创建海报出错: {str(e)}")
            return None

    def generate_posters(
        self,
        qr_files: List[str],
        template_file: str,
        sequence_prefix: str,
        start_number: int
    ) -> List[str]:
        """
        批量生成海报

        Args:
            qr_files: 二维码文件路径列表
            template_file: 模板文件路径
            sequence_prefix: 序列号前缀
            start_number: 起始序列号

        Returns:
            生成的海报文件路径列表
        """
        poster_files = []
        for i, qr_file in enumerate(qr_files):
            poster_file = self.create_poster(
                qr_file=qr_file,
                template_file=template_file,
                sequence_prefix=sequence_prefix,
                sequence_number=start_number + i
            )
            if poster_file:
                poster_files.append(poster_file)
        return poster_files
