import google.generativeai as genai
from PIL import Image
import json
import re
import os
import csv
import time
import sys
from google.api_core.exceptions import ResourceExhausted

# Configure terminal output encoding to prevent Windows console Unicode crashes
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8")


# ============================================================
# CONFIG
# ============================================================
API_KEY    = "paste_your_api_key_here"
IMAGE_DIR  = r"C:\Users\HP\Desktop\automation\#ge-sp-marstrek\test"
OUTPUT_CSV = r"C:\Users\HP\Desktop\automation\day1_results_v2.csv"

# Load API key from .env if present
if os.path.exists(".env"):
    with open(".env", "r", encoding="utf-8") as env_file:
        for line in env_file:
            if line.strip().startswith("API_KEY"):
                parts = line.split("=", 1)
                if len(parts) == 2:
                    API_KEY = parts[1].strip().strip("'\"")
                    break

DISTANCE_MIN = 600.13
DISTANCE_MAX = 620.13
# ============================================================

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-2.5-flash-lite")

# ============================================================
# PROMPT — v2
# Three changes from v1:
#   1. Search panel check merged with lat/lon (same section)
#   2. URL bar visibility is now explicitly asked
#   3. Clearer instructions for each field
# ============================================================
PROMPT = """This is a NASA Solar System Trek screenshot showing a Mars 
surface measurement of Olympus Mons.

Carefully examine every part of the image and extract the following:

--- SECTION 1: BROWSER ADDRESS BAR (top of the screen) ---
Look at the URL in the browser address bar at the very top of the screenshot.
- Is the address bar visible at all? (address_bar_visible: true/false)
- If visible, find the x= and y= parameters in the URL and extract their values.
  Example URL: trek.nasa.gov/mars/#v=0.1&x=-120.289&y=18.720&z=4...
  url_x would be -120.289 and url_y would be 18.720
- If the address bar is NOT visible or x= / y= are not in the URL, set url_x and url_y to null.
- IMPORTANT: if url_x or url_y is exactly 0 or 0.0, treat it as null — it means the value was not found.

--- SECTION 2: LEFT SEARCH/INFO PANEL ---
Look at the left side panel of the screenshot.
- Is the panel showing information about Olympus Mons?
  It should display the text "Olympus Mons" as a heading/title. (olympus_mons_in_search_tab: true/false)
- If Olympus Mons info IS shown, extract the Latitude and Longitude values 
  from the panel. They appear as labelled fields like "Latitude: 18.65275889"
- If the panel is NOT showing Olympus Mons info (or is closed/hidden), 
  set latitude and longitude both to null.
- NOTE: latitude, longitude, and olympus_mons_in_search_tab are all from 
  the SAME panel section. If the panel is not showing Olympus Mons, 
  all three will be false/null.

--- SECTION 3: DISTANCE RESULT POPUP ---
Look for the Distance Result popup/dialog box in the screenshot.
- Extract the terrain distance value shown in km. (terrain_distance_km)
- If the popup is not visible or the value cannot be read, set to null.

--- SECTION 4: MARS MAP ---
Look at the Mars surface map on the right side of the screenshot.
- Is there a yellow/orange measurement line drawn across the volcano? 
  (measurement_line_visible: true/false)

Return ONLY this JSON. No explanation. No markdown. Raw JSON only:
{
  "address_bar_visible": <true or false>,
  "url_x": <decimal number from URL x= parameter, or null>,
  "url_y": <decimal number from URL y= parameter, or null>,
  "olympus_mons_in_search_tab": <true or false>,
  "latitude": <decimal number from left panel, or null>,
  "longitude": <decimal number from left panel, or null>,
  "terrain_distance_km": <decimal number or null>,
  "measurement_line_visible": <true or false>
}"""


