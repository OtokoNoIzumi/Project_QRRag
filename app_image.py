# pylint: disable=no-member  # Project structure requires dynamic path handling
"""
whisk逆向图片生成
"""
import os
import sys
import json
from datetime import datetime
from typing import Optional, List, Dict
from requests.exceptions import HTTPError
from dotenv import load_dotenv
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
from Module.Common.scripts.datasource_feishu import FeishuClient
from Module.cache_sqlite import WhiskCache

CONFIG_PATH = os.path.join(current_dir, "config.json")

# 加载配置文件
with open(CONFIG_PATH, 'r', encoding='utf-8') as config_file:
    CONFIG = json.load(config_file)

# 修改后的常量定义
IMAGE_NUMBER = CONFIG["image_generation"]["default_image_number"]
ASPECT_RATIO = AspectRatio[CONFIG["image_generation"]["aspect_ratio"]]
ERROR_PATTERNS = CONFIG["error_patterns"]

# 缓存文件路径
CACHE_DIR = os.path.join(current_dir, CONFIG["cache"]["dir"])
CAPTION_CACHE_FILE = os.path.join(CACHE_DIR, CONFIG["cache"]["caption_file"])
STORY_CACHE_FILE = os.path.join(CACHE_DIR, CONFIG["cache"]["story_file"])
IMAGE_CACHE_DIR = os.path.join(CACHE_DIR, CONFIG["cache"]["image_dir"])


load_dotenv(os.path.join(current_dir, ".env"))

app_id = os.getenv("FEISHU_APP_ID", "")
app_secret = os.getenv("FEISHU_APP_SECRET", "")
FEISHU_RECEIVE_ID = os.getenv("RECEIVE_ID", "")

# 改进后的飞书客户端初始化（更Pythonic的写法）
FEISHU_CLIENT = None
FEISHU_ENABLED = False
if app_id and app_secret:  # 先做基础检查
    try:
        FEISHU_CLIENT = FeishuClient(app_id, app_secret)
        FEISHU_CLIENT.get_access_token()  # 主动验证凭证有效性
        FEISHU_ENABLED = True
    except (ValueError, RuntimeError) as e:
        print(f"⚠️ 飞书通知功能已禁用: {str(e)}")
