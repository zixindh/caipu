# 七日食谱 · Caipu

Eva、Heng 和强尼共用的中文七日菜单。应用会滚动显示从今天开始的 7 天，每天包含早餐、午餐和晚餐，并自动汇总尚未备齐的食材。

## 功能

- 固定选择 Eva、Heng 或强尼即可进入，无需密码或用户 Secrets
- 每餐记录菜品、食材、提议人和备注
- 每餐独立标记“食材已购买或冰箱已有”
- 自动生成采购清单，合并重复食材
- 只有保存和手动刷新时访问 Notion，减少等待和界面卡顿
- 每天自动滚动：始终显示今天起 7 天，次日自动加入新的空白日期
- 手机和电脑都可使用

## 部署到 Streamlit Community Cloud

1. 打开 [Streamlit Community Cloud](https://share.streamlit.io/)，选择 `Create app`。
2. 仓库填写 `zixindh/caipu`，分支选择 `main`，入口文件填写 `app.py`。
3. 打开 `Advanced settings` → `Secrets`。
4. 粘贴下面两个环境变量，并替换现有 Notion Token：

```toml
NOTION_TOKEN = "ntn_你的现有Notion API密钥"
NOTION_PAGE_ID = "392a6041f59c80fb8868f369f02a0470"
```

5. 保存并部署。

> 不要把真实 Token 提交到 GitHub。Streamlit 官方建议使用应用设置中的 Secrets 保存凭据。

仅需这两个变量，不需要再编辑 Food 页面或手工创建数据库。应用首次打开时会在指定页面下自动找到或创建 `七日餐单 · Caipu` 数据库和全部字段。

## 日常使用

- 在登录页点选 Eva、Heng 或强尼即可进入。
- 进入后选择日期，再编辑早餐、午餐或晚餐。
- 点击“保存这一餐”才会写入 Notion。
- 家人修改后，点击页面右上角“刷新”获取最新版本。
- 如果食材已经买好或冰箱里已有，打开该餐的“食材已购买或冰箱已有”。
- “采购清单”只显示尚未备齐的餐次所需食材。

同一餐若两个人同时编辑，最后保存的版本会覆盖较早版本。保存前不会自动拉取另一人的改动；需要时请先点“刷新”。应用刻意不做实时同步，以保持免费层上的操作流畅。

七日窗口不需要手工生成。每天按中国时区自动前移一天：昨天退出当前视图，原有未来六天保留，并在末尾增加一个包含早餐、午餐和晚餐空白输入区的新日期。历史数据仍保存在 Notion。

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