# ============================================================
# CLASSIFY — checks ALL conditions, collects ALL failures
# ============================================================
def classify(extracted: dict) -> tuple:
    """
    Checks every condition independently and returns ALL failures found.
    Returns (decision, combined_reasons, combined_messages, failures_list)
    """
    dist         = extracted.get("terrain_distance_km")
    lat          = extracted.get("latitude")
    lon          = extracted.get("longitude")
    search       = extracted.get("olympus_mons_in_search_tab")
    line         = extracted.get("measurement_line_visible")
    addr_visible = extracted.get("address_bar_visible")
    url_x        = extracted.get("url_x")
    url_y        = extracted.get("url_y")

    # treat 0 or 0.0 as null for coordinates (model sometimes returns 0 when not found)
    if url_x == 0 or url_x == 0.0:
        url_x = None
    if url_y == 0 or url_y == 0.0:
        url_y = None

    failures = []

    # ── Check 1: Address bar and URL coordinates ─────────────
    if not addr_visible:
        failures.append({
            "reason":  "address_bar_not_visible",
            "message": "The browser address bar is not visible in your screenshot — "
                       "make sure the full browser window including the URL bar at "
                       "the top is captured in your screenshot."
        })
    elif url_x is None or url_y is None:
        failures.append({
            "reason":  "url_coordinates_not_found",
            "message": "The x and y coordinates could not be found in the address bar URL — "
                       "make sure the full NASA Trek URL is visible and not truncated."
        })

    # ── Check 2: Distance readable ───────────────────────────
    if dist is None:
        failures.append({
            "reason":  "distance_not_visible",
            "message": "We couldn't read the terrain distance — make sure the "
                       "Distance Result panel is fully visible and not cut off."
        })
    # ── Check 3: Distance in range (only if readable) ────────
    elif not (DISTANCE_MIN <= dist <= DISTANCE_MAX):
        failures.append({
            "reason":  "distance_out_of_range",
            "message": f"Your measured diameter is {dist} km, which is outside the "
                       f"accepted range of {DISTANCE_MIN}–{DISTANCE_MAX} km. "
                       "Redraw the line across the full width of Olympus Mons."
        })

    # ── Check 4: Search panel — Olympus Mons + lat/lon ───────
    # These are merged into ONE condition because they are in the same panel.
    # If Olympus Mons is not in the search tab, lat and lon will also be missing.
    if not search:
        failures.append({
            "reason":  "search_panel_not_showing_olympus_mons",
            "message": "Your screenshot does not show the Olympus Mons information "
                       "in the left search panel — this also means the Latitude and "
                       "Longitude values are not visible. Make sure you have searched "
                       "for Olympus Mons and its details are shown in the left panel."
        })

    # ── Check 5: Measurement line ────────────────────────────
    if not line:
        failures.append({
            "reason":  "measurement_line_not_visible",
            "message": "The measurement line isn't visible on the Mars map — "
                       "make sure the line drawn across Olympus Mons is clearly "
                       "shown in your screenshot."
        })

    # ── Final decision ────────────────────────────────────────
    if failures:
        all_reasons  = " | ".join(f["reason"]  for f in failures)
        all_messages = " | ".join(f["message"] for f in failures)
        return "rejected", all_reasons, all_messages, failures

    return "approved", None, None, []


# ============================================================
# PROCESS ONE IMAGE
# ============================================================
def process_image(image_path: str) -> dict:
    image = Image.open(image_path).convert("RGB")

    max_retries = 5
    backoff     = 15
    raw         = ""

    for attempt in range(max_retries):
        try:
            response = model.generate_content(
                [PROMPT, image],
                generation_config={"temperature": 0.0}
            )
            raw = response.text.strip()
            break
        except ResourceExhausted as e:
            if attempt == max_retries - 1:
                raise e
            print(f"    [Rate limit hit — waiting {backoff}s before retry...]")
            time.sleep(backoff)
            backoff *= 2

    # strip markdown fences if present
    cleaned = re.sub(r"```json|```", "", raw).strip()
    match   = re.search(r"\{.*\}", cleaned, re.DOTALL)

    base = {
        "file":              os.path.basename(image_path),
        "parse_success":     False,
        "address_bar_visible": None,
        "url_x":             None,
        "url_y":             None,
        "olympus_mons":      None,
        "latitude":          None,
        "longitude":         None,
        "terrain_distance_km": None,
        "measurement_line_visible": None,
        "decision":          "rejected",
        "all_reasons":       "model_parse_failed",
        "all_messages":      "Model did not return valid JSON.",
        "failure_count":     1,
        "raw_output":        raw[:300],
    }

    if not match:
        return base

    try:
        data = json.loads(match.group())

        # normalise 0/0.0 to null for URL coords
        if data.get("url_x") in [0, 0.0]:
            data["url_x"] = None
        if data.get("url_y") in [0, 0.0]:
            data["url_y"] = None

        decision, all_reasons, all_messages, failures = classify(data)

        return {
            "file":                    os.path.basename(image_path),
            "parse_success":           True,
            "address_bar_visible":     data.get("address_bar_visible"),
            "url_x":                   data.get("url_x"),
            "url_y":                   data.get("url_y"),
            "olympus_mons":            data.get("olympus_mons_in_search_tab"),
            "latitude":                data.get("latitude"),
            "longitude":               data.get("longitude"),
            "terrain_distance_km":     data.get("terrain_distance_km"),
            "measurement_line_visible": data.get("measurement_line_visible"),
            "decision":                decision,
            "all_reasons":             all_reasons  or "",
            "all_messages":            all_messages or "",
            "failure_count":           len(failures),
            "raw_output":              raw[:300],
        }

    except json.JSONDecodeError:
        base["all_reasons"]  = "json_parse_error"
        base["all_messages"] = "Could not parse model response as JSON."
        base["raw_output"]   = raw[:300]
        return base


