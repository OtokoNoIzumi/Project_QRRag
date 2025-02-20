# pylint: disable=no-member  # Project structure requires dynamic path handling
"""
whisk逆向图片生成
"""
import os
import sys
import hashlib
import json
from datetime import datetime
from typing import Optional, List, Dict
from requests.exceptions import HTTPError
import gradio as gr

# ===== 2. 初始化配置 =====
# 获取当前文件所在目录的绝对路径
if "__file__" in globals():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    root_dir = os.path.normpath(os.path.join(current_dir, ".."))
else:
    # 在 Jupyter Notebook 环境中
    current_dir = os.getcwd()
    current_dir = os.path.join(current_dir, "..")
    root_dir = os.path.normpath(os.path.join(current_dir))

current_dir = os.path.normpath(current_dir)
sys.path.append(current_dir)

from Module.Common.scripts.llm.utils.google_whisk import (
    generate_image_base64,
    generate_caption,
    generate_image_fx,
    generate_story_board,
    DEFAULT_STYLE_PROMPT_DICT,
    DEFAULT_HEADERS,
    AspectRatio,
    Category
)
from Module.Common.scripts.common.auth_manager import (
    AuthKeeper,
    sustain_auth
)

# 缓存文件路径
CACHE_DIR = "cache"
CAPTION_CACHE_FILE = os.path.join(current_dir, CACHE_DIR, "image_caption_cache.json")
STORY_CACHE_FILE = os.path.join(current_dir, CACHE_DIR, "story_prompt_cache.json")
IMAGE_CACHE_DIR = os.path.join(current_dir, CACHE_DIR, "image")


