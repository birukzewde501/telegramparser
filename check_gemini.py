import os
import sys
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY", "").strip()

print("=" * 60)
print("🔑 GOOGLE GEMINI API KEY & MODEL DIAGNOSTIC SCRIPT")
print("=" * 60)

if not api_key:
    print("❌ ERROR: GEMINI_API_KEY is missing from your .env file!")
    print("👉 Get a free key at: https://aistudio.google.com/app/apikey")
    sys.exit(1)

print(f"📌 Key in .env: {api_key[:10]}...{api_key[-4:]} (Length: {len(api_key)})")

# Test 1: legacy google-generativeai package
print("\n[TEST 1] Testing with `google.generativeai` package...")
try:
    import google.generativeai as genai_legacy
    genai_legacy.configure(api_key=api_key)
    models = list(genai_legacy.list_models())
    print(f"✅ Success! Found {len(models)} models available:")
    for m in models:
        if 'generateContent' in m.supported_generation_methods:
            print(f" • {m.name}")
            
    print("\n🧪 Testing content generation with `gemini-1.5-flash`...")
    m = genai_legacy.GenerativeModel('gemini-1.5-flash')
    res = m.generate_content("Respond with: 'Legacy SDK Working!'")
    print(f"🤖 Response: {res.text.strip()}")
    print("🎉 SUCCESS with legacy SDK!\n")
except Exception as e:
    print(f"❌ Legacy SDK Error: {e}\n")

# Test 2: new google-genai package
print("[TEST 2] Testing with new `google.genai` package...")
try:
    from google import genai
    client = genai.Client(api_key=api_key)
    res = client.models.generate_content(
        model='gemini-2.0-flash',
        contents="Respond with: 'New SDK Working!'"
    )
    print(f"🤖 Response: {res.text.strip()}")
    print("🎉 SUCCESS with new SDK!\n")
except Exception as e:
    print(f"❌ New SDK Error: {e}\n")

print("=" * 60)
print("👉 If both tests failed with 'API key not valid':")
print("   1. Open: https://aistudio.google.com/app/apikey")
print("   2. Click 'Create API key'")
print("   3. Copy the NEW key into your .env file as GEMINI_API_KEY=AIzaSy...")
print("=" * 60)