# ============================================================
# MAIN
# ============================================================
def main():
    supported = {".png", ".jpg", ".jpeg", ".webp"}
    images = sorted([
        os.path.join(IMAGE_DIR, f)
        for f in os.listdir(IMAGE_DIR)
        if os.path.splitext(f)[1].lower() in supported
    ])

    if not images:
        print(f"No images found in {IMAGE_DIR}")
        return

    print(f"Found {len(images)} images")
    print("=" * 60)

    results  = []
    approved = 0
    rejected = 0
    failed   = 0

    for idx, path in enumerate(images, 1):
        print(f"\n[{idx}/{len(images)}] {os.path.basename(path)}")

        result = process_image(path)
        results.append(result)

        print(f"  Address bar visible : {result['address_bar_visible']}")
        print(f"  URL x / y           : {result['url_x']} / {result['url_y']}")
        print(f"  Olympus Mons panel  : {result['olympus_mons']}")
        print(f"  Latitude / Longitude: {result['latitude']} / {result['longitude']}")
        print(f"  Terrain Distance    : {result['terrain_distance_km']} km")
        print(f"  Measurement line    : {result['measurement_line_visible']}")
        print(f"  Failure count       : {result['failure_count']}")
        print(f"  ► Decision          : {result['decision'].upper()}")

        if result["all_reasons"]:
            for i, (r, m) in enumerate(zip(
                result["all_reasons"].split(" | "),
                result["all_messages"].split(" | ")
            ), 1):
                print(f"     Reason {i}: {r}")
                print(f"     Message {i}: {m}")

        if result["decision"] == "approved":
            approved += 1
        elif not result["parse_success"]:
            failed += 1
        else:
            rejected += 1

        if idx < len(images):
            print(f"  [Waiting 12s before next image...]")
            time.sleep(12)

    # ── Save CSV ──────────────────────────────────────────────
    fieldnames = [
        "file", "parse_success",
        "address_bar_visible", "url_x", "url_y",
        "olympus_mons", "latitude", "longitude",
        "terrain_distance_km", "measurement_line_visible",
        "decision", "failure_count", "all_reasons", "all_messages",
        "your_verdict",       # ← YOU fill
        "model_was_correct",  # ← YOU fill (yes / no)
        "notes",              # ← YOU fill
        "raw_output"
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            r["your_verdict"]      = ""
            r["model_was_correct"] = ""
            r["notes"]             = ""
            writer.writerow(r)

    # ── Summary ───────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  DAY 1 v2 — RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Total     : {len(images)}")
    print(f"  Approved  : {approved}")
    print(f"  Rejected  : {rejected}")
    print(f"  Failed    : {failed}")
    print(f"  Output    : {OUTPUT_CSV}")
    print("=" * 60)
    print("\n  NEXT STEP:")
    print("  Open day1_results_v2.csv in Excel.")
    print("  For each row, look at the original image and fill:")
    print("  - your_verdict      : approved / rejected")
    print("  - model_was_correct : yes / no")
    print("  - notes             : what was wrong if model failed")
    print("=" * 60)


if __name__ == "__main__":
    main()