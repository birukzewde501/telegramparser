import os
import re
import json
import urllib.request
import config

MODEL_POOL = [
    "gemini-3.6-flash",
    "gemini-flash-latest",
    "gemini-2.5-flash-lite",
]

def process_post_with_gemini(raw_text: str, custom_markup: int = None) -> str:
    """
    Uses Google Gemini API to clean, extract parameters, strip old contact info,
    apply price markup, remove all competitor links/locations, and format into Bless Computers listing.
    """
    broker_phone = config.get_broker_phone()
    broker_handle = config.get_broker_handle()
    price_markup = custom_markup if custom_markup is not None else config.get_price_markup()

    markup_instruction = ""
    if price_markup > 0:
        markup_instruction = f"- PRICE ADJUSTMENT: Add +{price_markup:,} Birr (ETB) to the original item price. (Example: if original price is 18,500 Birr, list it as {18500 + price_markup:,} Birr). Do NOT mention that a markup was added."
    elif price_markup < 0:
        markup_instruction = f"- PRICE ADJUSTMENT: Subtract {abs(price_markup):,} Birr (ETB) from the original item price. Do NOT mention that a discount was added."
    else:
        markup_instruction = "- Keep exact original item pricing."

    prompt = f"""
You are an expert tech copywriter and sales assistant for "Bless Computers".
Your task is to take any raw computer/laptop listing, completely strip out ALL competitor branding, remove ALL external links, and rewrite it into a clean, high-converting sales post for Telegram.

### STRICT RULES:
1. Rebrand Completely:
   - Header must be "💻 Bless Computers"
   - NEVER mention the original store, channel, or competitor name (e.g., "Phoenix Store").

2. ZERO Competitor Links, Websites, Channels, or Handles:
   - ABSOLUTELY NO external links, website URLs, or competitor channels.
   - Completely REMOVE lines like "View Full Details on Website", "Join Our Telegram Channel", "Visit Our Website", "Order Now", "t.me", "https://", "www.".
   - Completely REMOVE all competitor phone numbers, external usernames, Telegram handles, and web links.
   - Completely REMOVE all physical locations, addresses, landmarks, cities, building names, and shop numbers (e.g., Bole, Megenagna, Piassa, Dembel, 4 Kilo, building floors, etc.).
   - The ONLY contact phone permitted is: {broker_phone}
   - Contact Telegram handle: {broker_handle}

3. Hardware Specs:
   - Clearly list all technical specifications with clean emojis:
     • Model & Series
     • CPU / Processor
     • RAM
     • Storage (SSD / HDD)
     • Graphics / GPU
     • Display / Screen size
     • Battery health / life
     • Condition / OS
     • Any special features

4. Pricing & Final Polish:
   {markup_instruction}
   - List the price clearly (e.g. 💰 Price: 23,500 Birr). Do NOT repeat "Birr Birr".
   - Do NOT write "Price markup applied"! Just output the final price.
   - Include direct Call to Action at the bottom:
     📞 Call: {broker_phone}
     💬 Telegram: {broker_handle}

5. Output Format:
   - Return ONLY the final formatted post text ready to publish.
   - Do NOT include markdown code fences (no ```).
   - Do NOT include any conversational commentary or explanations.

Raw Listing to Process:
\"\"\"
{raw_text}
\"\"\"
"""

    api_key = config.GEMINI_API_KEY.strip() if config.GEMINI_API_KEY else ""

    if api_key and not api_key.startswith("AIzaSyYour"):
        # Iterate through working models
        for model in MODEL_POOL:
            # 1. Try direct HTTP REST API via urllib
            try:
                url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
                payload = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode("utf-8")
                req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
                
                with urllib.request.urlopen(req, timeout=12) as resp:
                    result_data = json.loads(resp.read().decode("utf-8"))
                    if "candidates" in result_data and result_data["candidates"]:
                        output = result_data["candidates"][0]["content"]["parts"][0]["text"].strip()
                        if output:
                            return clean_gemini_output(output, broker_phone, broker_handle)
            except Exception as e:
                # Log model attempt and try next in pool
                print(f"[Gemini Notice] Model {model} REST failed: {e}. Trying next...")

            # 2. Try google-genai SDK fallback
            try:
                from google import genai
                os.environ["GEMINI_API_KEY"] = api_key
                client = genai.Client(api_key=api_key)
                response = client.models.generate_content(
                    model=model,
                    contents=prompt,
                )
                output = response.text.strip()
                if output:
                    return clean_gemini_output(output, broker_phone, broker_handle)
            except Exception as e:
                print(f"[Gemini Notice] Model {model} SDK failed: {e}.")

    print("[Gemini Warning] API unreachable or keys invalid. Using hardened fallback cleaner.")
    return fallback_cleaner(raw_text, price_markup)