else:
    print("⚠️ 飞书通知功能已禁用: 缺少FEISHU_APP_ID或FEISHU_APP_SECRET环境变量")


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
        # 基础参数准备
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_date = datetime.now().strftime("%Y%m%d")
        output_prefix = os.path.join(
            IMAGE_CACHE_DIR,
            f"generated_image_{current_date}_take{len(os.listdir(IMAGE_CACHE_DIR)) + 1}"
        )

        # 处理指令直出模式
        if additional_text.startswith('/img') and len(additional_text) > 4:
            clean_prompt = additional_text[4:].strip()
            if clean_prompt:
                return self._handle_direct_mode(clean_prompt, current_time, output_prefix)

        # 输入检查
        if not any([image_input1, image_input2]):
            return None, None

        # 预处理图片数据
        image_data = self._prepare_image_data(image_input1, image_input2)
        all_caption_cached = all(caption for _, caption in image_data)

        # 打印缓存状态
        self._print_cache_status(
            current_time=current_time,
            all_caption_cached=all_caption_cached,
            image_data=image_data,
            style_key=style_key,
            additional_text=additional_text
        )

        try:
            # 生成描述和故事板
            captions = self._process_captions(image_data)
            if not captions:
                return None, None

            # 生成最终提示词
            final_prompt = self._get_final_prompt(captions, style_key, additional_text)
            print(f"最终Prompt: \n{final_prompt}")

            return self._generate_final_images(final_prompt, output_prefix)

        except HTTPError as e:
            return self._handle_http_error(e)
        except Exception as e:
            print(f"其他图片生成错误: {str(e)}")
            return None, None

    def _handle_direct_mode(self, clean_prompt, current_time, output_prefix):
        """处理指令直出模式"""
        print(f"[{current_time}] 指令直出，使用提示词: \n{clean_prompt}")
        try:
            image_files = self.generate_image_fx_wrapped(
                prompt=clean_prompt,
                output_prefix=output_prefix,
                image_number=2
            )
            return self._format_image_output(image_files)
        except HTTPError as e:
            return self._handle_http_error(e)
        except Exception as e:
            print(f"其他图片生成错误: {str(e)}")
            return None, None

    def _prepare_image_data(self, *image_inputs):
        """预处理图片数据"""
        image_data = []
        for img in image_inputs:
            if img:
                base64_str = generate_image_base64(img)
                cached_caption = self.cache.get_caption(base64_str)
                image_data.append((base64_str, cached_caption))
        return image_data

    def _print_cache_status(
        self,
        current_time,
        all_caption_cached,
        image_data,
        style_key,
        additional_text
    ):
        """打印缓存状态"""
        story_prompt_cached = False
        if all_caption_cached:
            caption_text = "|".join(caption for _, caption in image_data)
            story_prompt_cached = self.cache.get_story_prompt(
                caption_text,
                style_key,
                additional_text
            ) is not None

        print(
            f"\n[{current_time}] 生成图片 | "
            f"素材提示词缓存: {'启用' if all_caption_cached else '未启用'} | "
            f"最终提示词缓存: {'启用' if story_prompt_cached else '未启用'}"
        )

    def _process_captions(self, image_data):
        """处理图片描述"""
        captions = []
        for base64_str, cached_caption in image_data:
            if not cached_caption:
                new_caption = self.generate_caption_wrapped(base64_str)
                if new_caption:
                    self.cache.save_caption(base64_str, new_caption)
                    captions.append(new_caption)
            else:
                captions.append(cached_caption)
        return captions

    def _get_final_prompt(self, captions, style_key, additional_text):
        """获取最终提示词"""
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
        return final_prompt

    def _generate_final_images(self, final_prompt, output_prefix):
        """生成最终图片"""
        image_files = self.generate_image_fx_wrapped(
            prompt=final_prompt,
            output_prefix=output_prefix,
            image_number=IMAGE_NUMBER
        )
        return self._format_image_output(image_files)

    def _format_image_output(self, image_files):
        """格式化图片输出"""
        return (
            image_files[0] if image_files else None,
            image_files[1] if len(image_files) > 1 else None
        )

    def _handle_http_error(self, e):
        """统一处理HTTP错误"""
        error_info = {
            "status_code": e.response.status_code,
            "reason": e.response.reason,
            "url": e.response.url,
            "response_text": e.response.text[:200]
        }
        error_source = self._detect_error_source(e.response.url)
        result1, result2 = None, None
        if error_info['status_code'] == 401:
            print(f"[{error_source}] 自动续签认证失败，详细见飞书")
            gr.Warning("图片处理故障，已经通知管理员修复咯！")
            if FEISHU_ENABLED:
                FEISHU_CLIENT.send_message(
                    receive_id=FEISHU_RECEIVE_ID,
                    content={"text": "Whisk的Cookie已过期，请及时续签"},
                    msg_type="text"
                )
            auth_path = os.path.join(CACHE_DIR, "close_auth.png")
            result1, result2 = auth_path, auth_path
        elif error_info['status_code'] == 400:
            print(f"[{error_source}] 业务和谐，计划重试...")
            gr.Warning("图片生成失败，请换一张再试试")
            filter_path = os.path.join(CACHE_DIR, "close_filter.png")
            result1, result2 = filter_path, filter_path
        else:
            print(f"[{error_source}] 其他HTTP错误「{error_info['status_code']}」: "
                  f"{error_info['reason']} - TEXT: {error_info['response_text']}")

        return result1, result2

    def _detect_error_source(self, url):
        """优化后的错误来源检测（直观简洁版）"""
        return next(
            (v for k, v in ERROR_PATTERNS.items() if k in url),
            '未知来源'
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
    share_env = os.getenv("SHARE", "False")
    share_setting = share_env.lower() in ('true', 'yes', '1', 't', 'y')

    ssl_enabled = os.getenv("SSL_ENABLED", "False")
    ssl_setting = ssl_enabled.lower() in ('true', 'yes', '1', 't', 'y')
    if not ssl_setting:
        SERVER_PORT = CONFIG["server"]["port"]
        cert_file = None
        key_file = None
    else:
        SERVER_PORT = CONFIG["server"]["port"] if CONFIG["server"]["port"] not in [80, 443] else 443
        site_name = os.getenv("SITE_NAME", "Default_Whisk_Site")
        cert_file = os.path.join(current_dir, f"{site_name}.pem")
        if not os.path.exists(cert_file):
            # print(f"SSL证书文件 {cert_file} 不存在，使用非SSL模式")
            cert_file = None
            key_file = None
        else:
            key_file = os.path.join(current_dir, f"{site_name}.key")
            if not os.path.exists(key_file):
                # print(f"SSL密钥文件 {key_file} 不存在，使用非SSL模式")
                cert_file = None
                key_file = None
            # else:
            #     print(f"SSL证书文件 {cert_file} 和密钥文件 {key_file} 存在，使用SSL模式")
    demo.launch(
        server_name=CONFIG["server"]["name"],
        # server_name=site_name,
        # server_port=SERVER_PORT,      # 使用配置值
        ssl_certfile=cert_file,
        ssl_keyfile=key_file,
        share=share_setting,
        allowed_paths=[IMAGE_CACHE_DIR]
    )
