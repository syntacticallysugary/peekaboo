# Requirements Document

## Introduction

The Peekaboo Intellegence is a distributed, multi-camera security system that performs local facial recognition and selectively records unrecognized individuals. The system uses ESP32-based camera nodes as eyes, a Jetson Orin Nano 8GB as a dedicated inference node, and a Command Module (initially on a local R5 workstation, designed for future migration to AWS) for orchestration, storage, and the web interface. All processing remains on private hardware, ensuring biometric data never leaves the owner's control.

## Glossary

- **Eye_Node**: An ESP32-S3-EYE camera module deployed independently over WiFi
- **Cam_Node**: An ESP32-CAM paired with an ESP32-C6-DevKitC-1 V1.2 for networking and control
- **Camera_Node**: Either an Eye_Node or Cam_Node; the generic term for any ESP32 camera endpoint
- **Inference_Node**: The Jetson Orin Nano 8GB running GPU-accelerated face detection and recognition; exposes a simple REST inference API only — no web UI
- **Command_Module**: The orchestration, web interface, and storage layer (R5 workstation initially; AWS-deployable)
- **Known_Person**: An individual whose facial data is stored in the local recognition database
- **Unknown_Person**: An individual whose face is not recognized by the local database
- **Unallowed_Person**: An individual whose face is recognized but is listed as blocked
- **Motion_Event**: Detection of movement in a camera frame that exceeds the configured threshold
- **Face_Detection**: Identifying human faces within a camera frame (runs on Inference_Node)
- **Recognition_Process**: Comparing detected faces against the known-persons database (runs on Inference_Node)
- **Recording_Session**: A video clip capture triggered by an unknown or unallowed person detection; stored on the Command_Module
- **Local_Database**: PostgreSQL + pgvector store of known-person facial embeddings, hosted on the Command_Module

## Requirements

### Requirement 1

**User Story:** As a privacy-conscious homeowner, I want all facial recognition processing to happen on private hardware I control, so that my biometric data never leaves my premises.

#### Acceptance Criteria

1. THE System SHALL process all motion detection on Camera_Nodes or the Inference_Node — no cloud vision API calls
2. THE System SHALL perform all facial recognition on the Inference_Node using locally stored models
3. THE System SHALL store all known-person facial embeddings in the Local_Database on the Command_Module only
4. THE System SHALL execute recognition inference at greater than 10 FPS on the Inference_Node
5. THE System SHALL remain fully operational with no internet connection (after initial setup)

---

### Requirement 2

**User Story:** As a homeowner, I want to deploy multiple ESP32 cameras — both standalone Eye_Nodes and paired Cam_Nodes — so I can cover several areas simultaneously without being limited to a single webcam.

#### Acceptance Criteria

1. THE System SHALL support at least four Camera_Nodes simultaneously (any mix of Eye_Nodes and Cam_Nodes)
2. THE System SHALL discover and register Camera_Nodes automatically on the local network
3. WHEN a Camera_Node connects, THE System SHALL assign it a unique identifier and begin receiving its stream
4. WHEN a Camera_Node disconnects, THE System SHALL detect the loss within 30 seconds and flag it in the dashboard without crashing
5. THE Command_Module SHALL display the live status of every registered Camera_Node
6. Eye_Nodes SHALL operate fully independently (no paired controller required)
7. Cam_Nodes SHALL operate as a unit: the ESP32-CAM provides imaging; the ESP32-C6-DevKitC-1 V1.2 handles WiFi connectivity and control

---

### Requirement 3

**User Story:** As a homeowner, I want each camera's motion events to trigger inference analysis, so that the system reacts to actual activity rather than polling continuously.

#### Acceptance Criteria

1. WHEN a Camera_Node detects a Motion_Event, it SHALL push a trigger (with the relevant frame or short clip) to the Inference_Node within 2 seconds
2. THE Inference_Node SHALL perform Face_Detection on the received frame within 1 second of receipt
3. WHEN no motion is detected, Camera_Nodes SHALL remain in monitoring mode without sending data
4. THE System SHALL handle simultaneous Motion_Events from multiple Camera_Nodes without dropping triggers