def clean_gemini_output(output: str, broker_phone: str, broker_handle: str) -> str:
    """Extra safety pass on Gemini output to ensure zero code fences or rogue links leaked."""
    # Clean code fences
    if output.startswith("```"):
        lines = output.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        output = "\n".join(lines).strip()

    # Safety: Strip any rogue URL or competitor handle that Gemini might have hallucinated
    url_pattern = re.compile(r'https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+', re.IGNORECASE)
    output = url_pattern.sub('', output)

    # Ensure duplicate "Birr Birr" is cleaned
    output = re.sub(r'(?i)\bbirr\s+birr\b', 'Birr', output)

    # Ensure markup text never appears
    output = re.sub(r'(?i)[*💡]*\s*Price markup applied.*', '', output)

    return output.strip()

def fallback_cleaner(raw_text: str, price_markup: int = 0) -> str:
    """
    Hardened fallback cleaner: strips ALL URLs, markdown links, competitor store names,
    empty labels, and location references.
    """
    lines = raw_text.splitlines()
    cleaned_lines = []

    # Comprehensive regex patterns
    phone_pattern = re.compile(r'(\+?251|0)[\d\s-]{8,14}')
    handle_pattern = re.compile(r'@[A-Za-z0-9_]+')
    url_pattern = re.compile(r'https?://\S+|www\.\S+|t\.me/\S+|telegram\.me/\S+', re.IGNORECASE)
    markdown_link_pattern = re.compile(r'\[([^\]]+)\]\([^\)]+\)')

    # Banned competitor / junk lines (case-insensitive)
    banned_keywords = [
        "join our telegram", "telegram channel", "visit our website", "website for more",
        "view full details", "order now", "interested? order", "phoenix store",
        "quality electronics", "fair prices", "trusted service", "store",
        "አድራሻ", "address", "location", "ህንፃ", "ቢሮ", "ፎቅ", "መገናኛ", "ቦሌ", "ፒያሳ",
        "megenagna", "bole", "piassa", "dembel", "stadium", "shop", "floor"
    ]

    # Blank label patterns (e.g. "Inbox:", "Phone:", "Call:")
    blank_label_pattern = re.compile(r'^(💬|📞|☎️|📱)?\s*(inbox|phone|call|contact|telegram)\s*:\s*$', re.IGNORECASE)

    for line in lines:
        stripped = line.strip()
        lower = stripped.lower()

        # Skip headers / photo metadata
        if stripped.startswith("[") and ("photos" in stripped or "AM" in stripped or "PM" in stripped):
            continue

        # Skip competitor promotion / location lines
        if any(kw in lower for kw in banned_keywords):
            continue

        # Convert markdown links to pure text
        line = markdown_link_pattern.sub(r'\1', line)

        # Strip URLs, phone numbers, and @handles
        line = url_pattern.sub('', line)
        line = phone_pattern.sub('', line)
        line = handle_pattern.sub('', line)

        # Clean duplicate symbols or trailing colons
        line = re.sub(r'\*\*\s*\*\*', '', line)
        cleaned_line = line.strip()

        # Check if line became a blank label (e.g. "📞 Phone:" with no number)
        if blank_label_pattern.match(cleaned_line):
            continue

        # Price line adjustment in fallback
        if price_markup != 0 and re.search(r'(?i)(price|ዋጋ)\s*:', cleaned_line):
            match = re.search(r'([\d,]+)\s*(birr|etb)?', cleaned_line, re.IGNORECASE)
            if match:
                try:
                    num_str = match.group(1).replace(',', '')
                    old_price = int(num_str)
                    new_price = max(0, old_price + price_markup)
                    cleaned_line = re.sub(
                        r'([\d,]+)\s*(birr|etb)?',
                        f"{new_price:,} Birr",
                        cleaned_line,
                        flags=re.IGNORECASE
                    )
                except Exception:
                    pass

        # Clean duplicate "Birr Birr"
        cleaned_line = re.sub(r'(?i)\bbirr\s+birr\b', 'Birr', cleaned_line)

        if cleaned_line:
            cleaned_lines.append(cleaned_line)

    body = "\n".join(cleaned_lines).strip()

    return (
        "💻 **Bless Computers**\n\n"
        f"{body}\n\n"
        f"📞 Call: {config.get_broker_phone()}\n"
        f"💬 Telegram: {config.get_broker_handle()}"
    )
