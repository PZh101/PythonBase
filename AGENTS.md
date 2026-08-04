# AGENT.md — PythonBase AI 智能体引导

## 项目概述

PythonBase 是一个基于 FastAPI + Pydantic + SQLAlchemy 的 Python 项目基础框架，使用 `uv` 进行项目管理。

## 首次启动

1. 请先阅读 `.agent/CODE_RULE.md` 了解本项目完整的代码规范（包括 Python 编码规范、FastAPI 框架规范、测试规范、项目管理规范等）
2. 了解项目目录结构：`app/` 为应用代码，`pkg/` 为通用框架代码，`docs/` 为文档，`scripts/` 为运维脚本，`tests/` 为测试文件
3. 了解 `pkg/common/api.py` 中的 `BaseSchema`、`SafeBigInt`、`SafeDatetime` 等全局基础类型

## 核心约束

> **所有 FastAPI 接口的请求体和响应体必须使用 Pydantic 模型定义，且必须继承 `pkg.common.api.BaseSchema`。**

这意味着：
- 不能直接使用 `pydantic.BaseModel` 作为 FastAPI 的请求/响应模型
- 必须继承 `BaseSchema` 以获得自动驼峰转换、SafeBigInt、SafeDatetime 等全局能力
- 接口定义中如使用 `response_model`，对应的模型也必须继承 `BaseSchema`

## 注释规范

- **代码注释使用中文** — 行内注释、块注释、类/方法 docstring 均使用中文
- 重要方法须在 docstring 中写明**使用方式**，包括参数说明、返回值说明、以及典型用法示例（如有必要）
- 测试方法的 docstring 使用中文说明测试意图

## 重要提示

- 不要猜测或假设代码规范，遇到不确定的规范问题请先查阅 `.agent/CODE_RULE.md`
- 新增代码请遵循项目目录结构约定，不要随意放置文件