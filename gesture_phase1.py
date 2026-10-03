import cv2
import mediapipe as mp
import math

# ---------------- INITIALIZE ---------------- #
mp_hands = mp.solutions.hands
mp_draw = mp.solutions.drawing_utils

hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.7, # Slightly lowered for better back-of-hand detection
    min_tracking_confidence=0.7
)

cap = cv2.VideoCapture(0)

# ---------------- HELPER FUNCTION ---------------- #

def detect_gesture(hand_landmarks):
    # List to store if fingers are open (1) or closed (0)
    # [Thumb, Index, Middle, Ring, Pinky]
    fingers = []

    # LANDMARK INDICES:
    # Thumb: Tip(4), IP(3), MCP(2)
    # Index: Tip(8), PIP(6)
    # Middle: Tip(12), PIP(10)
    # Ring: Tip(16), PIP(14)
    # Pinky: Tip(20), PIP(18)

    # 1. THUMB LOGIC 
    # Check horizontal distance between thumb tip and index MCP to see if it's extended
    if abs(hand_landmarks.landmark[4].x - hand_landmarks.landmark[5].x) > 0.05:
        fingers.append(1)
    else:
        fingers.append(0)

    # 2. FOUR FINGERS LOGIC
    # We compare the Tip Y-coordinate with the PIP Y-coordinate.
    # Note: In MediaPipe, Y decreases as you go UP the screen.
    finger_tips = [8, 12, 16, 20]
    finger_pips = [6, 10, 14, 18]

    for tip, pip in zip(finger_tips, finger_pips):
        if hand_landmarks.landmark[tip].y < hand_landmarks.landmark[pip].y:
            fingers.append(1) # Finger is up
        else:
            fingers.append(0) # Finger is down

    # ---------------- GESTURE MAPPING ---------------- #
    total_fingers = sum(fingers)

    # ROCK: All fingers closed
    if total_fingers == 0:
        return "Rock ✊"
    
    # PAPER: All fingers open (or at least 4)
    elif total_fingers >= 4:
        return "Paper ✋"

    # SCISSORS: Only Index and Middle are up
    elif fingers[1] == 1 and fingers[2] == 1 and fingers[3] == 0 and fingers[4] == 0:
        return "Scissors ✌️"

    return "Detecting..."

# ---------------- MAIN LOOP ---------------- #

while True:
    success, img = cap.read()
    if not success:
        break

    img = cv2.flip(img, 1) # Mirror view
    img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    results = hands.process(img_rgb)

    gesture_text = "Show Hand"

    if results.multi_hand_landmarks:
        for hand_landmarks in results.multi_hand_landmarks:
            # Draw the skeleton
            mp_draw.draw_landmarks(
                img, 
                hand_landmarks, 
                mp_hands.HAND_CONNECTIONS,
                mp_draw.DrawingSpec(color=(0,0,255), thickness=2, circle_radius=2),
                mp_draw.DrawingSpec(color=(255,255,255), thickness=2)
            )

            gesture_text = detect_gesture(hand_landmarks)

    # UI Overlay
    cv2.rectangle(img, (0, 0), (350, 120), (0, 0, 0), -1) # Dark background for text
    cv2.putText(
        img, 
        gesture_text, 
        (20, 80), 
        cv2.FONT_HERSHEY_SIMPLEX, 
        1.5, 
        (0, 255, 0), 
        3
    )

    cv2.imshow("RPS Detector - Front & Back Support", img)

    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()