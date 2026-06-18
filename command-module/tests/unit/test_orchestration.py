import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta
from orchestration.nodes import (
    fetch_frame_node,
    run_detection_node,
    run_recognition_node,
    start_recording_node,
    suppress_recording_node
)
from orchestration.routers import face_detection_router, recognition_router
from orchestration.state import SystemState

@pytest.fixture
def base_state() -> SystemState:
    return {
        "trigger": {"camera_id": "cam1", "timestamp": "2026-05-04T12:00:00Z", "motion_score": 0.8},
        "frame_b64": None,
        "detected_faces": [],
        "recognition_match": None,
        "classification": None,
        "matched_person": None,
        "recording_path": None,
        "known_persons": [],
        "cooldowns": {},
        "inference_online": True,
        "inference_fallback_mode": False,
        "workflow_path": "start",
        "error": None
    }

@pytest.mark.asyncio
async def test_fetch_frame_node_success(base_state):
    base_state["trigger"]["frame_b64"] = "fake_base64"
    new_state = await fetch_frame_node(base_state)
    assert new_state["frame_b64"] == "fake_base64"
    assert new_state["error"] is None

@pytest.mark.asyncio
async def test_run_detection_node_success(base_state):
    base_state["frame_b64"] = "some_frame"
    mock_result = {"faces": [{"confidence": 0.9, "embedding": [0.1] * 512}], "inference_ms": 10}
    
    with patch("orchestration.nodes.inference_client.detect", new_callable=AsyncMock) as mock_detect:
        mock_detect.return_value = mock_result
        new_state = await run_detection_node(base_state)
        
        assert len(new_state["detected_faces"]) == 1
        assert new_state["inference_online"] is True

@pytest.mark.asyncio
async def test_recognition_router_logic(base_state):
    # 1. Unknown person (no match)
    base_state["recognition_match"] = None
    assert recognition_router(base_state) == "record"
    
    # 2. Known person
    base_state["recognition_match"] = {"person_id": "p1", "similarity": 0.9}
    base_state["matched_person"] = {"person_id": "p1", "name": "Alice", "is_blocked": False}
    assert recognition_router(base_state) == "suppress"
    
    # 3. Unallowed person
    base_state["matched_person"]["is_blocked"] = True
    assert recognition_router(base_state) == "record"

@pytest.mark.asyncio
async def test_suppression_cooldown_logic(base_state):
    base_state["trigger"] = {"camera_id": "cam1"}
    base_state["recognition_match"] = {"person_id": "p1", "similarity": 0.9}
    base_state["matched_person"] = {"person_id": "p1", "name": "Alice", "is_blocked": False}
    
    # Set a future cooldown
    base_state["cooldowns"]["cam1"] = datetime.now(timezone.utc) + timedelta(minutes=5)
    
    # Router should skip to notify if in cooldown
    assert recognition_router(base_state) == "notify"
    
    # Expired cooldown
    base_state["cooldowns"]["cam1"] = datetime.now(timezone.utc) - timedelta(minutes=1)
    assert recognition_router(base_state) == "suppress"

@pytest.mark.asyncio
async def test_inference_fallback_router(base_state):
    base_state["inference_fallback_mode"] = True
    # Should skip detection and go straight to record
    assert face_detection_router(base_state) == "record"

@pytest.mark.asyncio
async def test_start_recording_node_no_faces(base_state):
    base_state["detected_faces"] = []
    with patch("orchestration.nodes.check_storage_health", new_callable=AsyncMock) as mock_health:
        mock_health.return_value = True
        with patch("orchestration.nodes.record_clip", new_callable=AsyncMock) as mock_record:
            mock_record.return_value = "path/to/clip.mp4"
            base_state["trigger"]["stream_url"] = "http://stream"
            
            new_state = await start_recording_node(base_state)
            assert new_state["classification"] == "no_face"
            assert new_state["recording_path"] == "path/to/clip.mp4"