---

### Requirement 4

**User Story:** As a homeowner, I want the system to recognize known family members and friends so it doesn't record them unnecessarily.

#### Acceptance Criteria

1. WHEN faces are detected, THE Inference_Node SHALL compare embeddings against the Local_Database via the Command_Module API
2. WHEN a Known_Person is identified, THE System SHALL suppress video recording for that Camera_Node for 10 minutes
3. WHEN a Known_Person is identified, THE System SHALL log the event with timestamp and camera ID to the Command_Module
4. THE System SHALL complete the Recognition_Process within 2 seconds of face detection

---

### Requirement 5

**User Story:** As a homeowner, I want the system to record unknown or unallowed individuals so that I have security footage of potential threats.

#### Acceptance Criteria

1. WHEN an Unknown_Person is detected, THE System SHALL trigger a Recording_Session on the Command_Module immediately
2. WHEN no face is detected during a Motion_Event, THE System SHALL trigger a Recording_Session
3. WHEN an Unallowed_Person is detected, THE System SHALL trigger a Recording_Session and send a priority alert
4. THE System SHALL capture 100% of Unknown_Person detections within 2 seconds
5. THE System SHALL store all Recording_Sessions in local storage on the Command_Module with camera ID, timestamp, and classification metadata

---

### Requirement 6

**User Story:** As a system administrator, I want to manage the database of known persons through the web interface, so I can add or remove authorized individuals without touching configuration files.

#### Acceptance Criteria

1. THE Command_Module SHALL expose a web UI for adding known persons by uploading one or more reference images
2. THE Command_Module SHALL expose a web UI for removing or blocking known persons
3. THE System SHALL load known-person embeddings at startup from the Local_Database
4. THE System SHALL persist all known-person changes between system restarts
5. THE System SHALL support updating a known person's reference images without deleting and re-adding them

---

### Requirement 7

**User Story:** As a system administrator, I want the Command Module's web interface and database to run separately from the Inference Node, so I can later move the Command Module to AWS without changing the inference layer.

#### Acceptance Criteria

1. THE Inference_Node SHALL expose only a stateless REST inference API (face detection + recognition); it SHALL NOT host any web UI or database
2. THE Command_Module SHALL be the sole host of the web interface, Local_Database, recording storage, and orchestration logic
3. THE Inference_Node SHALL receive inference requests from and return results to the Command_Module over the local network
4. THE Command_Module SHALL be deployable as a containerized service (Docker) to support future migration to AWS
5. THE System configuration SHALL use environment variables or a config file (not hard-coded IPs) so the Command_Module address is reconfigurable without code changes

---

### Requirement 8

**User Story:** As a system administrator, I want clear real-time feedback in the web dashboard, so I can understand system state, camera health, and recent events at a glance.

#### Acceptance Criteria

1. THE Command_Module dashboard SHALL display live status for every registered Camera_Node (connected, disconnected, streaming, error)
2. WHEN a Recording_Session is triggered, THE dashboard SHALL display a real-time alert with camera ID and detection type
3. THE System SHALL log all recognition decisions with timestamps, camera ID, and outcome to persistent storage
4. THE dashboard SHALL show a recent-events feed with clips or thumbnails for the last N Recording_Sessions
5. THE System SHALL provide Inference_Node health status (GPU utilization, inference latency, queue depth) on the dashboard

---

### Requirement 9

**User Story:** As a system administrator, I want the ability to extend the system over time with additional actions (such as email alerts or smart-home integrations), so the system can grow without major rearchitecting.

#### Acceptance Criteria

1. WHEN any detection event occurs (known, unknown, unallowed, or no-face-motion), THE Command_Module SHALL publish a structured event to an internal event queue
2. THE event queue interface SHALL be documented so new consumers (email, webhook, MQTT bridge) can be added without modifying core logic
3. THE System SHALL support at least one configurable webhook endpoint that receives detection events as JSON
