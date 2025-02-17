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
# 创建缓存目录
os.makedirs(os.path.join(current_dir, CACHE_DIR), exist_ok=True)
os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)

# 全局变量初始化
image_caption_cache = {}
story_prompt_cache = {}


# 加载缓存
def load_cache():
    """从文件加载缓存"""
    global image_caption_cache, story_prompt_cache

    if os.path.exists(CAPTION_CACHE_FILE):
        with open(CAPTION_CACHE_FILE, 'r', encoding='utf-8') as cache_file:
            image_caption_cache = json.load(cache_file)
    else:
        image_caption_cache = {}

    if os.path.exists(STORY_CACHE_FILE):
        with open(STORY_CACHE_FILE, 'r', encoding='utf-8') as cache_file:
            story_prompt_cache = json.load(cache_file)
    else:
        story_prompt_cache = {}


# 保存缓存
def save_cache():
    """保存缓存到文件"""
    with open(CAPTION_CACHE_FILE, 'w', encoding='utf-8') as cache_file:
        json.dump(image_caption_cache, cache_file, ensure_ascii=False, indent=2)
    with open(STORY_CACHE_FILE, 'w', encoding='utf-8') as cache_file:
        json.dump(story_prompt_cache, cache_file, ensure_ascii=False, indent=2)


# 初始加载缓存
load_cache()


def get_cached_caption(image_base64: str):
    """获取缓存的图片描述"""
    if not image_base64:
        return None

    # 直接使用base64字符串计算哈希值
    hash_key = hashlib.md5(image_base64.encode()).hexdigest()
    return image_caption_cache.get(hash_key)


def cache_caption(image_base64: str, caption: str):
    """缓存图片描述"""
    if not image_base64 or not caption:
        return

    hash_key = hashlib.md5(image_base64.encode()).hexdigest()
    image_caption_cache[hash_key] = caption
    save_cache()


def get_cached_story_prompt(caption: str, style_key: str, additional_text: str):
    """获取缓存的故事提示词"""
    if not caption:
        return None

    # 使用所有输入参数组合生成缓存键
    cache_key = hashlib.md5(f"{caption}_{style_key}_{additional_text}".encode()).hexdigest()
    return story_prompt_cache.get(cache_key)


def cache_story_prompt(caption: str, style_key: str, additional_text: str, prompt: str):
    """缓存故事提示词"""
    if not caption or not prompt:
        return

    cache_key = hashlib.md5(f"{caption}_{style_key}_{additional_text}".encode()).hexdigest()
    story_prompt_cache[cache_key] = prompt
    save_cache()


gradio_auth_keeper = AuthKeeper(
    config_path=os.path.join(current_dir, "auth_config.json"),
    default_headers=DEFAULT_HEADERS
)

gradio_sustain_auth_cookies = sustain_auth(gradio_auth_keeper, 'cookies')
gradio_sustain_auth_token = sustain_auth(gradio_auth_keeper, 'auth_token')


@gradio_sustain_auth_cookies
def gradio_generate_caption(
    image_base64: str,
    category: Category = Category.CHARACTER,
    cookies: Optional[str] = None,  # 显式声明装饰器将注入的参数
) -> Dict:
    """生成图片描述包装函数"""
    return generate_caption(image_base64, category, cookies)


@gradio_sustain_auth_cookies
def gradio_generate_story_board(
    characters: Optional[List[str]] = None,
    style_prompt: Optional[str] = None,
    location_prompt: Optional[str] = None,
    pose_prompt: Optional[str] = None,
    additional_input: str = "",
    cookies: Optional[str] = None,  # 显式声明装饰器将注入的参数
) -> Dict:
    """生成故事提示词包装函数"""
    return generate_story_board(
        characters,
        style_prompt,
        location_prompt,
        pose_prompt,
        additional_input,
        cookies
    )


@gradio_sustain_auth_token
def gradio_generate_image_fx(
    prompt: str,
    seed: Optional[int] = None,
    aspect_ratio: AspectRatio = AspectRatio.LANDSCAPE,
    output_prefix: str = "generated_image",
    image_number: int = 4,
    auth_token: Optional[str] = None,  # 显式声明装饰器将注入的参数
) -> Dict:
    """生成图片包装函数"""
    return generate_image_fx(
        prompt,
        seed,
        aspect_ratio,
        output_prefix,
        image_number,
        auth_token
    )


# 在 demo 定义之前添加函数
def generate_images(
    image_input1: str,
    image_input2: str,
    style_key: str,
    additional_text: str
) -> tuple[str, str]:
    """处理图片生成请求"""
    try:
        # 1. 如果没有上传图片，直接返回
        if image_input1 is None and image_input2 is None:
            return None, None

        # 处理所有输入图片
        captions = []
        all_cached = True  # 用于跟踪是否所有caption都命中缓存
        for image_input in [image_input1, image_input2]:
            if image_input is not None:
                # 生成base64
                image_base64 = generate_image_base64(image_input)

                # 检查缓存中是否有caption
                caption = get_cached_caption(image_base64)
                if caption is None:
                    caption = gradio_generate_caption(image_base64)
                    if caption:
                        cache_caption(image_base64, caption)
                    all_cached = False  # 只要有一个caption没有命中缓存，就设为False
                if caption:
                    captions.append(caption)

        if not captions:
            return None, None

        # 2. 获取风格提示词
        style_prompt = DEFAULT_STYLE_PROMPT_DICT.get(style_key, "")

        # 3. 检查story prompt缓存
        # 使用所有caption拼接作为缓存key
        caption_text = "|".join(captions)
        final_prompt = get_cached_story_prompt(caption_text, style_key, additional_text)
        story_cache_used = final_prompt is not None

        if final_prompt is None:
            # 如果缓存中没有，则生成新的story prompt
            final_prompt = gradio_generate_story_board(
                characters=captions,
                style_prompt=style_prompt,
                additional_input=additional_text,
                # cookies=auth_config.cookies
            )
            if final_prompt:
                cache_story_prompt(caption_text, style_key, additional_text, final_prompt)

        # 打印日志
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time}] 生成图片 | 素材提示词缓存: {'启用' if all_cached else '未启用'} | "
              f"最终提示词缓存: {'启用' if story_cache_used else '未启用'} | "
              f"最终Prompt: \n{final_prompt}")

        # 4. 生成图片
        if final_prompt:
            image_files = gradio_generate_image_fx(
                prompt=final_prompt,
                # auth_token=auth_config.auth_token,
                output_prefix=(
                    IMAGE_CACHE_DIR +
                    r"\generated_image_" +
                    datetime.now().strftime("%Y%m%d")
                ),
                image_number=2
            )
            # 获取第一张和第二张生成的图片
            first_image = image_files[0] if image_files else None
            second_image = image_files[1] if len(image_files) > 1 else None
            return first_image, second_image
        return None, None

    except Exception as e:
        print(f"Error generating images: {e}")
        return None, None


# 在 demo 定义中添加新的界面
with gr.Blocks(theme="soft") as demo:
    with gr.Row():
        # 左侧输入区域
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

        # 右侧输出区域
        with gr.Column(scale=2):
            output_image1 = gr.Image(label="生成结果 1")
            output_image2 = gr.Image(label="生成结果 2")

    generate_btn.click(
        fn=generate_images,
        inputs=[input_image1, input_image2, style_dropdown, additional_text_ui],
        outputs=[output_image1, output_image2]
    )

if __name__ == "__main__":
    demo.launch(
        server_name="0.0.0.0",
        server_port=8765,
        ssl_verify=False,
        share=True,
        allowed_paths=[IMAGE_CACHE_DIR]
    )
