#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
哪吒形象生成系统 - 主入口
"""
import os
import sys
import json
import time
from typing import Dict, Optional, Tuple, List
import re
import gradio as gr

# ===== 1. 获取项目路径 =====
if "__file__" in globals():
    current_dir = os.path.dirname(os.path.abspath(__file__))
else:
    current_dir = os.getcwd()

root_dir = current_dir
sys.path.append(root_dir)

# ===== 2. 导入必要模块 =====
from Module.core.auth_service import AuthService
from Module.core.image_service import ImageService, calculate_image_hash
from Module.core.utils import (
    extract_token_from_url,
    format_time_remaining,
    create_sample_tokens_file,
    get_css_for_theme
)
# 导入原始的WhiskService
from Module.Common.scripts.llm.utils.google_whisk import (
    DEFAULT_STYLE_PROMPT_DICT,
)
from app_image import WhiskService

# ===== 3. 初始化配置 =====
# 加载配置
CONFIG_PATH = os.path.join(current_dir, "config.json")
with open(CONFIG_PATH, 'r', encoding='utf-8') as config_file:
    CONFIG = json.load(config_file)

# 加载哪吒项目配置
STYLE_PATH = os.path.join(root_dir, "Module", "style")
NEZHA_CONFIG_PATH = os.path.join(STYLE_PATH, "nezha", "config.json")
with open(NEZHA_CONFIG_PATH, 'r', encoding='utf-8') as config_file:
    NEZHA_CONFIG = json.load(config_file)

# 使用主配置覆盖特定项目配置
CONFIG.update(NEZHA_CONFIG.get("server", {}))

# 设置缓存和存储路径
CACHE_DIR = os.path.join(current_dir, CONFIG["cache"]["dir"])
IMAGE_CACHE_DIR = os.path.join(CACHE_DIR, CONFIG["cache"]["image_dir"])
STORAGE_DIR = os.path.join(STYLE_PATH, "nezha", "storage")
TOKENS_FILE = os.path.join(STORAGE_DIR, NEZHA_CONFIG.get("storage", {}).get("tokens_file", "tokens.json"))

# 确保目录存在
os.makedirs(CACHE_DIR, exist_ok=True)
os.makedirs(IMAGE_CACHE_DIR, exist_ok=True)
os.makedirs(STORAGE_DIR, exist_ok=True)

# 如果令牌文件不存在，创建样例文件
if not os.path.exists(TOKENS_FILE):
    create_sample_tokens_file(TOKENS_FILE, num_tokens=5)
    print(f"已创建样例令牌文件: {TOKENS_FILE}")

# ===== 4. 初始化服务 =====
# 初始化Whisk服务
whisk_service = WhiskService()

# 初始化认证服务
auth_service = AuthService(TOKENS_FILE, NEZHA_CONFIG_PATH)

# 初始化图像服务
image_service = ImageService(whisk_service, STORAGE_DIR, NEZHA_CONFIG)


# 添加一个函数用于重新加载tokens
def reload_tokens():
    """
    重新加载tokens配置

    在每次需要验证token时调用，确保使用最新的token数据
    """
    global auth_service
    if os.path.exists(TOKENS_FILE):
        # 比较文件修改时间
        last_modified = os.path.getmtime(TOKENS_FILE)
        if not hasattr(auth_service, 'last_token_load') or last_modified > auth_service.last_token_load:
            print(f"发现tokens文件已更新，重新加载: {TOKENS_FILE}")
            # 重新初始化认证服务
            auth_service = AuthService(TOKENS_FILE, NEZHA_CONFIG_PATH)
            auth_service.last_token_load = last_modified
            return True
    return False


# ===== 5. 定义处理函数 =====
def validate_url_token(request: gr.Request) -> Tuple[bool, Optional[str], Optional[Dict]]:
    """
    验证请求中的令牌

    Args:
        request: Gradio 请求对象

    Returns:
        元组: (是否有效, 错误消息, 令牌数据)
    """
    # 重新加载tokens配置
    reload_tokens()

    token_id = None

    try:
        # 从请求参数中提取token
        query_params = dict(request.query_params)
        print(f"DEBUG - 查询参数: {query_params}")

        if 'token' in query_params:
            token_id = query_params['token']
            print(f"DEBUG - 找到token参数: {token_id}")
        else:
            # 尝试从路径中提取
            path_parts = request.url.path.strip('/').split('/')
            if len(path_parts) > 0 and re.match(r'^[a-zA-Z0-9_-]+$', path_parts[-1]):
                token_id = path_parts[-1]
                print(f"DEBUG - 从路径提取token: {token_id}")
            else:
                # 尝试使用工具函数从URL中提取
                token_id = extract_token_from_url(str(request.url))
                if token_id:
                    print(f"DEBUG - 使用工具函数提取token: {token_id}")
                else:
                    print("DEBUG - 未找到token")
                    return False, "无效的专属通行证，请使用正确的链接访问，或扫描专属通行证二维码", None
    except Exception as e:
        print(f"DEBUG - 参数解析错误: {str(e)}")
        return False, f"无效的专属通行证，请使用正确的链接访问，或扫描专属通行证二维码", None

    if not token_id:
        return False, "无效的专属通行证，请使用正确的链接访问，或扫描专属通行证二维码", None

    is_valid, error_msg, token = auth_service.validate_token(token_id)
    if not is_valid:
        return False, error_msg, None

    return True, None, auth_service.get_token_data(token_id)


def process_image_request(
    image,
    style_key: str,
    token_id: str
) -> Tuple[Optional[str], Optional[str], str]:
    """
    处理图像生成请求

    Args:
        image: 上传的图像
        style_key: 选择的风格
        token_id: 令牌ID

    Returns:
        元组: (输出图像1, 输出图像2, 状态消息)
    """
    print(f"DEBUG - 处理图像请求: token={token_id}, style={style_key}")
    if not token_id:
        return None, None, "无效的专属通行证"

    if not image:
        return None, None, "请先上传图片，再开始创作"

    # 检查令牌是否可以生成图片
    can_generate, error_msg, token = auth_service.can_generate_image(token_id)
    if not can_generate:
        return None, None, f"无法创作图片: {error_msg}"

    # 计算图像哈希
    image_hash = calculate_image_hash(image)

    # 检查令牌图像使用状态
    is_valid, error_msg = auth_service.validate_image_hash(token_id, image_hash)
    if not is_valid:
        return None, None, error_msg

    # 处理图像生成
    output_image1, output_image2, process_data = image_service.process_image(
        image_path=image,
        token_id=token_id,
        theme=token.theme,
        style_key=style_key,
    )

    # 检查是否成功
    if not process_data.get("success", False):
        return None, None, f"生成失败: {process_data.get('error_message', '未知错误')}"

    # 确保输出图像是字符串路径
    output_paths = []
    # 保存的问题要看看，应该有
    for img in [output_image1, output_image2]:
        if img is not None:
            if hasattr(img, 'filename') and img.filename:
                output_paths.append(img.filename)
            elif isinstance(img, str):
                output_paths.append(img)
            else:
                output_paths.append(None)
        else:
            output_paths.append(None)

    # 记录使用
    auth_service.record_image_usage(
        token_id=token_id,
        image_hash=image_hash,
        style=style_key,
        output_images=[p for p in output_paths if p is not None]
    )

    return output_image1, output_image2, "创作成功!"


def get_available_styles_for_token(token_id: str, theme: str) -> List[Dict]:
    """
    获取令牌可用的风格列表

    Args:
        token_id: 令牌ID
        theme: 主题

    Returns:
        风格选项列表
    """
    # 重新加载tokens配置
    reload_tokens()

    # 获取主题的风格列表
    theme_config = NEZHA_CONFIG.get("themes", {}).get(theme, {})
    style_prompts = theme_config.get("style_prompts", {})

    if not style_prompts:
        # 如果没有找到风格配置，使用默认风格
        all_styles = list(DEFAULT_STYLE_PROMPT_DICT.keys())
    else:
        all_styles = list(style_prompts.keys())

    # 获取令牌可用的风格
    style_status = auth_service.get_available_styles(token_id, all_styles)

    # 获取令牌对象以检查是否可以使用更多风格
    valid, _, token = auth_service.validate_token(token_id)
    can_use_more = valid and token and token.can_use_more_styles

    # 检查已使用的风格数量
    used_styles_count = 0
    if valid and token:
        used_styles_count = len(token.used_styles)

    # 构造风格选项列表
    style_options = []
    for style in all_styles:
        status = style_status.get(style)
        # True: 已使用, None: 可用但未使用, False: 不可用
        label = style
        disabled = False

        if status is True:
            if can_use_more:
                label = f"{style} (已使用)"
            else:
                label = f"{style} (可使用)"
        elif status is False or not can_use_more:
            label = f"{style} (不可用)"
            disabled = True

        # 如果超过了使用限制(3种风格)，禁用选项
        if used_styles_count >= 3 and status is not True:
            disabled = True
            label = f"{style} (已达风格限制)"

        style_options.append({
            "value": style,
            "label": label,
            "disabled": disabled
        })

    return style_options


def get_token_stats(token_id: str) -> Dict:
    """
    获取令牌统计信息

    Args:
        token_id: 令牌ID

    Returns:
        令牌统计
    """
    # 重新加载tokens配置
    reload_tokens()

    token_data = auth_service.get_token_data(token_id)
    if not token_data:
        return {
            "usage_count": 0,
            "max_usage_count": 0,
            "usage_remaining": "0",
            "access_valid": False,
            "usage_valid": False,
            "usage_valid_until": "已过期",
            "access_valid_until": "已过期"
        }

    _, _, token = auth_service.validate_token(token_id)
    if token is None:
        return {
            "usage_count": 0,
            "max_usage_count": 0,
            "usage_remaining": "0",
            "access_valid": False,
            "usage_valid": False,
            "usage_valid_until": "已过期",
            "access_valid_until": "已过期"
        }

    return {
        "usage_count": token_data.get("usage_count", 0),
        "max_usage_count": token_data.get("max_usage_count", 0),
        "usage_remaining": str(max(0, token_data.get("max_usage_count", 0) - token_data.get("usage_count", 0))),
        "access_valid": token_data.get("is_access_valid", False),
        "usage_valid": token_data.get("is_usage_valid", False),
        "usage_valid_until": format_time_remaining(token.usage_valid_until),
        "access_valid_until": format_time_remaining(token.access_valid_until)
    }


def map_style_label_to_key(style_label: str) -> str:
    """
    将样式标签映射到实际的键名

    Args:
        style_label: 样式标签

    Returns:
        样式键名
    """
    # 移除状态后缀
    for suffix in [" (已使用)", " (不可用)", " (可使用)", " (已达风格限制)"]:
        if style_label.endswith(suffix):
            return style_label[:-len(suffix)]
    return style_label


def handle_upload_image(
    image,
    style_label: str,
    token_id: str
) -> Tuple[Optional[str], Optional[str], str, bool]:
    """
    处理上传图像

    Args:
        image: 上传的图像
        style_label: 样式标签
        token_id: 令牌ID

    Returns:
        元组: (输出图像1, 输出图像2, 状态消息, 是否显示风格选择)
    """
    # 重新加载tokens配置
    reload_tokens()

    print(f"DEBUG - 上传图像: style_label={style_label}, token_id={token_id}")

    if not image:
        return None, None, "请先上传照片，再开始创作", False

    if not token_id or token_id.strip() == "":
        return None, None, "无效的专属通行证", False

    # 获取令牌信息
    _, _, token = auth_service.validate_token(token_id)
    if token is None:
        return None, None, "无效的专属通行证", False

    # 计算图像哈希检查令牌是否已使用过其他图片
    image_hash = calculate_image_hash(image)
    is_valid, error_msg = auth_service.validate_image_hash(token_id, image_hash)
    if not is_valid:
        return None, None, error_msg, False

    theme = token.theme
    theme_config = NEZHA_CONFIG.get("themes", {}).get(theme, {})

    # 将标签映射到实际的风格键名
    style_key = ""
    if style_label and style_label.strip():
        style_key = map_style_label_to_key(style_label)

        # 验证风格是否可用
        if style_key not in token.used_styles and not token.can_use_more_styles:
            return None, None, "您已达到风格创作上限，最多可创作3种不同风格", True
    else:
        # 如果没有选择风格或风格为空，使用默认风格
        default_style = theme_config.get("default_style", "")
        if not default_style:
            # 如果没有默认风格，使用第一个可用风格
            style_prompts = theme_config.get("style_prompts", {})
            if style_prompts:
                style_key = list(style_prompts.keys())[0]
            else:
                return None, None, "未找到可用的创作风格", False
        else:
            style_key = default_style
        print(f"DEBUG - 使用默认风格: {style_key}")

    # 处理图像生成请求
    output_image1, output_image2, status_msg = process_image_request(
        image=image,
        style_key=style_key,
        token_id=token_id
    )

    # 如果成功生成，则显示风格选择
    show_style = status_msg == "创作成功!" and len(token.used_image_hashes) > 0
    # 缓存用户上传的图片
    if (output_image1 or output_image2):
        upload_dir = os.path.join(STORAGE_DIR, "results", token_id)
        upload_path = os.path.join(upload_dir, "upload.png")

        # 如果已经缓存过，则不再重复缓存
        if not os.path.exists(upload_path):
            os.makedirs(upload_dir, exist_ok=True)
            # 如果是路径，直接复制
            if isinstance(image, str) and os.path.exists(image):
                import shutil
                shutil.copy(image, upload_path)
            # 如果是PIL图像，保存
            elif hasattr(image, 'save'):
                image.save(upload_path)

    return output_image1, output_image2, status_msg, show_style

def get_token_history(token_id: str) -> List[Dict]:
    """
    获取令牌的历史记录

    Args:
        token_id: 令牌ID

    Returns:
        历史记录列表
    """
    # 重新加载tokens配置
    reload_tokens()

    valid, _, token = auth_service.validate_token(token_id)
    if not valid or token is None:
        return []

    history = []
    for record in token.generation_records:
        if record.get("output_files"):
            for file_path in record["output_files"]:
                if os.path.exists(file_path):
                    history.append((file_path, f"风格: {record['style']}"))

    # 确保返回的列表符合Gallery要求的格式，并按倒序排列
    if not history:
        return []
    return history[::-1]


# ===== 6. 创建Gradio界面 =====
with gr.Blocks(analytics_enabled=False) as demo:
    # 页面状态
    page_state = gr.State({"view": "login"})
    token_id = gr.State("")

    # 设置CSS样式
    css = gr.HTML(get_css_for_theme("default"))
    # 登录界面
    with gr.Column(visible=True) as login_container:
        gr.Markdown(f"# {NEZHA_CONFIG.get('project_settings', {}).get('name', '传奇神话形象定制')}")
        gr.Markdown("请扫描专属通行证二维码开始创作。")
        gr.Image(
            value="welcome.webp",
            width="100%",
            show_download_button=False,
            show_fullscreen_button=False
        )
        error_message = gr.Markdown("")
    # 主界面
    with gr.Column(visible=False) as main_container:
        with gr.Row():
            heading = gr.Markdown("# 哪吒形象生成")
            theme_logo = gr.Image(
                label="",
                visible=False,
                width=42,
                height=42,
                show_label=False,
                show_download_button=False,
                show_fullscreen_button=False
            )
        subheading = gr.Markdown("上传一张照片，生成你的专属形象")

        # 添加使用说明
        usage_instruction = gr.Markdown("""
        ### 使用说明
        - 每个专属通行证只能用于**一张**照片
        - 对同一张照片，您可以尝试不同的风格（最多3种）
        - 请务必选择您最喜欢的照片，因为一旦使用就不能更换
        """, visible=True)

        with gr.Row():
            with gr.Column(scale=1):
                # 左侧面板 - 上传和控制
                upload_image = gr.Image(
                    label="上传您的照片",
                    type="filepath",
                    height=300
                )
                # 风格选择器（初始隐藏）
                style_dropdown = gr.Dropdown(
                    label="选择创作风格",
                    choices=[],
                    visible=False
                )
                with gr.Row():
                    usage_info = gr.Markdown("剩余使用次数: 0/0")
                    valid_until = gr.Markdown("有效期至: 未知")

                generate_status = gr.Markdown("请上传图片")
                upload_btn = gr.Button("开始创作")

            with gr.Column(scale=2):
                # 右侧面板 - 显示结果
                with gr.Row():
                    output_image1 = gr.Image(
                        label="创作结果 1",
                        height=300,
                        interactive=False
                    )
                    output_image2 = gr.Image(
                        label="创作结果 2",
                        height=300,
                        interactive=False
                    )

                result_message = gr.Markdown("")

                # 添加历史图片展示
                gr.Markdown("### 您的创作历史")
                history_gallery = gr.Gallery(
                    label="历史作品",
                    show_label=False,
                    elem_id="history_gallery",
                    columns=2,
                    # rows=3,
                    # height=400,
                    show_download_button=True
                )

    # 过期界面
    with gr.Column(visible=False) as expired_container:
        gr.Markdown("# 访问已过期")
        expired_message = gr.Markdown("您的访问令牌已过期，感谢您的使用")

    def load_interface(request: gr.Request = None):
        """页面加载时的处理函数"""
        # 重新加载tokens配置
        reload_tokens()

        if request is None:
            return {
                "view": "login",
                "error": "请扫描二维码或使用有效链接访问",
                "token": ""
            }

        try:
            print(f"DEBUG - 获取到请求: {request}")
            print(f"DEBUG - 请求URL: {request.url}")
            print(f"DEBUG - 请求参数: {dict(request.query_params)}")
        except Exception as e:
            print(f"DEBUG - 请求解析错误: {str(e)}")
            return {
                "view": "login",
                "error": f"请求参数解析错误: {str(e)}",
                "token": ""
            }

        # 验证令牌
        is_valid, error_msg, token_data = validate_url_token(request)
        if not is_valid:
            return {
                "view": "login",
                "error": error_msg or "",
                "token": ""
            }

        # 获取token_id
        current_token = ""
        try:
            query_params = dict(request.query_params)
            if 'token' in query_params:
                current_token = query_params['token']
        except:
            current_token = extract_token_from_url(str(request.url))

        # 检查令牌是否可用
        stats = get_token_stats(current_token)

        if not stats["access_valid"]:
            return {"view": "expired", "error": "", "token": current_token}

        return {"view": "main", "error": "", "token": current_token}

    def update_ui(state):
        """根据页面状态更新UI"""
        view = state["view"]
        error = state.get("error", "")
        current_token = state.get("token", "")

        if view == "login":
            return {
                login_container: gr.update(visible=True),
                main_container: gr.update(visible=False),
                expired_container: gr.update(visible=False),
                error_message: error,
                css: get_css_for_theme("default")
            }

        elif view == "expired":
            theme = "default"
            if current_token:
                _, _, token = auth_service.validate_token(current_token)
                if token:
                    theme = token.theme

            return {
                login_container: gr.update(visible=False),
                main_container: gr.update(visible=False),
                expired_container: gr.update(visible=True),
                expired_message: "您的专属通行证已过期，感谢您的使用",
                css: get_css_for_theme(theme)
            }

        elif view == "main":
            if not current_token:
                return update_ui({"view": "login", "error": "无效的二维码"})

            _, _, token = auth_service.validate_token(current_token)
            if token is None:
                return update_ui({"view": "login", "error": "无效的二维码"})

            theme = token.theme
            stats = get_token_stats(current_token)
            style_options = get_available_styles_for_token(current_token, theme)
            history_images = get_token_history(current_token)
            can_generate = stats["usage_valid"]
            generate_message = (
                "可以开始创作" if can_generate else
                f"创作功能已过期 ({stats['usage_valid_until']})"
            )

            instruction_text = """
            ### 使用说明
            - 每个二维码只能用于**一张**照片
            - 对同一张照片，您可以尝试不同的风格（最多3种）
            - 请务必选择您最喜欢的照片，因为一旦使用就不能更换
            """

            if len(token.used_image_hashes) > 0:
                used_styles_str = "、".join(token.used_styles)
                remaining_styles = 3 - len(token.used_styles)

                instruction_text = f"""
                ### 使用说明
                - 您已经使用此二维码上传了一张照片
                - 已创作的风格: {used_styles_str}
                - 剩余可用风格数: {remaining_styles}种
                - 请继续使用相同的照片，**不能更换其他照片**
                """

            # 判断是否显示风格选择
            show_style_dropdown = len(token.used_image_hashes) > 0

            # 获取主题logo
            # 获取主题logo路径，需要从STYLE_PATH的nezha目录下获取
            theme_logo_path = os.path.join(STYLE_PATH, 'nezha', NEZHA_CONFIG.get('themes', {}).get(theme, {}).get('ui', {}).get('logo', ''))
            print(f"DEBUG - 主题logo路径: {theme_logo_path}")
            theme_logo_url = theme_logo_path if os.path.exists(theme_logo_path) else ''
            show_theme_logo = bool(theme_logo_url)

            return {
                login_container: gr.update(visible=False),
                main_container: gr.update(visible=True),
                expired_container: gr.update(visible=False),
                heading: f"# 与{NEZHA_CONFIG.get('themes', {}).get(theme, {}).get('name', theme)}合影吧~",
                theme_logo: gr.update(value=theme_logo_url, visible=show_theme_logo),
                subheading: f" 场景: {NEZHA_CONFIG.get('themes', {}).get(theme, {}).get('description', '')}",
                usage_instruction: instruction_text,
                style_dropdown: gr.update(choices=[option["label"] for option in style_options], visible=show_style_dropdown),
                usage_info: f"使用次数: {stats['usage_count']}/{stats['max_usage_count']} · 剩余: {stats['usage_remaining']}次",
                valid_until: f"有效期至: {stats['access_valid_until']}",
                generate_status: generate_message,
                upload_btn: gr.update(interactive=can_generate),
                history_gallery: history_images,
                css: get_css_for_theme(theme)
            }

        return update_ui({"view": "login", "error": "未知状态"})

    # 页面加载事件
    demo.load(
        fn=load_interface,
        inputs=None,
        outputs=page_state
    )

    # 页面状态变化事件
    page_state.change(
        fn=update_ui,
        inputs=page_state,
        outputs=[
            login_container, main_container, expired_container,
            error_message, heading, theme_logo, subheading, usage_instruction, style_dropdown,
            usage_info, valid_until, generate_status, upload_btn,
            expired_message, history_gallery, css
        ]
    )

    # 设置生成按钮事件
    def handle_image_with_state(image, style_label, state):
        """
        处理图片生成并更新UI状态
        """
        token_id = state.get("token", "")
        output_image1, output_image2, status_msg, show_style = handle_upload_image(image, style_label, token_id)
        # 获取更新后的历史图片
        history_images = get_token_history(token_id)

        # 更新页面状态以触发UI刷新
        updated_state = state.copy()
        updated_state["updated"] = time.time()  # 添加更新时间戳触发更新

        # 返回结果并更新UI
        return (
            output_image1,
            output_image2,
            status_msg,
            gr.update(visible=show_style),
            history_images,
            updated_state
        )

    upload_btn.click(
        fn=handle_image_with_state,
        inputs=[upload_image, style_dropdown, page_state],
        outputs=[output_image1, output_image2, result_message, style_dropdown, history_gallery, page_state]
    )

# ===== 7. 启动应用 =====
if __name__ == "__main__":
    # 获取环境变量
    share_env = os.getenv("SHARE", "False")
    share_setting = share_env.lower() in ('true', 'yes', '1', 't', 'y')
    print(f"分享设置 (从环境变量): {share_setting}")

    # 启动前的准备
    print(f"\n===== 传奇神话形象定制系统 v{NEZHA_CONFIG.get('project_settings', {}).get('version', '1.0.0')} =====")
    print("配置信息:")
    print(f"  - 服务地址: {CONFIG['name']}:{CONFIG['port']}")
    print(f"  - 缓存目录: {CACHE_DIR}")
    print(f"  - 存储目录: {STORAGE_DIR}")
    print(f"  - 主题数量: {len(NEZHA_CONFIG.get('themes', {}))} 个")
    print(f"  - 通行证文件: {TOKENS_FILE}")
    print(f"  - 分享模式: {'启用' if share_setting else '禁用'}")

    # 启动应用
    try:
        print(f"\n启动应用: http://{CONFIG['name']}:{CONFIG['port']}")
        print("如果需要启用分享模式，请设置环境变量 SHARE=True 后重新启动")
        print("如果分享链接生成失败，请运行 diagnose_gradio.py 来诊断问题")

        # 强制设置分享选项，确保正确应用
        if share_setting:
            print("正在尝试生成分享链接...")
            os.environ["GRADIO_SHARE"] = "true"

        # 启动Gradio应用
        demo.launch(
            server_name=CONFIG["name"],
            server_port=CONFIG["port"],
            ssl_verify=CONFIG.get("ssl_verify", False),
            share=share_setting,
            allowed_paths=[IMAGE_CACHE_DIR, STORAGE_DIR, CACHE_DIR, STYLE_PATH],
            show_error=True
        )
    except Exception as e:
        print(f"启动失败: {str(e)}")
        import traceback
        traceback.print_exc()
