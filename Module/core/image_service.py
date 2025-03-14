"""
图像服务模块，用于图像处理、指纹生成和生成逻辑
"""
import os
import base64
import hashlib
import time
from typing import Dict, Optional, Tuple
from datetime import datetime

from ..Common.scripts.llm.utils.google_whisk import (
    generate_image_base64,
    DEFAULT_STYLE_PROMPT_DICT,
    AspectRatio
)


def calculate_image_hash(image_data) -> str:
    """
    计算图像指纹哈希

    Args:
        image_data: 图像数据，可以是文件路径或Base64字符串

    Returns:
        图像哈希值
    """
    if isinstance(image_data, str):
        if os.path.exists(image_data):  # 文件路径
            with open(image_data, 'rb') as f:
                img_bytes = f.read()
        else:  # 假设是Base64字符串
            try:
                img_bytes = base64.b64decode(image_data)
            except:
                return hashlib.sha256(image_data.encode()).hexdigest()
    else:
        return hashlib.sha256(str(image_data).encode()).hexdigest()

    # 计算哈希
    return hashlib.sha256(img_bytes).hexdigest()


class ImageService:
    """图像服务类"""

    def __init__(self, whisk_service, cache_dir: str, nezha_config: Dict):
        """
        初始化图像服务

        Args:
            whisk_service: Whisk服务实例
            cache_dir: 缓存目录
            nezha_config: 哪吒项目配置
        """
        self.whisk_service = whisk_service
        self.cache_dir = cache_dir
        self.config = nezha_config
        self.image_cache_dir = os.path.join(cache_dir, "image")

        # 确保缓存目录存在
        os.makedirs(self.image_cache_dir, exist_ok=True)

    def get_theme_style_prompts(self, theme: str) -> Dict[str, str]:
        """
        获取主题对应的风格提示词

        Args:
            theme: 主题名称

        Returns:
            风格提示词字典
        """
        theme_config = self.config.get("themes", {}).get(theme, {})
        style_prompts = theme_config.get("style_prompts", {})

        # 如果没有找到风格配置，则使用默认风格
        if not style_prompts:
            return DEFAULT_STYLE_PROMPT_DICT

        return style_prompts

    def get_theme_location_prompt(self, theme: str) -> str:
        """
        获取主题对应的位置提示词

        Args:
            theme: 主题名称

        Returns:
            位置提示词
        """
        theme_config = self.config.get("themes", {}).get(theme, {})
        return theme_config.get("location_prompt", "")

    def get_theme_pose_prompt(self, theme: str) -> str:
        """
        获取主题对应的姿势提示词

        Args:
            theme: 主题名称

        Returns:
            姿势提示词
        """
        theme_config = self.config.get("themes", {}).get(theme, {})
        return theme_config.get("pose_prompt", "")

    def process_image(
        self,
        image_path: str,
        token_id: str,
        theme: str,
        style_key: str,
        additional_text: str = ""
    ) -> Tuple[Optional[str], Optional[str], Dict]:
        """
        处理图像生成

        Args:
            image_path: 图像路径
            token_id: 令牌ID
            theme: 主题
            style_key: 风格键名
            additional_text: 附加文本

        Returns:
            元组: (输出图像1, 输出图像2, 处理数据)
        """
        # 创建处理数据字典，用于记录处理过程
        process_data = {
            "token_id": token_id,
            "theme": theme,
            "style_key": style_key,
            "additional_text": additional_text,
            "timestamp": time.time(),
            "datetime": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "success": False,
            "error_message": None
        }

        try:
            # 生成输出前缀
            current_date = datetime.now().strftime("%Y%m%d")
            counter = len([f for f in os.listdir(self.image_cache_dir)
                          if f.startswith(f"nezha_{token_id}_{current_date}")]) + 1
            output_prefix = os.path.join(
                self.image_cache_dir,
                f"nezha_{token_id}_{current_date}_take{counter}"
            )

            # 准备图片数据
            base64_str = generate_image_base64(image_path)
            image_hash = calculate_image_hash(base64_str)
            process_data["image_hash"] = image_hash

            # 生成图片描述
            caption = self.whisk_service.generate_caption_wrapped(base64_str)
            if not caption:
                process_data["error_message"] = "生成图片描述失败"
                return None, None, process_data

            process_data["caption"] = caption

            # 获取主题特定配置
            style_prompts = self.get_theme_style_prompts(theme)
            style_prompt = style_prompts.get(style_key, "")
            location_prompt = self.get_theme_location_prompt(theme)
            pose_prompt = self.get_theme_pose_prompt(theme)

            # 生成故事板提示词
            final_prompt = self.whisk_service.generate_story_board_wrapped(
                characters=[caption],
                style_prompt=style_prompt,
                location_prompt=location_prompt,
                pose_prompt=pose_prompt,
                additional_input=additional_text
            )

            if not final_prompt:
                process_data["error_message"] = "生成故事板提示词失败"
                return None, None, process_data

            process_data["final_prompt"] = final_prompt

            # 生成最终图片
            aspect_ratio = AspectRatio[self.config.get("image_generation", {}).get("aspect_ratio", "LANDSCAPE")]
            image_number = self.config.get("image_generation", {}).get("default_image_number", 2)

            image_files = self.whisk_service.generate_image_fx_wrapped(
                prompt=final_prompt,
                output_prefix=output_prefix,
                image_number=image_number,
                aspect_ratio=aspect_ratio
            )

            if not image_files:
                process_data["error_message"] = "生成图片失败"
                return None, None, process_data

            # 记录成功
            process_data["success"] = True
            process_data["output_images"] = image_files

            return (
                image_files[0] if image_files else None,
                image_files[1] if len(image_files) > 1 else None,
                process_data
            )

        except Exception as e:
            error_message = f"图片处理错误: {str(e)}"
            process_data["error_message"] = error_message
            print(error_message)
            return None, None, process_data
