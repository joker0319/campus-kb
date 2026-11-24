"""配图索引 id 规则测试：内容哈希是「重建不丢标注」的前提。"""

import hashlib

from tools.build_figure_index import ID_HEX, figure_id


def test_id_is_content_hash_prefix():
    digest = hashlib.sha1(b"fake-image-bytes").hexdigest()
    assert figure_id(digest) == f"f{digest[:ID_HEX]}"
    assert len(figure_id(digest)) == ID_HEX + 1


def test_same_content_same_id():
    """同一张图无论出现在哪篇推文、排第几个，id 必须一致。"""
    digest = hashlib.sha1(b"same-bytes").hexdigest()
    assert figure_id(digest) == figure_id(digest)


def test_different_content_different_id():
    a = figure_id(hashlib.sha1(b"a").hexdigest())
    b = figure_id(hashlib.sha1(b"b").hexdigest())
    assert a != b


def test_id_is_url_safe():
    digest = hashlib.sha1(b"x").hexdigest()
    fid = figure_id(digest)
    assert fid.startswith("f")
    assert all(ch.isalnum() for ch in fid)
