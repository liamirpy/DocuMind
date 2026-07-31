import hashlib

from starlette.datastructures import Headers, UploadFile

from app.utils import save_upload_to_temp, sha256_file


async def test_save_upload_to_temp_returns_standard_sha256() -> None:
    content = b"%PDF-1.4\nexample"
    upload = UploadFile(
        filename="example.pdf",
        file=__import__("io").BytesIO(content),
        headers=Headers({"content-type": "application/pdf"}),
    )

    path, digest, size = await save_upload_to_temp(upload, max_bytes=1024)
    try:
        assert digest == hashlib.sha256(content).hexdigest()
        assert size == len(content)
    finally:
        path.unlink(missing_ok=True)


def test_sha256_file_matches_hashlib(tmp_path) -> None:
    content = b"%PDF-1.4\nmounted example"
    path = tmp_path / "mounted.pdf"
    path.write_bytes(content)
    assert sha256_file(path) == hashlib.sha256(content).hexdigest()
