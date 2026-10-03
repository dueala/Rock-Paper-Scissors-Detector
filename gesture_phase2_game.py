import cv2
import mediapipe as mp
import numpy as np
import random
import time
import subprocess
import threading
import os
import tempfile

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
# AUDIO  (ffplay, non-blocking)
# ─────────────────────────────────────────────
SOUND_DIR = os.path.join(tempfile.gettempdir(), "rps_sounds")
os.makedirs(SOUND_DIR, exist_ok=True)

def gen_voice(text, filename):
    path = os.path.join(SOUND_DIR, filename)
    if not os.path.exists(path):
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi",
             "-i", f"flite=text='{text}':voice=rms",
             path],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
        )
    return path

SOUNDS = {
    "rock":     gen_voice("Rock",            "rock.wav"),
    "paper":    gen_voice("Paper",           "paper.wav"),
    "scissors": gen_voice("Scissors",        "scissors.wav"),
    "shoot":    gen_voice("Shoot!",          "shoot.wav"),
    "youwin":   gen_voice("You win!",        "youwin.wav"),
    "cpuwin":   gen_voice("Computer wins!",  "cpuwin.wav"),
    "draw":     gen_voice("Draw!",           "draw.wav"),
}

_audio_proc = None

def play_sound(key):
    global _audio_proc
    if _audio_proc and _audio_proc.poll() is None:
        _audio_proc.terminate()
    path = SOUNDS.get(key)
    if path and os.path.exists(path):
        _audio_proc = subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path]
        )

def play_countdown():
    """Say Rock … Paper … Scissors … Shoot! with timing gaps."""
    def _run():
        for word in ["rock", "paper", "scissors", "shoot"]:
            play_sound(word)
            time.sleep(0.9)
    threading.Thread(target=_run, daemon=True).start()

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
# CARTOON AI HAND DRAWING
# ─────────────────────────────────────────────
SKIN    = (100, 180, 255)   # warm orange-yellow
SKIN_D  = ( 60, 130, 200)   # darker for outline
NAIL    = (220, 230, 255)
LINE_W  = 3

def filled_circle(img, cx, cy, r, color, outline=None):
    cv2.circle(img, (int(cx), int(cy)), int(r), color, -1)
    if outline:
        cv2.circle(img, (int(cx), int(cy)), int(r), outline, LINE_W)

def filled_ellipse(img, cx, cy, ax, ay, angle, color, outline=None):
    cv2.ellipse(img, (int(cx), int(cy)), (int(ax), int(ay)),
                angle, 0, 360, color, -1)
    if outline:
        cv2.ellipse(img, (int(cx), int(cy)), (int(ax), int(ay)),
                    angle, 0, 360, outline, LINE_W)

