import cv2, time, sys, ctypes, atexit

TARGET_FPS = 24
FRAME_TIME  = 1.0 / TARGET_FPS        # 0.041 667 s

# --- Windows: 1-ms timer resolution so sleep() is precise ---
if sys.platform.startswith("win"):
    winmm = ctypes.WinDLL("winmm")
    winmm.timeBeginPeriod(1)
    atexit.register(winmm.timeEndPeriod, 1)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1920)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT,1080)
cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))

if not cap.isOpened():
    print("Failed to open camera")
    sys.exit(1)

prev_disp_fps = 0.0
prev_time     = time.time()           # ← non-zero gap guaranteed

while True:
    loop_start = time.time()

    ret, frame = cap.read()
    if not ret:
        break

    # ── compute instantaneous fps, guard against zero ──
    elapsed = loop_start - prev_time
    if elapsed > 0:                   # only if we have a real delta
        inst_fps        = 1.0 / elapsed
        prev_disp_fps   = 0.8*prev_disp_fps + 0.2*inst_fps
    prev_time = loop_start

    cv2.putText(frame, f"{prev_disp_fps:0.1f} fps", (10,30),
                cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)

    cv2.imshow("cam @ 24 fps", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

    # ── throttle to target fps ──
    sleep_t = FRAME_TIME - (time.time() - loop_start)
    if sleep_t > 0:
        time.sleep(sleep_t)

cap.release()
cv2.destroyAllWindows()
