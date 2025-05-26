import cv2

video_path = r"D:\Calvin\Semester 8\TA\attandance-app\admin\static\uploads\videos\9\TPTK_TEST.mov"
cap = cv2.VideoCapture(video_path)

if not cap.isOpened():
    print("[ERROR] Cannot open video")

while True:
    ret, frame = cap.read()
    if not ret:
        print("[ERROR] Cannot read frame")
        break
    cv2.imshow("Video", frame)
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
