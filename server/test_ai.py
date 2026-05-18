"""Quick test harness for AIBrain."""

from core.ai_brain import AIBrain


def main():
    brain = AIBrain()
    prompt = "Hello Cheeku, say hi in two languages and give a short joke."
    print("Prompt:", prompt)
    resp = brain.respond(prompt)
    print("Response:\n", resp)


if __name__ == "__main__":
    main()
