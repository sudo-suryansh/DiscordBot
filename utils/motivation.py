import random

OPENERS = [
    "Hey {name}, welcome aboard! 🚀",
    "Yo {name}! Glad you're here. 👋",
    "Welcome to the grind, {name}. 💪",
    "{name}, great to have you with us! ✨",
    "Hey {name} — you just leveled up your journey. 🎮",
]

BODIES = [
    "Every expert coder was once a beginner staring at a blank editor. You've already taken the hardest step — showing up.",
    "Arrays, trees, graphs — they all seemed impossible once. Give it a few weeks of consistent practice and they'll feel like muscle memory.",
    "Consistency beats intensity. Solve one problem a day here and in a few months you'll barely recognize how far you've come.",
    "DSA isn't about being naturally smart — it's about pattern recognition built through reps. You're in the right place to build that.",
    "The people who make it aren't the ones who never struggle — they're the ones who keep showing up after a failed submission.",
    "Every 'Wrong Answer' is data, not defeat. Debugging your own logic is where the real learning happens.",
    "You don't need to solve the hardest problem today. You need to solve one problem better than you did yesterday.",
]

CLOSERS = [
    "Drop your first question in the server whenever you're ready — we've got you.",
    "Jump into a channel, introduce yourself, and let's get you solving.",
    "Looking forward to seeing your name on the leaderboard soon.",
    "This community's here for exactly this — don't hesitate to ask anything.",
    "Let's turn confusion into confidence, one problem at a time.",
]


def generate_welcome_dm(display_name: str) -> str:
    """Builds a randomized, personalized motivational message.
    Different opener/body/closer combination each call, so it doesn't
    feel like a copy-pasted template even across many joins."""
    opener = random.choice(OPENERS).format(name=display_name)
    body = random.choice(BODIES)
    closer = random.choice(CLOSERS)
    return f"{opener}\n\n{body}\n\n{closer}"
