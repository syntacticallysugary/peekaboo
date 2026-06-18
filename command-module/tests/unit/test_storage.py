import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from storage.local import LocalDiskBackend

@pytest.fixture
def temp_recordings_path(tmp_path):
    return tmp_path / "recordings"

@pytest.fixture
def local_storage(temp_recordings_path):
    with patch("storage.local.settings") as mock_settings:
        mock_settings.recordings_path = str(temp_recordings_path)
        return LocalDiskBackend()

@pytest.mark.asyncio
async def test_save_clip(local_storage, temp_recordings_path):
    data = b"fake video data"
    rel_path = "2026-05-04/cam01/test.mp4"
    
    saved_path = await local_storage.save_clip(data, rel_path)
    
    assert saved_path == rel_path
    full_path = temp_recordings_path / rel_path
    assert full_path.exists()
    assert full_path.read_bytes() == data

@pytest.mark.asyncio
async def test_get_clip_url(local_storage):
    path = "some/clip.mp4"
    url = await local_storage.get_clip_url(path)
    assert url == f"/recordings/{path}"

@pytest.mark.asyncio
async def test_delete_clip(local_storage, temp_recordings_path):
    rel_path = "delete_me.mp4"
    full_path = temp_recordings_path / rel_path
    full_path.write_bytes(b"data")
    assert full_path.exists()
    
    await local_storage.delete_clip(rel_path)
    assert not full_path.exists()

@pytest.mark.asyncio
async def test_free_bytes(local_storage):
    free = await local_storage.free_bytes()
    assert isinstance(free, int)
    assert free >= 0
