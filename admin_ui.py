"""
管理员界面模块
"""
import os
import gradio as gr
from Module.core.admin_service import AdminService
from Module.core.utils import load_config
import json
from typing import Tuple, List
# 加载配置
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")
with open(CONFIG_PATH, 'r', encoding='utf-8') as config_file:
    CONFIG = json.load(config_file)

# 加载哪吒项目配置
NEZHA_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "Module", "style", "nezha", "config.json")
with open(NEZHA_CONFIG_PATH, 'r', encoding='utf-8') as config_file:
    NEZHA_CONFIG = json.load(config_file)

# 设置存储路径
STORAGE_DIR = os.path.join(os.path.dirname(__file__), "Module", "style", "nezha", "storage")
TOKENS_FILE = os.path.join(STORAGE_DIR, NEZHA_CONFIG.get("storage", {}).get("tokens_file", "tokens.json"))

# 初始化管理员服务
admin_service = AdminService(STORAGE_DIR, TOKENS_FILE)

def generate_tokens_and_posters(
    count: int,
    theme: str,
    prefix: str,
    max_usage_count: int,
    usage_valid_days: int,
    access_valid_days: int,
    template_file: str,
    sequence_prefix: str,
    start_number: int
) -> Tuple[str, List[str], List[str]]:
    """
    生成令牌和海报

    Args:
        count: 生成数量
        theme: 主题
        prefix: 令牌前缀
        max_usage_count: 最大使用次数
        usage_valid_days: 使用有效期天数
        access_valid_days: 访问有效期天数
        template_file: 海报模板文件
        sequence_prefix: 序列号前缀
        start_number: 起始序列号

    Returns:
        元组: (状态消息, 二维码文件列表, 海报文件列表)
    """
    try:
        # 生成令牌
        tokens = admin_service.generate_tokens(
            count=count,
            theme=theme,
            prefix=prefix,
            max_usage_count=max_usage_count,
            usage_valid_days=usage_valid_days,
            access_valid_days=access_valid_days
        )

        # 保存令牌
        if not admin_service.save_tokens(tokens):
            return "保存令牌失败", [], []

        # 生成二维码
        qr_files = admin_service.generate_qr_codes(tokens)

        # 生成海报
        poster_files = admin_service.generate_posters(
            qr_files=qr_files,
            template_file=template_file,
            sequence_prefix=sequence_prefix,
            start_number=start_number
        )

        return "生成成功!", qr_files, poster_files
    except Exception as e:
        return f"生成失败: {str(e)}", [], []

# 创建管理员界面
with gr.Blocks(title="哪吒形象生成系统 - 管理员界面") as admin_demo:
    gr.Markdown("# 哪吒形象生成系统 - 管理员界面")

    with gr.Tab("批量生成令牌"):
        with gr.Row():
            with gr.Column():
                count = gr.Slider(
                    minimum=1,
                    maximum=100,
                    value=10,
                    step=1,
                    label="生成数量"
                )
                theme = gr.Dropdown(
                    choices=["ice", "fire"],
                    value="ice",
                    label="主题"
                )
                prefix = gr.Textbox(
                    label="令牌前缀",
                    placeholder="可选"
                )
                max_usage_count = gr.Slider(
                    minimum=1,
                    maximum=100,
                    value=10,
                    step=1,
                    label="最大使用次数"
                )
                usage_valid_days = gr.Slider(
                    minimum=1,
                    maximum=30,
                    value=2,
                    step=1,
                    label="使用有效期(天)"
                )
                access_valid_days = gr.Slider(
                    minimum=1,
                    maximum=30,
                    value=9,
                    step=1,
                    label="访问有效期(天)"
                )
            with gr.Column():
                template_file = gr.File(
                    label="海报模板",
                    file_types=["image"]
                )
                sequence_prefix = gr.Textbox(
                    label="序列号前缀",
                    value="No.",
                    placeholder="例如: No."
                )
                start_number = gr.Number(
                    label="起始序列号",
                    value=1,
                    precision=0,
                    minimum=1
                )

        generate_btn = gr.Button("生成令牌和海报")
        status_message = gr.Markdown("")

        with gr.Row():
            with gr.Column():
                gr.Markdown("### 生成的二维码")
                qr_gallery = gr.Gallery(
                    label="二维码",
                    show_label=True,
                    elem_id="qr_gallery",
                    columns=4,
                    rows=5,
                    height=400
                )
            with gr.Column():
                gr.Markdown("### 生成的海报")
                poster_gallery = gr.Gallery(
                    label="海报",
                    show_label=True,
                    elem_id="poster_gallery",
                    columns=4,
                    rows=5,
                    height=400
                )

    # 设置生成按钮事件
    generate_btn.click(
        fn=generate_tokens_and_posters,
        inputs=[
            count, theme, prefix, max_usage_count,
            usage_valid_days, access_valid_days,
            template_file, sequence_prefix, start_number
        ],
        outputs=[status_message, qr_gallery, poster_gallery]
    )

if __name__ == "__main__":
    admin_demo.launch(
        server_name=CONFIG["name"],
        server_port=CONFIG["port"] + 1,  # 使用不同的端口
        share=False
    )