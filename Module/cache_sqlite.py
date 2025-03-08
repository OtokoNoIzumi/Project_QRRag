import os
import sys
import hashlib
import sqlite3
import json
import time
import threading
from typing import Dict, Optional

# 处理路径问题
def get_project_paths():
    """获取项目相关路径，处理py文件和jupyter notebook不同环境"""
    if "__file__" in globals():
        current_file = os.path.abspath(__file__)
        module_dir = os.path.dirname(current_file)
        project_root = os.path.dirname(module_dir)
    else:
        # 在Jupyter Notebook环境中
        current_dir = os.getcwd()
        module_dir = os.path.join(current_dir, "Module")
        project_root = current_dir

    cache_dir = os.path.join(project_root, "cache")
    schema_dir = os.path.join(project_root, "schema")

    return project_root, module_dir, cache_dir, schema_dir

# 获取路径
PROJECT_ROOT, MODULE_DIR, CACHE_DIR, SCHEMA_DIR = get_project_paths()

# 缓存文件路径
SQLITE_DB_FILE = os.path.join(CACHE_DIR, "whisk_cache.db")
SCHEMA_FILE = os.path.join(SCHEMA_DIR, "whisk_cache_schema.sql")

# 原始JSON缓存文件路径 (用于迁移)
CAPTION_CACHE_FILE = os.path.join(CACHE_DIR, "image_caption_cache.json")
STORY_CACHE_FILE = os.path.join(CACHE_DIR, "story_prompt_cache.json")


