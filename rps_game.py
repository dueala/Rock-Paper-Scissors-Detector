import cv2
import mediapipe as mp
import numpy as np
import random
import time
import threading
import sys

# ─────────────────────────────────────────────
# SETUP
# ─────────────────────────────────────────────
mp_hands = mp.solutions.hands
mp_draw  = mp.solutions.drawing_utils
mp_style = mp.solutions.drawing_styles

hands = mp_hands.Hands(
    max_num_hands=1,
    min_detection_confidence=0.75,
    min_tracking_confidence=0.6
)

cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH,  1280)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

# ─────────────────────────────────────────────
# AUDIO — Windows SAPI TTS (no installs needed)
# ─────────────────────────────────────────────
import subprocess, os

def speak(text):
    """Speak text using Windows built-in TTS via PowerShell — non-blocking."""
    def _run():
        ps_cmd = (
            f"Add-Type -AssemblyName System.Speech; "
            f"$s = New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            f"$s.Rate = 0; "   # -10 (slow) to 10 (fast), 0 = normal
            f"$s.Speak('{text}');"
        )
        subprocess.run(
            ["powershell", "-WindowStyle", "Hidden", "-Command", ps_cmd],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    threading.Thread(target=_run, daemon=True).start()

def play_countdown():
    """Say Rock … Paper … Scissors … Shoot! in sequence."""
    def _run():
        for word, delay in [("Rock", 0.9), ("Paper", 0.9),
                             ("Scissors", 1.0), ("Shoot!", 0.0)]:
            speak(word)
            time.sleep(delay)
    threading.Thread(target=_run, daemon=True).start()

def play_result(result):
    speak(result)

# ─────────────────────────────────────────────
# GESTURE DETECTION
# ─────────────────────────────────────────────
def detect_gesture(lm):
    # Finger tips vs PIP joints (y-axis: smaller = higher on screen)
    up = []
    # Thumb: compare tip x to IP x (mirror-aware)
    up.append(1 if lm[4].x < lm[3].x else 0)   # left-hand tip left of IP
    for tip, pip in zip([8, 12, 16, 20], [6, 10, 14, 18]):
        up.append(1 if lm[tip].y < lm[pip].y - 0.015 else 0)

    total = sum(up)
    idx, mid = up[1], up[2]

    if total == 0 or (total == 1 and up[0]):          return "Rock"
    if idx and mid and sum(up[3:]) == 0:               return "Scissors"
    if total >= 4:                                     return "Paper"
    return "Rock"   # fallback

# ─────────────────────────────────────────────
# COLOUR PALETTE  (human skin tones)
# ─────────────────────────────────────────────
# AI hand — warm peach/tan
AI_SKIN      = (147, 193, 235)   # BGR peach
AI_SKIN_MID  = (110, 155, 200)   # mid shadow
AI_SKIN_DARK = ( 72, 112, 160)   # dark outline / crease
AI_NAIL      = (210, 225, 245)   # pale nail
AI_NAIL_OUT  = (160, 175, 200)

# User hand — slightly deeper tan so both look distinct
U_SKIN       = (120, 170, 210)
U_SKIN_MID   = ( 85, 130, 175)
U_SKIN_DARK  = ( 50,  90, 135)
U_NAIL       = (195, 215, 235)

# ─────────────────────────────────────────────
# SHARED DRAWING PRIMITIVES
# ─────────────────────────────────────────────
def fcircle(img, cx, cy, r, fill, outline=None, ow=2):
    cv2.circle(img, (int(cx), int(cy)), max(1, int(r)), fill, -1)
    if outline:
        cv2.circle(img, (int(cx), int(cy)), max(1, int(r)), outline, ow)

def fellipse(img, cx, cy, rx, ry, angle, fill, outline=None, ow=2):
    cv2.ellipse(img, (int(cx), int(cy)), (max(1,int(rx)), max(1,int(ry))),
                angle, 0, 360, fill, -1)
    if outline:
        cv2.ellipse(img, (int(cx), int(cy)), (max(1,int(rx)), max(1,int(ry))),
                    angle, 0, 360, outline, ow)

def draw_segment(img, x1, y1, x2, y2, w, fill, outline, ow=2):
    """Thick bone segment with rounded caps."""
    cv2.line(img, (int(x1),int(y1)), (int(x2),int(y2)), fill, max(1,int(w)))
    cv2.line(img, (int(x1),int(y1)), (int(x2),int(y2)), outline, ow)
    fcircle(img, x1, y1, w*0.55, fill, outline, ow)
    fcircle(img, x2, y2, w*0.55, fill, outline, ow)

def draw_nail(img, tx, ty, w, angle_deg, fill, outline):
    """Small rounded nail at finger tip."""
    nr = max(2, int(w * 0.38))
    fellipse(img, tx, ty - nr, nr, max(1,int(nr*0.55)), angle_deg, fill, outline, 1)

def human_finger(img, joints, widths, skin, skin_dark, nail_fill, nail_out):
    """
    Draw a realistic multi-segment finger.
    joints  = list of (x,y) from base → tip  (3 or 4 points)
    widths  = thickness at each segment
    """
    n = len(joints)
    for i in range(n - 1):
        x1, y1 = joints[i]
        x2, y2 = joints[i+1]
        w = widths[i]
        # Base colour fill
        draw_segment(img, x1, y1, x2, y2, w, skin, skin_dark, 2)
        # Subtle mid-tone highlight on upper half
        mx, my = (x1+x2)/2, (y1+y2)/2
        cv2.line(img, (int(x1),int(y1)), (int(mx),int(my)),
                tuple(min(255, c+25) for c in skin), max(1,int(w*0.35)))
    # Knuckle bumps
    for i in range(1, n-1):
        fcircle(img, joints[i][0], joints[i][1], widths[i]*0.7,
                tuple(max(0, c-15) for c in skin), skin_dark, 1)
    # Nail at tip
    tx, ty = joints[-1]
    dx = joints[-1][0] - joints[-2][0]
    dy = joints[-1][1] - joints[-2][1]
    angle = int(np.degrees(np.arctan2(dy, dx)))
    draw_nail(img, tx, ty, widths[-1]*1.4, angle, nail_fill, nail_out)

# ─────────────────────────────────────────────
# AI HAND  (illustrated, facing player)
# ─────────────────────────────────────────────
def draw_ai_hand(img, move, cx, cy, scale=1.0):
    """
    Illustrated human-style hand for the AI.
    Drawn facing RIGHT (thumb on right side, fingers pointing up).
    cx,cy = palm centre.
    """
    s = scale
    sk, skm, skd = AI_SKIN, AI_SKIN_MID, AI_SKIN_DARK
    nf, no = AI_NAIL, AI_NAIL_OUT

    # ── Palm (layered ellipses for depth) ────────────────────────
    fellipse(img, cx, cy,       int(82*s), int(72*s), 0, skm)
    fellipse(img, cx, cy-int(5*s), int(76*s), int(65*s), 0, sk, skd, 2)

    # ── Wrist ────────────────────────────────────────────────────
    wy = cy + int(68*s)
    fellipse(img, cx, wy, int(52*s), int(26*s), 0, sk, skd, 2)
    # wrist crease lines
    for off in [-1, 1]:
        cv2.line(img,
            (cx - int(40*s), wy + off*int(4*s)),
            (cx + int(40*s), wy + off*int(4*s)),
            skd, 1)

    # ── Finger base x-offsets (pinky→index, left to right) ───────
    # format: (palm_ox, palm_oy)  relative to cx,cy
    base_offsets = [(-52,-28), (-22,-42), (10,-44), (40,-38)]
    # finger lengths per phalanx [prox, mid, tip]
    lengths = {
        "index":   [int(v*s) for v in [38, 30, 22]],
        "middle":  [int(v*s) for v in [42, 32, 24]],
        "ring":    [int(v*s) for v in [36, 28, 20]],
        "pinky":   [int(v*s) for v in [24, 18, 14]],
    }
    widths_open = {
        "index":  [int(v*s) for v in [13, 11, 9]],
        "middle": [int(v*s) for v in [14, 12, 9]],
        "ring":   [int(v*s) for v in [12, 10, 8]],
        "pinky":  [int(v*s) for v in [9,   8, 6]],
    }
    finger_names = ["pinky","ring","middle","index"]

    def straight_finger(name, bx, by, angle_deg):
        lens = lengths[name]
        wids = widths_open[name]
        rad  = np.radians(angle_deg)
        pts  = [(bx, by)]
        x, y = bx, by
        for l in lens:
            x += int(np.cos(rad)*l)
            y += int(np.sin(rad)*l)
            pts.append((x, y))
        human_finger(img, pts, wids, sk, skd, nf, no)

    def curled_finger(name, bx, by, angle_deg):
        """Finger bent down — draw as fat knuckle bump only."""
        wids = widths_open[name]
        fcircle(img, bx, by, wids[0]*1.1, skm, skd, 2)
        # second knuckle peeking
        rad  = np.radians(angle_deg)
        kx   = bx + int(np.cos(rad)*wids[0]*1.4)
        ky   = by + int(np.sin(rad)*wids[0]*1.4)
        fcircle(img, kx, ky, wids[1]*0.9, sk, skd, 1)

    if move == "Rock":
        # All fingers curled, thumb over
        angles = [-95, -92, -90, -88]
        for i, (ox, oy) in enumerate(base_offsets):
            bx = cx + int(ox*s);  by = cy + int(oy*s)
            curled_finger(finger_names[i], bx, by, angles[i])
        # Thumb — short, angled across fist
        tx = cx + int(72*s);  ty = cy + int(5*s)
        t_pts = [(tx, ty),
                 (tx + int(18*s), ty - int(14*s)),
                 (tx + int(30*s), ty - int(22*s))]
        human_finger(img, t_pts, [int(v*s) for v in [16,13,10]], sk, skd, nf, no)

    elif move == "Paper":
        # All fingers up, natural spread
        angles = [-100, -95, -90, -84]
        for i, (ox, oy) in enumerate(base_offsets):
            bx = cx + int(ox*s);  by = cy + int(oy*s)
            straight_finger(finger_names[i], bx, by, angles[i])
        # Thumb — pointing out to right
        tx = cx + int(68*s);  ty = cy + int(18*s)
        t_pts = [(cx + int(50*s), ty + int(10*s)),
                 (tx,              ty),
                 (tx + int(24*s),  ty - int(16*s))]
        human_finger(img, t_pts, [int(v*s) for v in [16,13,10]], sk, skd, nf, no)

    elif move == "Scissors":
        # Index + middle up, ring + pinky curled
        angles = [-100, -95, -90, -84]
        for i, (ox, oy) in enumerate(base_offsets):
            bx = cx + int(ox*s);  by = cy + int(oy*s)
            if finger_names[i] in ("index","middle"):
                straight_finger(finger_names[i], bx, by, angles[i])
            else:
                curled_finger(finger_names[i], bx, by, angles[i])
        # Thumb curled in
        tx = cx + int(60*s);  ty = cy + int(10*s)
        fcircle(img, tx, ty, int(14*s), skm, skd, 2)

    # Palm crease lines for realism
    cv2.line(img,
        (cx - int(55*s), cy + int(10*s)),
        (cx + int(30*s), cy - int(20*s)),
        skd, max(1, int(1.5*s)))
    cv2.line(img,
        (cx - int(50*s), cy + int(28*s)),
        (cx + int(40*s), cy + int(5*s)),
        skd, max(1, int(1.5*s)))

# ─────────────────────────────────────────────
# USER HAND  (skin-coloured silhouette tracking real landmarks)
# ─────────────────────────────────────────────
def draw_user_hand(canvas, landmarks, h, w):
    """
    Draw the user's hand as a fleshy skin-tone silhouette that
    exactly follows the MediaPipe landmark positions.
    """
    pts = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]
    sk, skm, skd = U_SKIN, U_SKIN_MID, U_SKIN_DARK
    nf, no = U_NAIL, U_SKIN_DARK

    # Bone thicknesses  [wrist→MCP, MCP→PIP, PIP→DIP, DIP→TIP]
    # Indexed by landmark pairs
    BONE_W = {
        # Thumb
        (0,1):18, (1,2):16, (2,3):14, (3,4):12,
        # Index
        (0,5):16, (5,6):14, (6,7):12, (7,8):10,
        # Middle
        (0,9):17, (9,10):15,(10,11):13,(11,12):11,
        # Ring
        (0,13):15,(13,14):13,(14,15):11,(15,16): 9,
        # Pinky
        (0,17):13,(17,18):11,(18,19): 9,(19,20): 8,
        # Palm connectors
        (5,9):15, (9,13):15,(13,17):13,
    }

    overlay = canvas.copy()

    # 1) Wide pass — fat bones to fill palm area
    for (a, b), bw in BONE_W.items():
        cv2.line(overlay, pts[a], pts[b], sk, bw*2)

    # 2) Joint blobs at each landmark
    joint_r = [14,12,11,10, 9,
               13,11,10, 9,
               14,12,10, 9,
               12,10, 9, 8,
               11, 9, 8, 7]
    for i, pt in enumerate(pts):
        r = joint_r[i] if i < len(joint_r) else 8
        cv2.circle(overlay, pt, r, sk, -1)

    cv2.addWeighted(overlay, 1.0, canvas, 0.0, 0, canvas)

    # 3) Refined coloured bones on top
    for (a, b), bw in BONE_W.items():
        x1,y1 = pts[a]; x2,y2 = pts[b]
        cv2.line(canvas, (x1,y1), (x2,y2), sk,  bw)
        cv2.line(canvas, (x1,y1), (x2,y2), skd,  2)
        # highlight stripe
        mx,my = (x1+x2)//2, (y1+y2)//2
        cv2.line(canvas, (x1,y1), (mx,my),
                 tuple(min(255,c+30) for c in sk), max(1,bw//3))

    # 4) Knuckle circles
    for i, pt in enumerate(pts):
        r = joint_r[i] if i < len(joint_r) else 8
        cv2.circle(canvas, pt, r,  sk,  -1)
        cv2.circle(canvas, pt, r,  skd,  2)

    # 5) Nails at finger tips  [4,8,12,16,20]
    tip_ids = [4, 8, 12, 16, 20]
    sub_ids = [3, 7, 11, 15, 19]
    for tip, sub in zip(tip_ids, sub_ids):
        tx,ty = pts[tip]; sx,sy = pts[sub]
        dx,dy = tx-sx, ty-sy
        ang = int(np.degrees(np.arctan2(dy,dx)))
        nr  = max(3, joint_r[tip] if tip < len(joint_r) else 7)
        fellipse(canvas, tx, ty, nr, max(2,int(nr*0.6)), ang, nf, skd, 1)

    # 6) Palm crease lines
    # Life line (thumb base to wrist)
    cv2.line(canvas, pts[1], pts[0], skd, 1)
    # Heart line across knuckles
    cv2.line(canvas, pts[5], pts[17], skd, 1)

# ─────────────────────────────────────────────
# GAME STATE
# ─────────────────────────────────────────────
user_score    = 0
cpu_score     = 0
game_state    = "waiting"   # waiting | countdown | hold | result
countdown_start = 0
hold_start    = 0
cpu_move      = "Rock"
result_text   = ""
result_color  = (30, 30, 30)
current_move  = "Rock"

# Countdown phases: each lasts ~0.9 s → total ~3.6 s before "shoot"
PHASES   = ["rock", "paper", "scissors", "shoot"]
PHASE_T  = 0.85   # seconds per word

# ─────────────────────────────────────────────
# UI HELPERS
# ─────────────────────────────────────────────
FONT = cv2.FONT_HERSHEY_DUPLEX

def text_center(img, text, y, size, color, thickness=2):
    h, w = img.shape[:2]
    (tw, th), _ = cv2.getTextSize(text, FONT, size, thickness)
    cv2.putText(img, text, (w // 2 - tw // 2, y), FONT, size, color, thickness, cv2.LINE_AA)

def put_text(img, text, x, y, size, color, thickness=2):
    cv2.putText(img, text, (x, y), FONT, size, color, thickness, cv2.LINE_AA)

# ─────────────────────────────────────────────
# MAIN LOOP
# ─────────────────────────────────────────────
print("=== Rock Paper Scissors ===")
print("SPACE = start round   |   R = reset scores   |   Q = quit")

while True:
    ok, frame = cap.read()
    if not ok:
        break

    frame = cv2.flip(frame, 1)
    fh, fw = frame.shape[:2]

    # White canvas
    canvas = np.ones((fh, fw, 3), dtype=np.uint8) * 238

    # Subtle vertical divider
    cv2.line(canvas, (fw // 2, 60), (fw // 2, fh - 60), (190, 190, 190), 2)

    # ── Hand detection ──────────────────────────────────────────────
    results = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))

    hand_detected = False
    if results.multi_hand_landmarks:
        for hl in results.multi_hand_landmarks:
            hand_detected = True
            lms = hl.landmark
            current_move = detect_gesture(lms)

            # Draw real hand silhouette on RIGHT side
            # Build per-landmark lists for drawing
            draw_user_hand(canvas, lms, fh, fw)

    # ── AI cartoon hand on LEFT ─────────────────────────────────────
    ai_display = cpu_move if game_state == "result" else "Rock"
    ai_cx = fw // 4
    ai_cy = fh // 2
    draw_ai_hand(canvas, ai_display, ai_cx, ai_cy, scale=1.3)

    # ── Game logic ──────────────────────────────────────────────────
    key = cv2.waitKey(1) & 0xFF

    if key == ord(' ') and game_state in ("waiting", "result"):
        game_state = "countdown"
        countdown_start = time.time()
        result_text = ""
        play_countdown()

    if key == ord('r'):
        user_score = cpu_score = 0
        game_state = "waiting"

    if game_state == "countdown":
        elapsed = time.time() - countdown_start
        phase_idx = int(elapsed / PHASE_T)

        if phase_idx < len(PHASES):
            label = PHASES[phase_idx].upper()
            # Big phase label
            text_center(canvas, label, fh // 2 + 30, 3.5, (30, 30, 30), 8)
            # Progress dots
            for i, p in enumerate(PHASES):
                dot_color = (30, 30, 30) if i <= phase_idx else (190, 190, 190)
                dot_x = fw // 2 - int(len(PHASES) / 2 * 30) + i * 35
                cv2.circle(canvas, (dot_x, fh - 40), 7, dot_color, -1)
        else:
            # Transition to HOLD phase
            game_state = "hold"
            hold_start = time.time()
            cpu_move = random.choice(["Rock", "Paper", "Scissors"])

    if game_state == "hold":
        elapsed = time.time() - hold_start
        remain  = max(0, 1.0 - elapsed)
        text_center(canvas, f"HOLD!  {remain:.1f}s", fh // 2 + 30, 2.0, (30, 30, 30), 5)
        if elapsed >= 1.0:
            # Evaluate
            u, c = current_move, cpu_move
            if u == c:
                result_text = "DRAW"; result_color = (100, 100, 100)
                play_result("Draw!")
            elif (u == "Rock"     and c == "Scissors") or \
                 (u == "Paper"    and c == "Rock")     or \
                 (u == "Scissors" and c == "Paper"):
                result_text = "YOU WIN!"; result_color = (20, 120, 20)
                user_score += 1; play_result("You win!")
            else:
                result_text = "CPU WINS"; result_color = (160, 20, 20)
                cpu_score  += 1; play_result("Computer wins!")
            game_state = "result"

    # ── Score bar ───────────────────────────────────────────────────
    put_text(canvas, "CPU",  fw // 4 - 40,  45, 0.85, (100, 100, 100))
    put_text(canvas, "YOU", 3 * fw // 4 - 30, 45, 0.85, (100, 100, 100))
    text_center(canvas, f"{cpu_score}  :  {user_score}", 48, 1.3, (30, 30, 30), 3)

    # ── Result banner ───────────────────────────────────────────────
    if game_state == "result":
        # Show what each played
        put_text(canvas, ai_display.upper(),  fw // 4 - 50, fh - 30, 0.85, (80, 80, 80))
        put_text(canvas, current_move.upper(), 3*fw//4 - 50, fh - 30, 0.85, (80, 80, 80))
        text_center(canvas, result_text, fh // 2 - 20, 2.8, result_color, 7)
        text_center(canvas, "SPACE to play again", fh - 15, 0.7, (150, 150, 150))

    # ── Waiting / hints ─────────────────────────────────────────────
    if game_state == "waiting":
        text_center(canvas, "PRESS SPACE TO START", fh // 2 + 30, 1.2, (130, 130, 130), 3)
        if not hand_detected:
            text_center(canvas, "Show your hand to the camera", fh // 2 + 80, 0.8, (170, 170, 170))

    # ── Current move indicator (top right) ─────────────────────────
    if hand_detected and game_state in ("waiting", "result"):
        move_label = f"Detected: {current_move}"
        put_text(canvas, move_label, fw - 280, fh - 20, 0.7, (100, 100, 180))

    cv2.imshow("Rock Paper Scissors", canvas)

    if key == ord('q'):
        break

cap.release()
cv2.destroyAllWindows()
