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