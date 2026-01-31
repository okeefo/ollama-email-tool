import os
import json
import subprocess

PROMPT_FILE = os.path.join("modelfiles", "prompt", "email-triage.system.txt")
MODELS_CONFIG = os.path.join("modelfiles", "models.json")
GENERATED_DIR = os.path.join("modelfiles", "generated")
DOCKER_CONTAINER = "ollama"


def _load_models_config():
    try:
        with open(MODELS_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Failed to read {MODELS_CONFIG}: {e}")
        return []


def _read_prompt():
    try:
        with open(PROMPT_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        print(f"Failed to read prompt file {PROMPT_FILE}: {e}")
        return ""


def _generate_modelfile(base: str, name: str, params: dict, prompt_text: str) -> str:
    os.makedirs(GENERATED_DIR, exist_ok=True)
    out_path = os.path.join(GENERATED_DIR, f"{name}.modelfile")
    temperature = params.get("temperature", 0.0)
    num_ctx = params.get("num_ctx", 1024)
    num_predict = params.get("num_predict", 80)

    content = (
        f"FROM {base}\n\n"
        f"PARAMETER temperature {temperature}\n"
        f"PARAMETER num_ctx {num_ctx}\n"
        f"PARAMETER num_predict {num_predict}\n\n"
        'SYSTEM """\n'
        f"{prompt_text}\n"
        '"""\n'
    )
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(content)
    return out_path


def _docker_exec(cmd: list) -> int:
    try:
        return subprocess.call(["docker", "exec", "-i", DOCKER_CONTAINER] + cmd)
    except Exception as e:
        print(f"Docker exec failed: {e}")
        return 1


def _create_model(name: str) -> bool:
    mf_container_path = f"/modelfiles/generated/{name}.modelfile"
    rc = _docker_exec(["ollama", "create", name, "-f", mf_container_path])
    if rc == 0:
        print(f"Created model: {name}")
        return True
    print(f"Failed to create model: {name} (exit {rc})")
    return False


def _list_ollama_models():
    try:
        out = subprocess.check_output(
            ["docker", "exec", "-i", DOCKER_CONTAINER, "ollama", "list"]
        ).decode()
        print(out)
    except Exception as e:
        print(f"Failed to list Ollama models: {e}")


def _set_env_ollama_model(name: str):
    env_path = ".env"
    lines = []
    if os.path.exists(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
    found = False
    for i, line in enumerate(lines):
        if line.startswith("OLLAMA_MODEL="):
            lines[i] = f"OLLAMA_MODEL={name}\n"
            found = True
            break
    if not found:
        lines.append(f"OLLAMA_MODEL={name}\n")
    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)
    print(f"Set OLLAMA_MODEL={name} in .env")


def run_model_manager():
    models = _load_models_config()
    prompt_text = _read_prompt()
    if not models or not prompt_text:
        print("Missing models.json or prompt file.")
        return

    while True:
        print("\n" + "=" * 40)
        print(" Model Manager ")
        print("=" * 40)
        print("1. Build ALL models from config")
        print("2. Build SELECTED models from config")
        print("3. List models in Ollama")
        print("4. Select/start model (sets OLLAMA_MODEL)")
        print("E. Exit")
        choice = input("Select: ").strip().upper()

        if choice == "E":
            break
        elif choice == "1":
            for m in models:
                path = _generate_modelfile(
                    m["base"], m["name"], m.get("params", {}), prompt_text
                )
                print(f"Generated: {path}")
                _create_model(m["name"])  # create in container
            print("Build ALL complete.")
        elif choice == "2":
            print("\nAvailable models:")
            for i, m in enumerate(models, start=1):
                print(f" {i}. {m['name']}  (base: {m['base']})")
            raw = input("Enter number(s) comma-separated: ").strip()
            try:
                idxs = [int(x) for x in raw.split(",") if x.strip().isdigit()]
            except Exception:
                idxs = []
            if not idxs:
                print("No valid selection.")
                continue
            for i in idxs:
                if 1 <= i <= len(models):
                    m = models[i - 1]
                    path = _generate_modelfile(
                        m["base"], m["name"], m.get("params", {}), prompt_text
                    )
                    print(f"Generated: {path}")
                    _create_model(m["name"])  # create in container
            print("Selected builds complete.")
        elif choice == "3":
            _list_ollama_models()
        elif choice == "4":
            print("\nSelect model to use locally:")
            for i, m in enumerate(models, start=1):
                print(f" {i}. {m['name']}")
            raw = input("Enter number: ").strip()
            if not raw.isdigit():
                print("Invalid selection.")
                continue
            i = int(raw)
            if not (1 <= i <= len(models)):
                print("Out of range.")
                continue
            name = models[i - 1]["name"]
            _set_env_ollama_model(name)
            print("You can now run local tuner with this model.")
        else:
            print("Unknown option.")


if __name__ == "__main__":
    run_model_manager()
