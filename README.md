# 哪吒形象生成系统

基于二维码访问认证的个性化图片生成系统。

## 功能特点

- **二维码访问认证**：每个二维码包含唯一标识，可以访问特定主题的生成界面
- **主题风格**：支持"冰"和"火"两种主题风格，每种主题有对应的视觉风格和提示词设置
- **一次性使用**：每个图片生成后会保存指纹，防止重复使用
- **有限风格选择**：用户最多可以尝试3种不同风格，包括默认风格
- **有效期限制**：每个访问令牌有使用有效期和访问有效期限制

## 安装说明

### 1. 环境准备

确保您已安装 Python 3.8 或更高版本。然后，按照以下步骤安装必要的依赖：

```bash
# 克隆仓库（如适用）
git clone <repository-url>
cd <repository-folder>

# 安装依赖
pip install -r requirements.txt
```

### 2. 配置设置

1. 复制 `.env.example` 文件并重命名为 `.env`，然后根据需要修改其中的配置。

```bash
cp .env.example .env
```

2. 查看并根据需要修改 `Module/style/nezha/config.json` 中的配置。

### 3. 创建测试令牌（可选）

系统会自动创建示例令牌文件，但如果需要自定义令牌，可以修改 `Module/style/nezha/storage/tokens.json` 文件。

## 使用说明

### 1. 启动应用

```bash
python app_gate.py
```

服务默认会在 http://0.0.0.0:7860 上启动（可在config.json中修改端口和服务器地址）。

### 2. 访问应用

- **默认界面**：直接访问 http://localhost:端口号 会显示未授权的登陆界面
- **测试访问**：
  - 冰主题: http://localhost:端口号/?token=ice123
  - 火主题: http://localhost:端口号/?token=fire123

注意：端口号默认为7860，可在config.json中修改

### 3. 制作二维码（实际部署时）

在实际部署时，您需要为每个令牌生成对应的二维码。二维码内容为访问URL，格式为：

```
http://<your-server-address>:<port>/?token=<token-id>
```

## 目录结构

```
/
├── app_gate.py              # 主入口文件
├── config.json              # 全局配置
├── Module/
│   ├── core/                # 核心功能模块
│   │   ├── auth_service.py  # 认证服务
│   │   ├── image_service.py # 图像处理服务
│   │   └── utils.py         # 工具函数
│   └── style/
│       └── nezha/           # 哪吒主题风格
│           ├── config.json  # 主题配置
│           └── storage/     # 数据存储
│               └── tokens.json  # 令牌存储
```

## 开发扩展

### 添加新主题

1. 在 `Module/style/nezha/config.json` 的 `themes` 部分添加新主题配置
2. 在 `Module/core/utils.py` 的 `get_css_for_theme` 函数中添加新主题的CSS样式

### 添加新令牌

修改 `Module/style/nezha/storage/tokens.json` 文件，添加新的令牌：

```json
"new_token_id": {
  "theme": "ice",  // 或 "fire"
  "usage_count": 0,
  "max_usage_count": 3,
  "created_at": 1710338400,
  "usage_valid_until": 1715608800,
  "access_valid_until": 1720866000,
  "used_image_hashes": [],
  "used_styles": [],
  "generation_records": []
}
```

## 注意事项

- 请确保服务器有足够的存储空间，用于保存生成的图片
- 图片生成需要调用Whisk API，请确保网络连接正常
- 每个令牌的有效期和使用次数有限，请根据需求合理设置
