"""
WhiskCache迁移工具

该脚本用于将JSON缓存文件一次性迁移到SQLite数据库。
迁移后，系统将自动使用SQLite数据库进行缓存，无需再次迁移。

Usage:
    python cache_migrate.py [--verify]

选项:
    --verify    仅验证当前缓存内容，不执行迁移

也支持导入到其他脚本中使用：
    from cache_migrate import migrate_cache
    migrate_cache()
"""

import os
import json
import sys

# 确保可以导入Module
current_dir = os.path.dirname(os.path.abspath(__file__))
sys.path.append(current_dir)

# 读取config.json，设置cache_auto_migrate=True
def update_config():
    """更新配置文件，启用自动迁移"""
    config_path = os.path.join(current_dir, "config.json")

    # 读取当前配置
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        except Exception as e:
            print(f"读取配置文件失败: {str(e)}")
            config = {}
    else:
        config = {}

    # 设置自动迁移标志
    config["cache_auto_migrate"] = True

    # 保存配置
    try:
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=4)
        print(f"已更新配置文件: {config_path}")
    except Exception as e:
        print(f"保存配置文件失败: {str(e)}")


def verify_cache():
    """仅验证缓存内容，不执行迁移"""
    from Module.cache_sqlite import WhiskCacheSQLite
    cache = WhiskCacheSQLite(auto_migrate=False)
    cache.verify_cache(limit=10)
    return cache


def migrate_cache():
    """执行迁移过程"""
    # 更新配置
    update_config()

    # 导入并执行迁移
    from Module.cache_sqlite import migrate_json_to_sqlite
    cache = migrate_json_to_sqlite()

    # 验证缓存内容
    cache.verify_cache(limit=5)

    print("\n迁移完成！后续使用将自动使用SQLite数据库缓存。")
    return cache


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--verify":
        print("仅验证当前缓存内容，不执行迁移...")
        verify_cache()
    else:
        print("开始迁移WhiskCache从JSON到SQLite...")
        migrate_cache()