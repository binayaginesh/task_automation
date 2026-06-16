import google.generativeai as genai
from PIL import Image
import json
import re
import os
import csv
from datetime import datetime
import time
from google.api_core.exceptions import ResourceExhausted

# ============================================================
# CONFIG — fill these in before running
# ============================================================
API_KEY    = os.environ.get("GEMINI_API_KEY", "")
IMAGE_DIR  = r"C:\Users\HP\Desktop\automation\#ge-sp-marstrek\test"
OUTPUT_CSV = r"C:\Users\HP\Desktop\automation\day1_results.csv"

DISTANCE_MIN = 600.13
DISTANCE_MAX = 620.13
# ============================================================

genai.configure(api_key=API_KEY)
model = genai.GenerativeModel("gemini-flash-latest")

PROMPT = """This is a NASA Solar System Trek screenshot showing a Mars 
surface measurement of Olympus Mons.

Carefully read ALL visible text including:
- The browser URL bar at the top (look for x= and y= values)
- The left search/info panel (look for Latitude and Longitude fields)
- The Distance Result popup (look for Terrain Distance value in km)
- Whether Olympus Mons appears in the search/info panel on the left
- Whether a yellow measurement line is drawn across the Mars map

Return ONLY this JSON. No explanation. No markdown. Raw JSON only:
{
  "terrain_distance_km": <decimal number or null if not visible>,
  "latitude": <decimal number from search panel or null>,
  "longitude": <decimal number from search panel or null>,
  "url_x": <decimal number from URL bar x= parameter or null>,
  "url_y": <decimal number from URL bar y= parameter or null>,
  "olympus_mons_in_search_tab": <true or false>,
  "measurement_line_visible": <true or false>
}"""


def classify(extracted: dict) -> tuple:
    """
    Returns (decision, reason, message) based on extracted values.
    Pure if/else logic — no model involved here.
    """
    dist   = extracted.get("terrain_distance_km")
    lat    = extracted.get("latitude")
    lon    = extracted.get("longitude")
    search = extracted.get("olympus_mons_in_search_tab")
    line   = extracted.get("measurement_line_visible")

    if dist is None:
        return (
            "rejected",
            "distance_not_visible",
            "We couldn't read the terrain distance — make sure the "
            "Distance Result panel is fully visible and not cut off."
        )
    if not (DISTANCE_MIN <= dist <= DISTANCE_MAX):
        return (
            "rejected",
            "distance_out_of_range",
            f"Your measured diameter is {dist} km, which is outside the "
            f"accepted range of {DISTANCE_MIN}–{DISTANCE_MAX} km. "
            "Redraw the line across the full width of Olympus Mons."
        )
    if not search:
        return (
            "rejected",
            "olympus_mons_not_in_search",
            "Your screenshot does not show Olympus Mons in the search "
            "panel — make sure the search tab with Olympus Mons is visible."
        )
    if lat is None or lon is None:
        return (
            "rejected",
            "coordinates_not_visible",
            "The latitude/longitude values aren't readable — ensure the "
            "full search panel including coordinates is visible."
        )
    if not line:
        return (
            "rejected",
            "line_not_visible",
            "The measurement line isn't visible on the Mars map — make "
            "sure the line drawn across Olympus Mons is clearly shown."
        )

    return ("approved", None, None)


