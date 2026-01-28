import os

# Try to load .env if available
try:
    from dotenv import load_dotenv

    load_dotenv()
except Exception:
    pass

try:
    import google.generativeai as genai
except Exception as e:
    print(f"ERROR: google-generativeai not installed: {e}")
    raise

api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
if not api_key:
    # fallback: read .env directly
    try:
        with open(".env", "r") as f:
            for line in f:
                if line.strip().startswith("GEMINI_API_KEY="):
                    api_key = line.strip().split("=", 1)[1]
                    break
    except Exception:
        api_key = None

if not api_key:
    print("ERROR: No GEMINI_API_KEY found.")
else:
    genai.configure(api_key=api_key)
    print("Checking Tier 1 available models...")
    for m in genai.list_models():
        try:
            methods = getattr(m, "supported_generation_methods", []) or []
            name = getattr(m, "name", "")
            if "generateContent" in methods:
                simple = name.replace("models/", "")
                print(f"MODEL: {simple}")
        except Exception as e:
            print(f"SKIP: {e}")
