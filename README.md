# 七日食谱 · Caipu

Eva、Heng 和强尼共用的中文七日菜单。应用会滚动显示从今天开始的 7 天，每天包含早餐、午餐和晚餐，并自动汇总尚未备齐的食材。

## 功能

- 固定选择 Eva、Heng 或强尼即可进入，无需密码或用户 Secrets
- 每餐记录菜品、食材、提议人和备注
- 每餐独立标记“食材已购买或冰箱已有”
- 自动生成采购清单，合并重复食材
- 只有保存和手动刷新时访问 Notion，减少等待和界面卡顿
- 手机和电脑都可使用

## 第一次设置

### 1. 在 Notion 创建连接

1. 打开 [Notion Integrations](https://www.notion.so/profile/integrations)。
2. 新建一个内部连接，例如命名为 `Caipu`。
3. 打开连接的权限设置，确认启用读取、插入和更新内容。
4. 复制内部集成密钥（通常以 `ntn_` 开头）。

### 2. 准备一个 Notion 页面

1. 打开已经准备好的 [Food 页面](https://app.notion.com/p/Food-392a6041f59c80fb8868f369f02a0470)。
2. 点击页面右上角 `•••`，选择 `连接` 或 `Add connections`，加入刚创建的 `Caipu` 连接。

首次启动时，应用会在这个页面下自动创建 `七日餐单 · Caipu` 数据库和全部字段，不需要手工建表。

### 3. 部署到 Streamlit Community Cloud

1. 打开 [Streamlit Community Cloud](https://share.streamlit.io/)，选择 `Create app`。
2. 仓库填写 `zixindh/caipu`，分支选择 `main`，入口文件填写 `app.py`。
3. 打开 `Advanced settings` → `Secrets`。
4. 粘贴下面配置，并替换 Notion Token：

```toml
[notion]
token = "ntn_你的Notion连接密钥"
parent_page_id = "392a6041f59c80fb8868f369f02a0470"
```

5. 保存并部署。首次打开会自动初始化 Notion 数据库。

> 不要把真实 Token 提交到 GitHub。Streamlit 官方建议使用应用设置中的 Secrets 保存凭据。

## 日常使用

- 在登录页点选 Eva、Heng 或强尼即可进入。
- 进入后选择日期，再编辑早餐、午餐或晚餐。
- 点击“保存这一餐”才会写入 Notion。
- 家人修改后，点击页面右上角“刷新”获取最新版本。
- 如果食材已经买好或冰箱里已有，打开该餐的“食材已购买或冰箱已有”。
- “采购清单”只显示尚未备齐的餐次所需食材。

同一餐若两个人同时编辑，最后保存的版本会覆盖较早版本。保存前不会自动拉取另一人的改动；需要时请先点“刷新”。应用刻意不做实时同步，以保持免费层上的操作流畅。

## 本地开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .streamlit/secrets.example.toml .streamlit/secrets.toml
streamlit run app.py
```

本地测试：

```bash
python -m unittest discover -s tests
```