def process_image(image_path: str) -> dict:
    image = Image.open(image_path).convert("RGB")

    max_retries = 5
    backoff = 15
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
            print(f"    [Quota exceeded, waiting {backoff} seconds before retry...]")
            time.sleep(backoff)
            backoff *= 2

    # clean markdown if present
    cleaned = re.sub(r"```json|```", "", raw).strip()
    match   = re.search(r"\{.*\}", cleaned, re.DOTALL)

    if not match:
        return {
            "file":               os.path.basename(image_path),
            "parse_success":      False,
            "terrain_distance_km": None,
            "latitude":           None,
            "longitude":          None,
            "url_x":              None,
            "url_y":              None,
            "olympus_mons":       None,
            "line_visible":       None,
            "decision":           "rejected",
            "reason":             "model_parse_failed",
            "message":            "Model did not return valid JSON.",
            "raw_output":         raw[:200],
        }

    try:
        data     = json.loads(match.group())
        decision, reason, message = classify(data)

        return {
            "file":                os.path.basename(image_path),
            "parse_success":       True,
            "terrain_distance_km": data.get("terrain_distance_km"),
            "latitude":            data.get("latitude"),
            "longitude":           data.get("longitude"),
            "url_x":               data.get("url_x"),
            "url_y":               data.get("url_y"),
            "olympus_mons":        data.get("olympus_mons_in_search_tab"),
            "line_visible":        data.get("measurement_line_visible"),
            "decision":            decision,
            "reason":              reason,
            "message":             message,
            "raw_output":          raw[:200],
        }

    except json.JSONDecodeError:
        return {
            "file":                os.path.basename(image_path),
            "parse_success":       False,
            "terrain_distance_km": None,
            "latitude":            None,
            "longitude":           None,
            "url_x":               None,
            "url_y":               None,
            "olympus_mons":        None,
            "line_visible":        None,
            "decision":            "rejected",
            "reason":              "json_parse_error",
            "message":             "Could not parse model response as JSON.",
            "raw_output":          raw[:200],
        }


def main():
    # collect images
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
    print("=" * 55)

    results  = []
    approved = 0
    rejected = 0
    failed   = 0

    for idx, path in enumerate(images, 1):
        print(f"\n[{idx}/{len(images)}] {os.path.basename(path)}")

        result = process_image(path)
        results.append(result)

        # Sleep to comply with 5 RPM limit
        if idx < len(images):
            time.sleep(12)

        print(f"  Distance    : {result['terrain_distance_km']} km")
        print(f"  Lat / Lon   : {result['latitude']} / {result['longitude']}")
        print(f"  URL x / y   : {result['url_x']} / {result['url_y']}")
        print(f"  OlympusMons : {result['olympus_mons']}")
        print(f"  Line visible: {result['line_visible']}")
        print(f"  -> Decision  : {result['decision'].upper()}")
        if result["reason"]:
            print(f"  -> Reason    : {result['reason']}")
        if result["message"]:
            print(f"  -> Message   : {result['message']}")

        if result["decision"] == "approved":
            approved += 1
        elif not result["parse_success"]:
            failed += 1
        else:
            rejected += 1

    # save results to CSV for your manual review
    fieldnames = [
        "file", "parse_success", "terrain_distance_km",
        "latitude", "longitude", "url_x", "url_y",
        "olympus_mons", "line_visible", "decision",
        "reason", "message",
        "your_verdict",          # ← YOU fill this column
        "model_was_correct",     # ← YOU fill this column (yes/no)
        "notes",                 # ← YOU fill this column
        "raw_output"
    ]

    with open(OUTPUT_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for r in results:
            r["your_verdict"]      = ""   # fill manually
            r["model_was_correct"] = ""   # fill manually
            r["notes"]             = ""   # fill manually
            writer.writerow(r)

    # summary
    print("\n" + "=" * 55)
    print("  DAY 1 RESULTS SUMMARY")
    print("=" * 55)
    print(f"  Total images   : {len(images)}")
    print(f"  Approved       : {approved}")
    print(f"  Rejected       : {rejected}")
    print(f"  Parse failed   : {failed}")
    print(f"\n  Results saved  : {OUTPUT_CSV}")
    print("=" * 55)
    print("\n  NEXT STEP:")
    print("  Open day1_results.csv in Excel or Google Sheets.")
    print("  For each row:")
    print("  - Look at the original image")
    print("  - Fill 'your_verdict' with approved/rejected")
    print("  - Fill 'model_was_correct' with yes/no")
    print("  - Add notes if the model got something wrong")
    print("  This tells us where Gemini is failing.")
    print("=" * 55)


if __name__ == "__main__":
    main()