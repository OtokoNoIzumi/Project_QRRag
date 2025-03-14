#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
令牌生成工具 - 简化版管理员功能
"""
import os
import sys
import json
import time
import qrcode
import argparse
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont

# 获取项目路径
if "__file__" in globals():
    current_dir = os.path.dirname(os.path.abspath(__file__))
else:
    current_dir = os.getcwd()

root_dir = current_dir
sys.path.append(root_dir)

# 导入模块
from Module.core.admin_service import AdminService

# 加载配置
CONFIG_PATH = os.path.join(current_dir, "config.json")
with open(CONFIG_PATH, 'r', encoding='utf-8') as config_file:
    CONFIG = json.load(config_file)

# 加载哪吒项目配置
NEZHA_CONFIG_PATH = os.path.join(root_dir, "Module", "style", "nezha", "config.json")
with open(NEZHA_CONFIG_PATH, 'r', encoding='utf-8') as config_file:
    NEZHA_CONFIG = json.load(config_file)

# 设置存储路径
STORAGE_DIR = os.path.join(root_dir, "Module", "style", "nezha", "storage")
TOKENS_FILE = os.path.join(STORAGE_DIR, NEZHA_CONFIG.get("storage", {}).get("tokens_file", "tokens.json"))

# 确保目录存在
os.makedirs(STORAGE_DIR, exist_ok=True)

# 初始化管理员服务
admin_service = AdminService(STORAGE_DIR, TOKENS_FILE)

def generate_tokens(args):
    """生成令牌和二维码"""
    print(f"开始生成 {args.count} 个令牌，主题：{args.theme}")

    # 计算有效期
    now = datetime.now()
    usage_valid_until = (now + timedelta(days=args.usage_days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    access_valid_until = (now + timedelta(days=args.access_days)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )

    print(f"使用有效期：{usage_valid_until.strftime('%Y-%m-%d')}（{args.usage_days}天）")
    print(f"访问有效期：{access_valid_until.strftime('%Y-%m-%d')}（{args.access_days}天）")

    # 生成令牌
    tokens = admin_service.generate_tokens(
        count=args.count,
        theme=args.theme,
        prefix=args.prefix,
        max_usage_count=args.max_usage,
        usage_valid_days=args.usage_days,
        access_valid_days=args.access_days
    )

    # 保存令牌
    if admin_service.save_tokens(tokens):
        print(f"✓ 成功保存 {len(tokens)} 个令牌到 {TOKENS_FILE}")
    else:
        print(f"✗ 保存令牌失败")
        return

    # 生成二维码
    qr_files = admin_service.generate_qr_codes(tokens)
    print(f"✓ 成功生成 {len(qr_files)} 个二维码，保存到 {admin_service.qr_codes_dir}")

    # 如果有模板，生成海报
    if args.template:
        template_file = args.template
        if os.path.exists(template_file):
            poster_files = admin_service.generate_posters(
                qr_files=qr_files,
                template_file=template_file,
                sequence_prefix=args.seq_prefix,
                start_number=args.start_number
            )
            print(f"✓ 成功生成 {len(poster_files)} 个海报，保存到 {admin_service.posters_dir}")
        else:
            print(f"✗ 模板文件不存在：{template_file}")

    # 打印令牌信息
    print("\n生成的令牌：")
    for i, token in enumerate(tokens):
        print(f"{i+1}. ID: {token.token_id}")
        print(f"   主题: {token.theme}")
        print(f"   使用次数: {token.max_usage_count}")
        print(f"   二维码: {qr_files[i]}")
        print("")

    print(f"完成！所有文件已保存到：{STORAGE_DIR}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="哪吒形象生成系统 - 令牌生成工具")
    parser.add_argument("--count", type=int, default=10, help="生成令牌数量 (1-100)")
    parser.add_argument("--theme", type=str, choices=["ice", "fire"], default="ice", help="令牌主题")
    parser.add_argument("--prefix", type=str, default="", help="令牌前缀")
    parser.add_argument("--max-usage", type=int, default=10, help="最大使用次数")
    parser.add_argument("--usage-days", type=int, default=2, help="使用有效期(天)")
    parser.add_argument("--access-days", type=int, default=9, help="访问有效期(天)")
    parser.add_argument("--template", type=str, help="海报模板文件路径")
    parser.add_argument("--seq-prefix", type=str, default="No.", help="序列号前缀")
    parser.add_argument("--start-number", type=int, default=1, help="起始序列号")

    args = parser.parse_args()

    if args.count < 1 or args.count > 100:
        print("错误：生成数量必须在1-100之间")
        sys.exit(1)

    generate_tokens(args)