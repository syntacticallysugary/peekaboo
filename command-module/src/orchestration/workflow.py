from langgraph.graph import END, StateGraph

from orchestration.nodes import (
    fetch_frame_node,
    notify_dashboard_node,
    persist_event_node,
    run_detection_node,
    run_recognition_node,
    start_recording_node,
    suppress_recording_node,
)
from orchestration.routers import face_detection_router, recognition_router
from orchestration.state import SystemState


def build_workflow():
    g = StateGraph(SystemState)

    g.add_node("fetch_frame",    fetch_frame_node)
    g.add_node("detect",         run_detection_node)
    g.add_node("recognize",      run_recognition_node)
    g.add_node("record",         start_recording_node)
    g.add_node("suppress",       suppress_recording_node)
    g.add_node("persist",        persist_event_node)
    g.add_node("notify",         notify_dashboard_node)

    g.set_entry_point("fetch_frame")
    g.add_edge("fetch_frame", "detect")

    g.add_conditional_edges("detect", face_detection_router, {
        "recognize": "recognize",
        "record":    "record",
        "notify":    "notify",   # error path
    })

    g.add_conditional_edges("recognize", recognition_router, {
        "record":   "record",
        "suppress": "suppress",
        "notify":   "notify",   # error path
    })

    g.add_edge("record",   "persist")
    g.add_edge("suppress", "persist")
    g.add_edge("persist",  "notify")
    g.add_edge("notify",   END)

    return g.compile()


guard_workflow = build_workflow()
