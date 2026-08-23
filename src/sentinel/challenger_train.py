"""CLI entry point: python -m sentinel.challenger_train."""

from sentinel.challenger import train_challenger

if __name__ == "__main__":
    model = train_challenger(
        seed=42, save_path=__import__("pathlib").Path("evaluation/challenger.pkl")
    )
    print(f"trained {model.version} on {model.trained_on}; shadow active on next make serve")
