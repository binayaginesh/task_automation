import os
import discord
import importlib
from discord.ext import commands
from dotenv import load_dotenv

# Import your Mars evaluator
from day1_test import process_image
from database import coordinate_exists, save_coordinate

# --------------------------------------------------------
# Load environment variables
# --------------------------------------------------------

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not found in .env")

# --------------------------------------------------------
# Discord Intents
# --------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents
)

# --------------------------------------------------------
# Bot Ready
# --------------------------------------------------------

@bot.event
async def on_ready():
    print("=" * 60)
    print("✅ Bot Connected!")
    print(f"Logged in as : {bot.user}")
    print("=" * 60)


# --------------------------------------------------------
# Message Listener
# --------------------------------------------------------

@bot.event
async def on_message(message):

    # Ignore bot's own messages
    if message.author.bot:
        return

    print("\n" + "=" * 60)
    print(f"Author  : {message.author}")
    print(f"Channel : #{message.channel.name}")
    print(f"Message : {message.content}")

    content_lower = message.content.lower()

    # Process mufifa2026-intro submissions
    if "#mufifa2026-intro" in content_lower:
        print("Processing #mufifa2026-intro submission...")
        try:
            mufifa_module = importlib.import_module("#mufifa2026-intro")
            result = mufifa_module.validate_submission(message.content)
            
            if result.get("reaction"):
                await message.add_reaction(result["reaction"])
            
            if result.get("reply_message"):
                await message.reply(result["reply_message"])
                
        except Exception as e:
            print(f"Error handling #mufifa2026-intro: {e}")
            await message.add_reaction("🚩")
            await message.reply("⚠️ An internal error occurred while validating your Pull Request.")
            
        await bot.process_commands(message)
        return

    # Only process Mars Trek submissions
    if "#ge-sp-marstrek" not in content_lower:
        print("Not a Mars Trek submission.")
        await bot.process_commands(message)
        return

    # No attachment
    if not message.attachments:
        print("No image attached.")

        await message.reply(
            "❌ Please attach a Mars Trek screenshot."
        )

        await bot.process_commands(message)
        return

    attachment = message.attachments[0]

    # Check attachment is an image
    if not attachment.content_type or not attachment.content_type.startswith("image"):
        print("Attachment is not an image.")

        await message.reply(
            "❌ Please upload an image."
        )

        await bot.process_commands(message)
        return

    print("\nImage detected")
    print(f"Filename : {attachment.filename}")
    print(f"Type     : {attachment.content_type}")
    print(f"Size     : {attachment.size} bytes")

    try:

        print("\nReading image into memory...")

        image_bytes = await attachment.read()

        print("Sending image to Gemini...")

        result = process_image(image_bytes)

        print("\n========== GEMINI RESULT ==========")
        print(result)
        print("===================================")

        if result["decision"] == "approved":

            print("✅ APPROVED")

            url_x = result.get("url_x")
            url_y = result.get("url_y")

            if url_x is not None and url_y is not None and coordinate_exists(url_x, url_y):
                print("❌ REJECTED (Duplicate)")
                await message.add_reaction("🚩")
                await message.reply(
                    "❌ Submission rejected.\n\n"
                    "- This coordinate has already been submitted by another student."
                )
            else:
                if url_x is not None and url_y is not None:
                    save_coordinate(str(message.author.id), message.author.name, url_x, url_y)

                await message.add_reaction("🏁")

                await message.reply(
                    "✅ Submission looks valid.\n"
                    "Waiting for General Enabler review."
                )

        else:

            print("❌ REJECTED")

            await message.add_reaction("🚩")

            reasons_raw = result.get("all_messages", "Unknown reason.")
            if " | " in reasons_raw:
                reasons = "\n".join(f"- {r}" for r in reasons_raw.split(" | "))
            else:
                reasons = f"- {reasons_raw}"

            await message.reply(
                f"❌ Submission rejected.\n\n{reasons}"
            )

    except Exception as e:

        print("\nERROR")
        print(e)

        await message.reply(
            "⚠️ An internal error occurred while checking the image."
        )

    await bot.process_commands(message)


# --------------------------------------------------------
# Run Bot
# --------------------------------------------------------

bot.run(TOKEN)