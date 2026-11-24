"""测试全局默认：关闭本地 embedding 模型。

单测不应依赖 95MB 模型下载或本机缓存；纯 BM25 降级路径已能覆盖绝大多数逻辑。
需要验证稠密路的用例（tests/test_rag.py 的 fake_model 夹具）会自行覆盖为 auto，
并用假向量注入，避免真实推理。
"""

import pytest


@pytest.fixture(autouse=True)
def embedding_off_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CAMPUS_EMBEDDING", "off")
