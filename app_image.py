# pylint: disable=no-member  # Project structure requires dynamic path handling
"""
whisk逆向图片生成
"""
import os
import sys
import hashlib
import json
from datetime import datetime
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
)


class AuthConfig:
    """认证配置"""
    def __init__(self):
        self.cookies = config.get("cookies", "")
        self.auth_token = config.get("auth_token", "")


with open(os.path.join(current_dir, "auth_config.json"), 'r', encoding='utf-8') as f:
    config = json.load(f)

auth_config = AuthConfig()

# 缓存文件路径
CACHE_DIR = "cache"
CAPTION_CACHE_FILE = os.path.join(current_dir, CACHE_DIR, "image_caption_cache.json")
STORY_CACHE_FILE = os.path.join(current_dir, CACHE_DIR, "story_prompt_cache.json")

IMAGE_CACHE_DIR = os.path.join(current_dir, CACHE_DIR, "image")
# 创建缓存目录
os.makedirs(os.path.join(current_dir, CACHE_DIR), exist_ok=True)
os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)


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


# 在 demo 定义之前添加函数
def generate_images(image_input, style_key, additional_text):
    """处理图片生成请求"""
    try:
        # 1. 如果没有上传图片，直接返回
        if image_input is None:
            return None, None

        # 直接使用文件路径生成base64
        image_base64 = generate_image_base64(image_input)

        # 2. 检查缓存中是否有caption
        caption = get_cached_caption(image_base64)
        caption_cache_used = caption is not None
        if caption is None:
            # 如果缓存中没有，则生成新的caption
            caption = generate_caption(image_base64, cookies=auth_config.cookies)
            if caption:
                cache_caption(image_base64, caption)

        # 2. 获取风格提示词
        style_prompt = DEFAULT_STYLE_PROMPT_DICT.get(style_key, "")

        # 3. 检查story prompt缓存
        final_prompt = get_cached_story_prompt(caption, style_key, additional_text)
        story_cache_used = final_prompt is not None
        if final_prompt is None:
            # 如果缓存中没有，则生成新的story prompt
            style_prompt = DEFAULT_STYLE_PROMPT_DICT.get(style_key, "")
            final_prompt = generate_story_board(
                characters=[caption] if caption else [],
                style_prompt=style_prompt,
                additional_input=additional_text,
                cookies=auth_config.cookies
            )
            if final_prompt:
                cache_story_prompt(caption, style_key, additional_text, final_prompt)

        # 打印日志
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        print(f"[{current_time}] 生成图片 | 素材提示词缓存: {'启用' if caption_cache_used else '未启用'} | "
              f"最终提示词缓存: {'启用' if story_cache_used else '未启用'} | "
              f"最终Prompt: \n{final_prompt}")

        # 4. 生成图片
        if final_prompt:
            image_files = generate_image_fx(
                prompt=final_prompt,
                auth_token=auth_config.auth_token,
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
            input_image = gr.Image(
                label="上传图片",
                type="filepath",
                height=300  # 限制图片显示高度
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
        inputs=[input_image, style_dropdown, additional_text_ui],
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
