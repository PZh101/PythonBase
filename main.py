"""项目 HTTP 服务启动入口。"""

from app.web import create_app

app = create_app()


def main() -> None:
    """启动 FastAPI HTTP 服务。

    使用方式:
        在项目根目录运行 `uv run python main.py`，随后访问
        `http://127.0.0.1:8000/docs` 查看已注册接口。
    """
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
