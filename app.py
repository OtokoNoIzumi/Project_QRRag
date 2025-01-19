# pylint: disable=no-member  # Project structure requires dynamic path handling
"""
For more information on `huggingface_hub` Inference API support
please check the docs: https://huggingface.co/docs/huggingface_hub/v0.22.2/en/guides/inference
"""
import os
import sys
import gradio as gr
import cv2
from pyzbar.pyzbar import decode
import numpy as np
from google import genai
from google.genai import types
from dotenv import load_dotenv

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

with open(
    os.path.join(current_dir, "system_role_prompt.md"), "r", encoding="utf-8"
) as f:
    system_role = f.read()


BEGIN_PROMPT = """
总结一下最新的内容
"""


CONFIRM_PROMPT = """
对比一下两个版本的差异
"""

load_dotenv(dotenv_path=os.path.join(current_dir, ".env"))  # current_dir + "\.env")
api_key = os.getenv("GEMINI_API_KEY")
gemini_client = None
if api_key:
    gemini_client = genai.Client(api_key=api_key)

MODEL_NAME = "gemini-2.0-flash-exp"


# Common safety settings for all requests
def get_safety_settings():
    return [
        types.SafetySetting(category="HARM_CATEGORY_HATE_SPEECH", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_DANGEROUS_CONTENT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_HARASSMENT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_SEXUALLY_EXPLICIT", threshold="OFF"),
        types.SafetySetting(category="HARM_CATEGORY_CIVIC_INTEGRITY", threshold="OFF")
    ]


def format_content(role: str, text: str) -> types.Content:
    """格式化单条消息内容"""
    return types.Content(
        role=role,
        parts=[types.Part(text=text)]
    )


def respond(
    message,
    history: list[tuple[str, str]],
    use_system_message,
):
    # 构建对话历史
    def build_contents(message=None, before_message=None):
        contents = []
        for val in history:
            if val["content"] == "开始":
                context = BEGIN_PROMPT
            elif val["content"] == "确认":
                context = CONFIRM_PROMPT
            else:
                context = val["content"]
            contents.append(format_content(
                val["role"],
                context
            ))

        if before_message:
            contents.append(format_content(
                "assistant",
                before_message
            ))

        if message:
            contents.append(format_content(
                "user",
                message
            ))
        return contents
    if message == "开始" and not history:
        message = BEGIN_PROMPT

    if message == "确认" and len(history) == 2:
        message = CONFIRM_PROMPT

    if message:
        # 处理普通消息
        contents = build_contents(message)
        response = ""
        if use_system_message:
            config = types.GenerateContentConfig(
                system_instruction=system_role,
                safety_settings=get_safety_settings(),
            )
        else:
            config = types.GenerateContentConfig(
                safety_settings=get_safety_settings(),
            )
        for chunk in gemini_client.models.generate_content_stream(
            model=MODEL_NAME,
            contents=contents,
            config=config
        ):
            if chunk.text:  # Check if chunk.text is not None
                response += chunk.text
                yield response


def get_gradio_version():
    return gr.__version__


game_state = {"gr_version": get_gradio_version()}  # 示例 game_state


def process_qr_frame(frame):
    """处理视频帧，检测和解码二维码"""
    if frame is None:
        return frame, game_state

    # 转换图像格式确保兼容性
    if isinstance(frame, np.ndarray):
        img = frame.copy()
    else:
        img = np.array(frame).copy()

    # 检测二维码
    decoded_objects = decode(img)

    if decoded_objects:
        # 获取二维码数据
        qr_data = decoded_objects[0].data.decode('utf-8')

        # 解析二维码数据
        qr_info = {"设定": qr_data}

        game_state.update(qr_info)

        # 在图像上绘制识别框和状态
        points = decoded_objects[0].polygon
        if points:
            # 绘制绿色边框表示成功识别
            pts = np.array(points, np.int32)
            pts = pts.reshape((-1, 1, 2))
            cv2.polylines(img, [pts], True, (0, 255, 0), 2)

            # 添加文本显示已更新
            cv2.putText(img, "QR Code Updated!", (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

    return img, game_state


def export_chat(history):
    export_string = ""
    for item in history:
        user_msg = item[0]['content']
        bot_msg = item[1]
        export_string += f"User: {user_msg}\nBot: {bot_msg}\n\n"
    return export_string


def get_chat_history(chatbot_component):
    return chatbot_component.load_history()


with gr.Blocks(theme="soft") as demo:
    if gemini_client:
        chatbot = gr.ChatInterface(
            respond,
            title="知识助理",
            type="messages",
            additional_inputs=[
                gr.Checkbox(value=False, label="Use system message"),
            ],

        )
    else:
        gr.Markdown("Gemini API key not found. Please check your .env file.")

    with gr.Accordion("查看状态", open=False):
        game_info_image = gr.Image(label="二维码设定",
                                   webcam_constraints={
                                        "video": {
                                            "facingMode": {"ideal": "environment"}
                                        }
                                    })
        output_img = gr.Image(label="识别结果")
        game_state_output = gr.JSON(value=game_state)  # 初始显示 game_state

        # 设置实时流处理
        game_info_image.upload(
            fn=process_qr_frame,
            inputs=[game_info_image],
            outputs=[output_img, game_state_output],
            show_progress=False,
        )
        # 设置实时流处理
        game_info_image.stream(
            fn=process_qr_frame,
            inputs=[game_info_image],
            outputs=[output_img, game_state_output],
            show_progress=False,
            stream_every=0.5  # 每0.5秒处理一次
        )

if __name__ == "__main__":
    cert_file = os.path.join(current_dir, "localhost+1.pem")
    key_file = os.path.join(current_dir, "localhost+1-key.pem")

    if os.path.exists(cert_file) and os.path.exists(key_file):
        demo.launch(
            server_name="0.0.0.0",
            ssl_certfile=cert_file,
            ssl_keyfile=key_file
        )
    else:
        demo.launch(server_name="0.0.0.0")
