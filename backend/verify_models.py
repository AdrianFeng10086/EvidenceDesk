"""
API 连通性验证脚本

运行此脚本以验证 LLM 和向量模型的连接。

使用方法:
    python verify_models.py
"""

import os
import sys
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()


# 1x1 白色 PNG，用于视觉模型连通性测试
_TEST_IMAGE_B64 = (
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8/x8AAwMCAO+ip1sAAAAASUVORK5CYII="
)


def _print_available_models(client):
    """模型名错误时，列出服务端可用模型便于排查"""
    try:
        ids = [m.id for m in client.models.list().data]
        print(f"   可用模型: {', '.join(ids)}")
    except Exception:
        pass


def verify_llm():
    """验证主 LLM（OpenAI 兼容接口）连通性"""
    provider = os.getenv("LLM_PROVIDER", "deepseek")
    print(f"\n🔍 验证 LLM API ({provider})...")

    if not os.getenv("LLM_API_KEY"):
        print("❌ 环境变量中未找到 LLM_API_KEY")
        return False

    try:
        import openai
        from services.llm import get_llm_client, llm_model

        client = get_llm_client()
        model = llm_model()

        resp = client.chat.completions.create(
            model=model,
            max_tokens=50,
            messages=[{"role": "user", "content": "你好，如果收到请回复'OK'"}],
        )

        response_text = resp.choices[0].message.content or ""
        print(f"✅ LLM API 连接成功")
        print(f"   地址: {client.base_url}")
        print(f"   模型: {resp.model}")
        print(f"   响应: {response_text[:50]}")
        return True

    except ImportError:
        print("❌ openai 包未安装。请运行: pip install -r requirements.txt")
        return False
    except openai.NotFoundError as e:
        print(f"❌ 模型或接口不存在 (LLM_MODEL={model}): {e}")
        _print_available_models(client)
        return False
    except openai.APIConnectionError as e:
        print(f"❌ 无法连接 {client.base_url}，请检查 LLM_BASE_URL: {e}")
        return False
    except Exception as e:
        print(f"❌ LLM API 错误: {type(e).__name__}: {e}")
        return False


def verify_vision():
    """验证视觉模型是否接受图片输入（非阻断：仅视觉证据功能依赖它）"""
    print("\n🔍 验证视觉模型图片输入...")

    try:
        from services.llm import get_llm_client, vision_model

        client = get_llm_client(vision=True)
        model = vision_model()

        resp = client.chat.completions.create(
            model=model,
            max_tokens=20,
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": "这张图片是什么颜色？只回答颜色。"},
                    {"type": "image_url",
                     "image_url": {"url": f"data:image/png;base64,{_TEST_IMAGE_B64}"}},
                ],
            }],
        )

        print(f"✅ 视觉模型可用")
        print(f"   模型: {resp.model}")
        print(f"   响应: {(resp.choices[0].message.content or '')[:50]}")

    except Exception as e:
        print(f"⚠️  视觉模型不可用 (VISION_MODEL={os.getenv('VISION_MODEL')}): {type(e).__name__}: {e}")
        print("   不影响文本问答；视觉证据功能需要换用支持图片输入的模型")

    return True


def verify_cloudflare_embedding():
    """验证 Cloudflare Workers AI 向量化 API 连通性"""
    print("\n🔍 验证 Cloudflare Workers AI 向量化 API...")

    for var in ("CLOUDFLARE_ACCOUNT_ID", "EMBEDDING_API_KEY"):
        if not os.getenv(var):
            print(f"❌ 环境变量中未找到 {var}")
            return False

    try:
        from services.embedding import CloudflareEmbedding, EmbeddingError

        client = CloudflareEmbedding()

        # 测试向量化（维度校验在客户端内完成）
        embeddings = client.embed(["这是一段中文文本", "这是另一段中文文本"])

        print(f"✅ Cloudflare 向量化 API 连接成功")
        print(f"   模型: {client.model}")
        print(f"   数量: {len(embeddings)}  维度: {len(embeddings[0])} (期望: {client.dimension})")
        return True

    except ImportError as e:
        print(f"❌ 依赖缺失: {e}。请运行: pip install -r requirements.txt")
        return False
    except EmbeddingError as e:
        print(f"❌ Cloudflare API 错误: {e}")
        return False
    except Exception as e:
        print(f"❌ 请求失败: {type(e).__name__}: {e}")
        return False


def main():
    print("=" * 60)
    print("有据工作台 - 模型连通性验证")
    print("=" * 60)

    results = []

    # 检查必需的包
    print("\n📦 检查必需的包...")
    try:
        import openai
        print("✅ openai")
    except ImportError:
        print("❌ openai 未安装")
        results.append(False)

    try:
        import httpx
        print("✅ httpx")
    except ImportError:
        print("❌ httpx 未安装")
        results.append(False)

    # 验证 API
    results.append(verify_llm())
    results.append(verify_vision())
    results.append(verify_cloudflare_embedding())

    # 汇总
    print("\n" + "=" * 60)
    if all(results):
        print("✅ 所有验证通过!")
        print("\n现在可以运行:")
        print("  python main.py")
        return 0
    else:
        print("❌ 部分验证失败")
        print("\n请执行:")
        print("  1. 安装缺失的包: pip install -r requirements.txt")
        print("  2. 在 .env 文件中设置 API 密钥")
        print("  3. 再次运行此脚本")
        return 1


if __name__ == "__main__":
    sys.exit(main())
