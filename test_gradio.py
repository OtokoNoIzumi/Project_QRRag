#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Gradio 5.x 基本功能测试文件
"""
import gradio as gr

def handle_request(request: gr.Request):
    """处理请求并返回请求信息"""
    if request is None:
        return "请求为空"

    try:
        # 获取 URL 字符串
        url_str = str(request.url)
        info = f"请求URL: {url_str}\n"
        info += f"请求方法: {request.method}\n"
        info += f"请求客户端: {request.client.host}\n"

        # 使用 query_params 获取查询参数
        query_params = dict(request.query_params)
        if query_params:
            info += f"查询参数: {query_params}\n"
        else:
            info += "查询参数: 无\n"

        return info
    except Exception as e:
        return f"解析请求时出错: {str(e)}"

with gr.Blocks() as demo:
    gr.Markdown("# Gradio 请求测试")
    result = gr.Textbox(label="请求信息", lines=10)

    # 页面加载时调用，自动传递请求对象
    demo.load(
        fn=handle_request,
        inputs=None,  # 明确无用户输入
        outputs=[result]  # 明确输出到 result
    )

    # 添加刷新按钮，同样自动传递请求对象
    refresh_btn = gr.Button("刷新请求信息")
    refresh_btn.click(
        fn=handle_request,
        inputs=None,  # 明确无用户输入
        outputs=[result]  # 明确输出到 result
    )

if __name__ == "__main__":
    demo.launch(share=True)  # 设置 share=True 以创建公共链接