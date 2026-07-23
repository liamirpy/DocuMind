import hashlib
import os
import tempfile
from pathlib import Path

from fastapi import HTTPException, UploadFile, status

PDF_MAGIC = b"%PDF-"


async def save_upload_to_temp(
    upload: UploadFile,
    *,
    max_bytes: int,
    chunk_size: int = 1024 * 1024,
) -> tuple[Path, str, int]:
    """Stream an uploaded PDF to disk while hashing it and enforcing a size limit."""
    digest = hashlib.sha256()
    total = 0
    first_chunk = True

    fd, temp_name = tempfile.mkstemp(prefix="pdf-extract-", suffix=".pdf")
    os.close(fd)
    temp_path = Path(temp_name)

    try:
        with temp_path.open("wb") as output:
            while chunk := await upload.read(chunk_size):
                if first_chunk:
                    first_chunk = False
                    if not chunk.startswith(PDF_MAGIC):
                        raise HTTPException(
                            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            detail="The uploaded file does not have a valid PDF signature.",
                        )

                total += len(chunk)
                if total > max_bytes:
                    raise HTTPException(
                        status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                        detail=f"PDF exceeds the configured limit of {max_bytes} bytes.",
                    )

                digest.update(chunk)
                output.write(chunk)

        if total == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="The uploaded PDF is empty.",
            )

        return temp_path, digest.hexdigest(), total
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def safe_filename(name: str | None) -> str:
    return Path(name).name if name else "document.pdf"


def asset_url(prefix: str, relative_path: str) -> str:
    return f"{prefix.rstrip('/')}/{relative_path.lstrip('/')}"
