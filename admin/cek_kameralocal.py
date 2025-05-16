import cv2

cap = cv2.VideoCapture(0)  # 0 untuk webcam default

if not cap.isOpened():
    print("Gagal membuka kamera")
    exit()

while True:
    ret, frame = cap.read()
    if not ret:
        print("Gagal membaca frame")
        break

    cv2.imshow('Webcam', frame)

    # Tekan 'q' untuk keluar
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