class WhiskCache:
    """Whisk缓存管理类"""
    def __init__(self):
        os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
        self.caption_cache = self._load_cache(CAPTION_CACHE_FILE)
        self.story_cache = self._load_cache(STORY_CACHE_FILE)

    def _load_cache(self, file_path: str) -> Dict:
        """加载缓存文件"""
        if os.path.exists(file_path):
            with open(file_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}

    def save_cache(self, file_path: str, data: Dict):
        """保存缓存到文件"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def get_caption(self, image_base64: str):
        """获取缓存的图片描述"""
        hash_key = hashlib.md5(image_base64.encode()).hexdigest()
        return self.caption_cache.get(hash_key)

    def save_caption(self, image_base64: str, caption: str):
        """缓存图片描述"""
        hash_key = hashlib.md5(image_base64.encode()).hexdigest()
        self.caption_cache[hash_key] = caption
        self.save_cache(CAPTION_CACHE_FILE, self.caption_cache)

    def get_story_prompt(self, caption: str, style_key: str, additional_text: str):
        """获取缓存的故事提示词"""
        cache_key = hashlib.md5(f"{caption}_{style_key}_{additional_text}".encode()).hexdigest()
        return self.story_cache.get(cache_key)

    def save_story_prompt(self, caption: str, style_key: str, additional_text: str, prompt: str):
        """缓存故事提示词"""
        cache_key = hashlib.md5(f"{caption}_{style_key}_{additional_text}".encode()).hexdigest()
        self.story_cache[cache_key] = prompt
        self.save_cache(STORY_CACHE_FILE, self.story_cache)


class WhiskService:
    """Whisk服务类"""
    def __init__(self):
        self.cache = WhiskCache()
        self.auth_keeper = AuthKeeper(
            config_path=os.path.join(current_dir, "auth_config.json"),
            default_headers=DEFAULT_HEADERS
        )
        # 保持原始装饰器调用方式
        self.sustain_cookies = sustain_auth(self.auth_keeper, 'cookies')
        self.sustain_token = sustain_auth(self.auth_keeper, 'auth_token')

    @property
    def generate_caption_wrapped(self):
        """保持装饰器调用方式不变"""
        return self.sustain_cookies(self._generate_caption_impl)

    def _generate_caption_impl(
        self,
        image_base64: str,
        category: Category = Category.CHARACTER,  # 补全参数
        cookies: str = None  # 保持装饰器参数
    ) -> Dict:
        return generate_caption(
            image_base64=image_base64,
            category=category,  # 传递补全参数
            cookies=cookies
        )

    @property
    def generate_story_board_wrapped(self):
        """保持装饰器调用方式不变"""
        return self.sustain_cookies(self._generate_story_board_impl)

    def _generate_story_board_impl(
        self,
        characters: Optional[List[str]] = None,
        style_prompt: Optional[str] = None,
        location_prompt: Optional[str] = None,  # 补全参数
        pose_prompt: Optional[str] = None,       # 补全参数
        additional_input: str = "",
        cookies: str = None
    ) -> Dict:
        return generate_story_board(
            characters=characters,
            style_prompt=style_prompt,
            location_prompt=location_prompt,  # 传递补全参数
            pose_prompt=pose_prompt,           # 传递补全参数
            additional_input=additional_input,
            cookies=cookies
        )

    @property
    def generate_image_fx_wrapped(self):
        """保持装饰器调用方式不变"""
        return self.sustain_token(self._generate_image_fx_impl)

    def _generate_image_fx_impl(
        self,
        prompt: str,
        seed: Optional[int] = None,
        aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
        output_prefix: str = None,
        image_number: int = 4,
        auth_token: str = None,
        save_local: bool = False  # 补全参数
    ) -> List:
        return generate_image_fx(
            prompt=prompt,
            seed=seed,
            aspect_ratio=aspect_ratio,
            output_prefix=output_prefix,
            image_number=image_number,
            auth_token=auth_token,
            save_local=save_local  # 传递补全参数
        )

    def generate_images(
        self,
        image_input1: str,
        image_input2: str,
        style_key: str,
        additional_text: str
    ):
        """处理图片生成请求"""
        # 1. 基础检查
        if not image_input1 and not image_input2:
            return None, None

        # 2. 预处理图片数据
        image_data = []
        all_caption_cached = True
        for image_input in [image_input1, image_input2]:
            if image_input:
                base64_str = generate_image_base64(image_input)
                cached_caption = self.cache.get_caption(base64_str)
                image_data.append((base64_str, cached_caption))
                if cached_caption is None:
                    all_caption_cached = False

        # 检查story prompt缓存
        if all_caption_cached:
            caption_text = "|".join(
                caption for _, caption in image_data
            )
            story_prompt_cached = self.cache.get_story_prompt(
                caption_text,
                style_key,
                additional_text
            ) is not None if caption_text else False
        else:
            story_prompt_cached = False

        # 打印缓存状态
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(
            f"\n[{current_time}] 生成图片 | "
            f"素材提示词缓存: {'启用' if all_caption_cached else '未启用'} | "
            f"最终提示词缓存: {'启用' if story_prompt_cached else '未启用'}"
        )

        try:
            # 3. 生成描述和故事板
            captions = []
            for base64_str, cached_caption in image_data:
                if not cached_caption:
                    new_caption = self.generate_caption_wrapped(base64_str)
                    if new_caption:
                        self.cache.save_caption(base64_str, new_caption)
                        captions.append(new_caption)
                else:
                    captions.append(cached_caption)

            if not captions:
                return None, None

            # 4. 生成最终图片
            final_prompt = self.cache.get_story_prompt(
                "|".join(captions),
                style_key,
                additional_text
            )
            if not final_prompt:
                final_prompt = self.generate_story_board_wrapped(
                    characters=captions,
                    style_prompt=DEFAULT_STYLE_PROMPT_DICT.get(style_key, ""),
                    additional_input=additional_text
                )
                if final_prompt:
                    self.cache.save_story_prompt(
                        "|".join(captions),
                        style_key,
                        additional_text,
                        final_prompt
                    )

            current_date = datetime.now().strftime("%Y%m%d")
            output_prefix = os.path.join(
                IMAGE_CACHE_DIR,
                f"generated_image_{current_date}_take{len(os.listdir(IMAGE_CACHE_DIR)) + 1}"
            )

            print(f"最终Prompt: \n{final_prompt}")
            image_files = self.generate_image_fx_wrapped(
                prompt=final_prompt,
                output_prefix=output_prefix,
                image_number=2
            )

            return (
                image_files[0] if image_files else None,
                image_files[1] if len(image_files) > 1 else None
            )

        except HTTPError as e:
            # 提取详细信息
            error_info = {
                "status_code": e.response.status_code,
                "reason": e.response.reason,
                "url": e.response.url,
                "response_text": e.response.text[:200]  # 截取前200字符避免过大
            }
            error_source = self._detect_error_source(e.response.url)

            if error_info['status_code'] == 401:
                print(f"[{error_source}] 自动续签认证失败，添加一个飞书消息...")
            elif error_info['status_code'] == 400:
                print(f"[{error_source}] 业务和谐，计划重试...")
            else:
                print(f"[{error_source}] 其他HTTP错误，添加一个飞书消息...")

            return None, None
            # raise  # 重新抛出或返回错误信息
        except Exception as e:
            print(f"其他图片生成错误: {str(e)}")
            return None, None

    def _detect_error_source(self, url):
        """优化后的错误来源检测（直观简洁版）"""
        error_patterns = {
            'runImageFx': 'step3.图片生成',
            'generateStoryBoardPrompt': 'step2.故事板生成',
            'generateCaption': 'step1.描述生成'
        }
        return next(
            (v for k, v in error_patterns.items() if k in url),
            '未知来源'  # 默认值
        )


# 创建服务实例
whisk_service = WhiskService()

# Gradio界面
with gr.Blocks(theme="soft") as demo:
    with gr.Row():
        with gr.Column(scale=1):
            with gr.Row():
                input_image1 = gr.Image(
                    label="上传图片1",
                    type="filepath",
                    height=300
                )
                input_image2 = gr.Image(
                    label="上传图片2（可选）",
                    type="filepath",
                    height=300
                )
            style_dropdown = gr.Dropdown(
                choices=list(DEFAULT_STYLE_PROMPT_DICT.keys()),
                value=list(DEFAULT_STYLE_PROMPT_DICT.keys())[0],
                label="选择风格"
            )
            additional_text_ui = gr.Textbox(
                label="补充提示词",
                placeholder="请输入额外的提示词...",
                lines=3
            )
            generate_btn = gr.Button("生成图片")

        with gr.Column(scale=2):
            output_image1 = gr.Image(label="生成结果 1")
            output_image2 = gr.Image(label="生成结果 2")

    generate_btn.click(
        fn=whisk_service.generate_images,
        inputs=[input_image1, input_image2, style_dropdown, additional_text_ui],
        outputs=[output_image1, output_image2]
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=80,
        ssl_verify=False,
        share=True,
        allowed_paths=[IMAGE_CACHE_DIR]
    )
