# ✋ Gesture-Based Rock Paper Scissors

A real-time computer vision Rock Paper Scissors game that uses a webcam and hand gesture recognition to let you play against a computer opponent.

The project uses **Python, OpenCV, and MediaPipe** to detect the player's hand, recognize Rock, Paper, or Scissors, and turn the detected gesture into an interactive game.

## 🎮 Features

- ✋ Real-time hand gesture recognition
- 📷 Webcam-based interaction
- 🧠 Computer opponent with randomized moves
- 🪨 Rock, Paper, Scissors gesture detection
- ⏱️ Interactive countdown: Rock → Paper → Scissors → Shoot
- 🏆 Automatic win, loss, and draw detection
- 📊 Real-time score tracking
- 🔊 Voice feedback for countdown and game results
- 🎨 Custom AI hand visualization
- 🖐️ Real-time visualization of the user's detected hand
- 🔄 Score reset and replay functionality

## 🛠️ Technologies Used

- **Python**
- **OpenCV**
- **MediaPipe**
- **NumPy**

## 🧠 How It Works

The webcam captures the player's hand in real time.

MediaPipe detects **21 hand landmarks**, which are used to determine which fingers are extended.

The detected finger configuration is then mapped to a gesture:

| Gesture | Hand Configuration |
|---|---|
| ✊ Rock | Fingers closed |
| ✋ Paper | Most/all fingers extended |
| ✌️ Scissors | Index and middle fingers extended |

The computer randomly selects its own move, and the game compares both moves to determine the result.

## 🎮 Game Flow

1. Start the game.
2. Show your hand to the webcam.
3. Press **SPACE** to begin a round.
4. Follow the countdown:
   - ROCK
   - PAPER
   - SCISSORS
   - SHOOT!
5. Your hand gesture is detected.
6. The computer selects its move.
7. The game determines the winner.
8. Your score is updated.
9. Press **SPACE** to play again.

## ⌨️ Controls

| Key | Action |
|---|---|
| `SPACE` | Start a round / Play again |
| `R` | Reset scores |
| `Q` | Quit the game |

## 🚀 Installation

### 1. Clone the repository
2. Install dependencies
pip install opencv-python mediapipe numpy
3. Run the game
python rps_game.py

```bash
git clone https://github.com/dueala/gesture-rock-paper-scissors.git
cd gesture-rock-paper-scissors
