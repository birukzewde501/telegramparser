import os
import re
import config

def process_post_with_gemini(raw_text: str, custom_markup: int = None) -> str:
    """
    Uses Google Gemini API to clean, extract parameters, strip old contact info,
    apply price markup, and format the Telegram post into a high-converting broker listing.
    """
    broker_phone = config.get_broker_phone()
    broker_handle = config.get_broker_handle()
    price_markup = custom_markup if custom_markup is not None else config.get_price_markup()

    markup_instruction = ""
    if price_markup > 0:
        markup_instruction = f"5. PRICE ADJUSTMENT: Add +{price_markup:,} Birr (ETB) to the original item price. (For example: if original price is 45,000 Birr, list it as {45000 + price_markup:,} Birr)."
    elif price_markup < 0:
        markup_instruction = f"5. PRICE ADJUSTMENT: Subtract {abs(price_markup):,} Birr (ETB) from the original item price."
    else:
        markup_instruction = "5. PRICE ADJUSTMENT: Keep exact original item pricing."

    prompt = f"""
You are an expert tech copywriter and sales assistant for "Bless Computers".
Your task is to take any raw computer/laptop listing, strip out all competitor branding, remove all locations, and rewrite it into a clean, high-converting sales post for Telegram.

### STRICT RULES:
1. Rebrand Completely:
   - Replace any store name, channel handle, or watermark with "Bless Computers".
   - Never mention the original store, channel, or competitor name.

2. Sanitize Contacts & Strip Locations:
   - Completely REMOVE all physical locations, addresses, landmarks, cities, building names, and shop numbers (e.g., Bole, Megenagna, Piassa, Dembel, 4 Kilo, building floors, etc.). Do NOT mention ANY location whatsoever.
   - Strip out all competitor phone numbers, external usernames, Telegram handles, and web links.
   - The ONLY contact phone permitted is: {broker_phone}
   - Contact Telegram handle: {broker_handle}

3. Preserve Hardware Specs:
   - Extract and clearly list all technical specifications:
     • Model & Series
     • CPU / Processor
     • RAM
     • Storage (SSD / HDD)
     • Graphics / GPU
     • Display / Screen size & resolution
     • Battery health / life
     • Condition (Brand New, Open Box, or Like New / Clean)
     • Any special features (Touchscreen, Backlit Keyboard, Fingerprint, etc.)

4. Formatting & Polish:
   - Use clean typography with appropriate tech emojis (💻, ⚡️, 🚀, 🔋, 📞, 💰).
   - Create a strong, catchy headline highlighting the laptop model and "Bless Computers".
   - Present all specifications using scannable bullet points.
   - List the price clearly (in Birr / ETB).
   {markup_instruction}
   - Include a direct, energetic Call to Action at the bottom:
     📞 Call: {broker_phone}
     💬 Telegram: {broker_handle}

5. Language & Tone:
   - Match the primary language of the input post (English, Amharic, or standard mixed Ethiopian tech phrasing).
   - Keep the tone energetic, trustworthy, and professional.

6. Output Format:
   - Return ONLY the final formatted post text ready to publish.
   - Do NOT include markdown code fences (no ```).
   - Do NOT include any conversational commentary or explanations.

Raw Listing to Process:
\"\"\"
{raw_text}
\"\"\"
"""

    if not config.GEMINI_API_KEY or config.GEMINI_API_KEY.startswith("AIzaSyYour"):
        print("[Warning] GEMINI_API_KEY is missing or using default placeholder.")

    try:
        output = None
        # 1. Try direct HTTP REST API via urllib (works with all key types including cloud keys)
        try:
            import json
            import urllib.request
            
            url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={config.GEMINI_API_KEY}"
            payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
            
            with urllib.request.urlopen(req, timeout=15) as resp:
                result_data = json.loads(resp.read().decode("utf-8"))
                if "candidates" in result_data and result_data["candidates"]:
                    output = result_data["candidates"][0]["content"]["parts"][0]["text"].strip()
        except Exception as rest_err:
            # 2. Try google-genai SDK fallback
            try:
                from google import genai
                if config.GEMINI_API_KEY:
                    os.environ["GEMINI_API_KEY"] = config.GEMINI_API_KEY
                client = genai.Client()
                response = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=prompt,
                )
                output = response.text.strip()
            except Exception:
                pass

        if output:
            # Clean code fences if Gemini included them
            if output.startswith("```"):
                lines = output.splitlines()
                if lines[0].startswith("```"):
                    lines = lines[1:]
                if lines and lines[-1].startswith("```"):
                    lines = lines[:-1]
                output = "\n".join(lines).strip()
            return output

    except Exception as e:
        print(f"[Gemini Error] Failed to process post with Gemini: {e}")

    # Fallback basic cleaner in case of API error or offline
    return fallback_cleaner(raw_text, price_markup)

def fallback_cleaner(raw_text: str, price_markup: int = 0) -> str:
    """Basic fallback text manipulation if Gemini API is unreachable."""
    lines = raw_text.splitlines()
    cleaned_lines = []
    
    # Simple regex to strip phone numbers and handles
    phone_pattern = re.compile(r'(\+?251|0)[\d\s-]{8,12}')
    handle_pattern = re.compile(r'@[A-Za-z0-9_]+')
    location_keywords = [
        "አድራሻ", "address", "location", "ህንፃ", "ቢሮ", "ፎቅ", "መገናኛ", "ቦሌ", "ፒያሳ",
        "megenagna", "bole", "piassa", "dembel", "stadium", "shop", "floor"
    ]

    for line in lines:
        lower = line.lower()
        if line.startswith("[") and ("photos" in line or "AM" in line or "PM" in line):
            continue
        # Skip location lines in fallback
        if any(kw in lower for kw in location_keywords):
            continue
        # Strip phone numbers and @handles from raw lines
        line = phone_pattern.sub('', line)
        line = handle_pattern.sub('', line)
        cleaned_lines.append(line)
    
    body = "\n".join([l for l in cleaned_lines if l.strip()]).strip()
    
    markup_text = ""
    if price_markup != 0:
        markup_text = f"\n💡 *Price markup applied: {price_markup:+} Birr*"

    return (
        "💻 **Bless Computers**\n\n"
        f"{body}"
        f"{markup_text}\n\n"
        f"📞 Call: {config.get_broker_phone()}\n"
        f"💬 Telegram: {config.get_broker_handle()}"
    )
