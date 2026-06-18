#include "frame_stats.h"

volatile uint32_t g_frames_captured  = 0;
volatile uint32_t g_frames_dropped_q = 0;
volatile uint32_t g_frames_sent      = 0;