class WhiskCacheSQLite:
    """基于SQLite的Whisk缓存管理类，API与WhiskCache保持一致"""

    def __init__(self, auto_migrate=False):
        """
        初始化SQLite缓存

        Args:
            auto_migrate: 自动从JSON迁移数据到SQLite (默认为False，仅首次使用时手动设为True)
        """
        # 确保缓存目录存在
        os.makedirs(CACHE_DIR, exist_ok=True)
        os.makedirs(SCHEMA_DIR, exist_ok=True)

        # 连接数据库 (延迟初始化，仅当需要时才连接)
        self.conn = None
        # 添加线程锁用于保护数据库操作
        self.lock = threading.RLock()

        # 检查是否需要初始化数据库
        if not os.path.exists(SQLITE_DB_FILE) or os.path.getsize(SQLITE_DB_FILE) == 0:
            self._connect_db()
            self._init_db_schema()

            # 新数据库且开启自动迁移，则执行迁移
            if auto_migrate:
                self._migrate_from_json()
        elif auto_migrate:
            # 如果数据库已存在但仍请求迁移，检查是否表为空
            self._connect_db()
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM sqlite_master WHERE type='table'")
            table_count = cursor.fetchone()[0]

            if table_count == 0:
                self._init_db_schema()
                self._migrate_from_json()

    def _connect_db(self):
        """连接到SQLite数据库"""
        if self.conn is None:
            self.conn = sqlite3.connect(SQLITE_DB_FILE, check_same_thread=False)
            # 启用外键约束
            self.conn.execute("PRAGMA foreign_keys = ON")
            # 配置使返回的行为字典而不是元组
            self.conn.row_factory = sqlite3.Row

    def _init_db_schema(self):
        """初始化数据库Schema"""
        self._connect_db()

        # 优先使用Schema文件
        if os.path.exists(SCHEMA_FILE):
            with open(SCHEMA_FILE, 'r', encoding='utf-8') as f:
                schema_sql = f.read()
                with self.lock:
                    self.conn.executescript(schema_sql)
                    self.conn.commit()
        else:
            # 回退使用内置Schema
            self._create_default_schema()

    def _create_default_schema(self):
        """创建默认的数据库Schema"""
        # 内置默认Schema定义
        default_schema = """
        -- 图片描述缓存表
        CREATE TABLE IF NOT EXISTS caption_cache (
            hash_key TEXT PRIMARY KEY,  -- 图片base64的MD5哈希值
            caption TEXT NOT NULL,      -- 图片描述文本
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 创建时间
        );

        -- 故事提示词缓存表
        CREATE TABLE IF NOT EXISTS story_cache (
            cache_key TEXT PRIMARY KEY,  -- caption, style_key和additional_text组合的MD5哈希值
            prompt TEXT NOT NULL,        -- 故事提示词
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP -- 创建时间
        );

        -- 添加索引以提高查询性能
        CREATE INDEX IF NOT EXISTS idx_caption_cache_hash_key ON caption_cache(hash_key);
        CREATE INDEX IF NOT EXISTS idx_story_cache_cache_key ON story_cache(cache_key);
        """

        with self.lock:
            self.conn.executescript(default_schema)
            self.conn.commit()

        # 如果schema目录存在，将默认schema保存到文件
        if not os.path.exists(SCHEMA_FILE) and os.path.exists(SCHEMA_DIR):
            try:
                with open(SCHEMA_FILE, 'w', encoding='utf-8') as f:
                    f.write(default_schema.strip())
                print(f"已将默认Schema保存到: {SCHEMA_FILE}")
            except Exception as e:
                print(f"保存Schema文件失败: {str(e)}")

    def _migrate_from_json(self):
        """从JSON文件迁移数据到SQLite"""
        self._connect_db()

        # 迁移图片描述缓存
        if os.path.exists(CAPTION_CACHE_FILE):
            try:
                with open(CAPTION_CACHE_FILE, 'r', encoding='utf-8') as f:
                    caption_data = json.load(f)

                if caption_data:
                    with self.lock:
                        # 检查是否有数据需要迁移
                        cursor = self.conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM caption_cache")
                        count = cursor.fetchone()[0]

                        # 只有当SQLite表为空时才迁移
                        if count == 0:
                            print(f"开始从 {CAPTION_CACHE_FILE} 迁移数据到SQLite...")
                            for hash_key, caption in caption_data.items():
                                self.conn.execute(
                                    "INSERT OR IGNORE INTO caption_cache (hash_key, caption) VALUES (?, ?)",
                                    (hash_key, caption)
                                )
                            self.conn.commit()
                            print(f"成功迁移 {len(caption_data)} 条图片描述缓存")
            except Exception as e:
                print(f"迁移图片描述缓存失败: {str(e)}")

        # 迁移故事提示词缓存
        if os.path.exists(STORY_CACHE_FILE):
            try:
                with open(STORY_CACHE_FILE, 'r', encoding='utf-8') as f:
                    story_data = json.load(f)

                if story_data:
                    with self.lock:
                        # 检查是否有数据需要迁移
                        cursor = self.conn.cursor()
                        cursor.execute("SELECT COUNT(*) FROM story_cache")
                        count = cursor.fetchone()[0]

                        # 只有当SQLite表为空时才迁移
                        if count == 0:
                            print(f"开始从 {STORY_CACHE_FILE} 迁移数据到SQLite...")
                            for cache_key, prompt in story_data.items():
                                self.conn.execute(
                                    "INSERT OR IGNORE INTO story_cache (cache_key, prompt) VALUES (?, ?)",
                                    (cache_key, prompt)
                                )
                            self.conn.commit()
                            print(f"成功迁移 {len(story_data)} 条故事提示词缓存")
            except Exception as e:
                print(f"迁移故事提示词缓存失败: {str(e)}")

    def get_caption(self, image_base64: str):
        """获取缓存的图片描述，保持与原API一致"""
        self._connect_db()

        hash_key = hashlib.md5(image_base64.encode()).hexdigest()
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT caption FROM caption_cache WHERE hash_key = ?", (hash_key,))
            row = cursor.fetchone()
            if row:
                # 将Row对象转换为字典以便于调试
                row_dict = dict(row)
                print(f"获取图片描述成功: {row_dict}")
            else:
                print(f"未找到图片描述，hash_key: {hash_key[:8]}...")
        return row['caption'] if row else None

    def save_caption(self, image_base64: str, caption: str):
        """缓存图片描述，保持与原API一致"""
        self._connect_db()

        hash_key = hashlib.md5(image_base64.encode()).hexdigest()
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO caption_cache (hash_key, caption) VALUES (?, ?)",
                (hash_key, caption)
            )
            self.conn.commit()

    def get_story_prompt(self, caption: str, style_key: str, additional_text: str):
        """获取缓存的故事提示词，保持与原API一致"""
        self._connect_db()

        cache_key = hashlib.md5(f"{caption}_{style_key}_{additional_text}".encode()).hexdigest()
        with self.lock:
            cursor = self.conn.cursor()
            cursor.execute("SELECT prompt FROM story_cache WHERE cache_key = ?", (cache_key,))
            row = cursor.fetchone()
            if row:
                # 将Row对象转换为字典以便于调试
                row_dict = dict(row)
                print(f"获取故事提示词成功: {row_dict}")
            else:
                print(f"未找到故事提示词，cache_key: {cache_key[:8]}...")
        return row['prompt'] if row else None

    def save_story_prompt(self, caption: str, style_key: str, additional_text: str, prompt: str):
        """缓存故事提示词，保持与原API一致"""
        self._connect_db()

        cache_key = hashlib.md5(f"{caption}_{style_key}_{additional_text}".encode()).hexdigest()
        with self.lock:
            self.conn.execute(
                "INSERT OR REPLACE INTO story_cache (cache_key, prompt) VALUES (?, ?)",
                (cache_key, prompt)
            )
            self.conn.commit()

    def export_to_json(self):
        """将SQLite缓存导出为JSON文件 (备份功能)"""
        self._connect_db()

        with self.lock:
            # 导出图片描述缓存
            cursor = self.conn.cursor()
            cursor.execute("SELECT hash_key, caption FROM caption_cache")
            caption_data = {row['hash_key']: row['caption'] for row in cursor.fetchall()}

            # 导出故事提示词缓存
            cursor.execute("SELECT cache_key, prompt FROM story_cache")
            story_data = {row['cache_key']: row['prompt'] for row in cursor.fetchall()}

        with open(CAPTION_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(caption_data, f, ensure_ascii=False, indent=4)

        with open(STORY_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(story_data, f, ensure_ascii=False, indent=4)

        print(f"缓存已导出为JSON格式: {CAPTION_CACHE_FILE}, {STORY_CACHE_FILE}")

    def clear_cache(self, older_than_days=None):
        """清除缓存数据

        Args:
            older_than_days: 如果指定，仅清除早于指定天数的缓存
        """
        self._connect_db()

        with self.lock:
            if older_than_days is not None:
                # 计算截止时间戳
                cutoff_time = time.time() - (older_than_days * 86400)
                cutoff_timestamp = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(cutoff_time))

                self.conn.execute("DELETE FROM caption_cache WHERE created_at < ?", (cutoff_timestamp,))
                self.conn.execute("DELETE FROM story_cache WHERE created_at < ?", (cutoff_timestamp,))
            else:
                # 清除所有缓存
                self.conn.execute("DELETE FROM caption_cache")
                self.conn.execute("DELETE FROM story_cache")

            self.conn.commit()

    def verify_cache(self, limit=10, print_content=True):
        """验证并显示缓存内容，便于调试

        Args:
            limit: 每个表最多显示的记录数
            print_content: 是否打印内容详情

        Returns:
            dict: 包含缓存统计信息的字典
        """
        self._connect_db()

        result = {
            "caption_cache": {
                "count": 0,
                "samples": []
            },
            "story_cache": {
                "count": 0,
                "samples": []
            }
        }

        with self.lock:
            # 获取图片描述缓存统计
            cursor = self.conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM caption_cache")
            result["caption_cache"]["count"] = cursor.fetchone()[0]

            # 获取最新的图片描述记录
            cursor.execute(
                "SELECT hash_key, caption, created_at FROM caption_cache ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            for row in cursor.fetchall():
                row_dict = dict(row)
                # 为了节省空间，只显示caption的前50个字符
                if len(row_dict["caption"]) > 50:
                    row_dict["caption"] = row_dict["caption"][:50] + "..."
                result["caption_cache"]["samples"].append(row_dict)

            # 获取故事提示词缓存统计
            cursor.execute("SELECT COUNT(*) FROM story_cache")
            result["story_cache"]["count"] = cursor.fetchone()[0]

            # 获取最新的故事提示词记录
            cursor.execute(
                "SELECT cache_key, prompt, created_at FROM story_cache ORDER BY created_at DESC LIMIT ?",
                (limit,)
            )
            for row in cursor.fetchall():
                row_dict = dict(row)
                # 为了节省空间，只显示prompt的前50个字符
                if len(row_dict["prompt"]) > 50:
                    row_dict["prompt"] = row_dict["prompt"][:50] + "..."
                result["story_cache"]["samples"].append(row_dict)

        if print_content:
            print("===== 缓存验证报告 =====")
            print(f"图片描述缓存: {result['caption_cache']['count']} 条记录")
            if result["caption_cache"]["samples"]:
                print(f"最新 {len(result['caption_cache']['samples'])} 条记录:")
                for i, sample in enumerate(result["caption_cache"]["samples"]):
                    print(f"  {i+1}. hash: {sample['hash_key'][:8]}..., time: {sample['created_at']}")
                    print(f"     caption: {sample['caption']}")

            print(f"\n故事提示词缓存: {result['story_cache']['count']} 条记录")
            if result["story_cache"]["samples"]:
                print(f"最新 {len(result['story_cache']['samples'])} 条记录:")
                for i, sample in enumerate(result["story_cache"]["samples"]):
                    print(f"  {i+1}. hash: {sample['cache_key'][:8]}..., time: {sample['created_at']}")
                    print(f"     prompt: {sample['prompt']}")

            print("========================")

        return result

    def __del__(self):
        """析构函数，确保关闭数据库连接"""
        if hasattr(self, 'conn') and self.conn is not None:
            self.conn.close()


# 用于向后兼容的代码 - 使原始WhiskCache继承SQLite版本
class WhiskCache(WhiskCacheSQLite):
    """继承SQLite版本的缓存类，保持完全兼容原API，同时提供平滑迁移"""

    def __init__(self):
        """初始化时自动从JSON迁移到SQLite"""
        # 首次使用时读取配置决定是否迁移
        config_file = os.path.join(PROJECT_ROOT, "config.json")
        auto_migrate = False

        if os.path.exists(config_file):
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                    # 如果配置中有cache_auto_migrate字段，使用该值
                    auto_migrate = config.get("cache_auto_migrate", False)
            except Exception:
                # 配置读取失败，使用默认值
                pass

        super().__init__(auto_migrate=auto_migrate)

    # 使用JSON版本中的方法名称，但功能使用SQLite实现
    # 所有方法都由父类WhiskCacheSQLite提供

    def _load_cache(self, file_path: str) -> Dict:
        """保持兼容原始API，但实际不再使用"""
        # 该方法保留仅用于向后兼容，不实际加载任何文件
        # 所有数据由SQLite提供
        return {}

    def save_cache(self, file_path: str, data: Dict):
        """保持兼容原始API，但实际不再使用"""
        # 该方法保留仅用于向后兼容，不实际保存任何文件
        # 所有数据由SQLite自动保存
        pass


# 用于一次性迁移的辅助函数
def migrate_json_to_sqlite():
    """一次性迁移JSON数据到SQLite数据库"""
    cache = WhiskCacheSQLite(auto_migrate=True)
    print("迁移完成。后续使用会自动使用SQLite数据库，无需再次迁移。")
    return cache