def draw_finger(img, bx, by, length, width, angle_deg, bent=False, flip=False):
    """Draw one cartoon finger as a rounded rectangle."""
    sign = -1 if flip else 1
    rad  = np.radians(angle_deg)
    dx   = int(np.cos(rad) * length * sign)
    dy   = int(np.sin(rad) * length)
    ex, ey = bx + dx, by + dy
    cv2.line(img, (bx, by), (ex, ey), SKIN, int(width * 1.8))
    cv2.line(img, (bx, by), (ex, ey), SKIN_D, LINE_W)
    # Knuckle
    filled_circle(img, bx, by, width * 0.9, SKIN, SKIN_D)
    # Tip
    filled_circle(img, ex, ey, width * 0.85, SKIN, SKIN_D)
    # Nail on tip
    nail_r = int(width * 0.55)
    nrad   = np.radians(angle_deg + 90)
    cv2.ellipse(img,
        (int(ex), int(ey)),
        (nail_r, max(2, nail_r // 2)), angle_deg, 0, 360,
        NAIL, -1)

def draw_cartoon_hand(img, move, cx, cy, scale=1.0, facing_right=True):
    """
    Draw a colored cartoon hand for Rock / Paper / Scissors.
    cx, cy  = center of the palm
    facing_right = True means thumb points right (AI hand facing player)
    """
    s   = scale
    flip = not facing_right

    # ── Palm ──────────────────────────────────────────────────────
    pw, ph = int(90 * s), int(80 * s)
    filled_ellipse(img, cx, cy, pw, ph, 0, SKIN, SKIN_D)

    # ── Wrist ─────────────────────────────────────────────────────
    wy = cy + int(75 * s) if not flip else cy + int(75 * s)
    filled_ellipse(img, cx, wy, int(55 * s), int(30 * s), 0, SKIN, SKIN_D)

    sign = 1 if facing_right else -1

    if move == "Rock":
        # All fingers curled — just show rounded fist bumps
        knuckle_y = cy - int(40 * s)
        for i, ox in enumerate([-50, -20, 10, 40]):
            kx = cx + int(ox * s * sign)
            filled_circle(img, kx, knuckle_y, int(16 * s), SKIN, SKIN_D)
        # Thumb to side
        tx = cx + int(85 * s * sign)
        filled_circle(img, tx, cy - int(10 * s), int(18 * s), SKIN, SKIN_D)

    elif move == "Paper":
        # All four fingers up, slightly spread
        finger_data = [
            (-55, -45, 80,  14, -85),
            (-20, -50, 90,  14, -88),
            ( 15, -48, 90,  14, -88),
            ( 48, -42, 78,  13, -85),
        ]
        for ox, oy, length, width, angle in finger_data:
            bx = cx + int(ox * s * sign)
            by = cy + int(oy * s)
            draw_finger(img, bx, by, int(length * s), int(width * s), angle, flip=flip)
        # Thumb out to side
        tx = cx + int(85 * s * sign)
        ty = cy + int(10 * s)
        cv2.line(img, (cx + int(60*s*sign), ty), (tx, ty - int(20*s)),
                 SKIN, int(22 * s))
        filled_circle(img, tx, ty - int(20*s), int(15*s), SKIN, SKIN_D)

    elif move == "Scissors":
        # Index + middle up, others curled
        scissors_data = [
            (-30, -50, 90, 13, -82),
            (  5, -50, 90, 13, -82),
        ]
        for ox, oy, length, width, angle in scissors_data:
            bx = cx + int(ox * s * sign)
            by = cy + int(oy * s)
            draw_finger(img, bx, by, int(length * s), int(width * s), angle, flip=flip)
        # Curled ring + pinky bumps
        for ox in [38, 62]:
            filled_circle(img, cx + int(ox*s*sign), cy - int(30*s), int(13*s), SKIN, SKIN_D)
        # Thumb
        tx = cx + int(75 * s * sign)
        filled_circle(img, tx, cy + int(5*s), int(15*s), SKIN, SKIN_D)

# ─────────────────────────────────────────────
# DRAW USER HAND (real skeleton → silhouette)
# ─────────────────────────────────────────────
def draw_user_hand(canvas, landmarks, h, w):
    """
    Mirror the user's actual hand as a solid filled silhouette
    by connecting landmark positions into a filled polygon.
    """
    pts_raw = [(int(lm.x * w), int(lm.y * h)) for lm in landmarks]

    # Build hull-like outline of the hand
    # We'll draw thick lines between bones first, then fill
    connections = mp_hands.HAND_CONNECTIONS
    overlay = canvas.copy()

    # Draw filled fat skeleton (soft silhouette)
    for conn in connections:
        p1 = pts_raw[conn[0]]
        p2 = pts_raw[conn[1]]
        cv2.line(overlay, p1, p2, (30, 30, 30), 28)

    # Draw circles at each joint
    for pt in pts_raw:
        cv2.circle(overlay, pt, 14, (30, 30, 30), -1)

    # Blend to soften
    cv2.addWeighted(overlay, 0.9, canvas, 0.1, 0, canvas)

    # Draw refined skeleton on top for detail
    mp_draw.draw_landmarks(
        canvas, 
        type('obj', (object,), {'landmark': landmarks})(),
        mp_hands.HAND_CONNECTIONS,
        mp_draw.DrawingSpec(color=(200, 200, 200), thickness=1, circle_radius=2),
        mp_draw.DrawingSpec(color=(160, 160, 160), thickness=1)
    )

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
    draw_cartoon_hand(canvas, ai_display, ai_cx, ai_cy, scale=1.3, facing_right=True)

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
                play_sound("draw")
            elif (u == "Rock"     and c == "Scissors") or \
                 (u == "Paper"    and c == "Rock")     or \
                 (u == "Scissors" and c == "Paper"):
                result_text = "YOU WIN!"; result_color = (20, 120, 20)
                user_score += 1; play_sound("youwin")
            else:
                result_text = "CPU WINS"; result_color = (160, 20, 20)
                cpu_score  += 1; play_sound("cpuwin")
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
if _audio_proc and _audio_proc.poll() is None:
    _audio_proc.terminate()