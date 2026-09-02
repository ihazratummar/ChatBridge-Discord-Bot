import os
import sys
import logging
import asyncio
import signal
import discord
from discord.ext import commands
from dotenv import load_dotenv

from core.database import get_database_manager
from core.bridge_service import BridgeService
from services.f2f_client import F2FClient
from services.campaign_service import CampaignService
from cogs.owner_commands import OwnerCommands
from cogs.f2f_automation import F2FAutomation

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("ChatBridge")

# Load environment variables
load_dotenv()
TOKEN = os.getenv("DISCORD_BOT_TOKEN")

if not TOKEN or TOKEN == "YOUR_DISCORD_BOT_TOKEN_HERE":
    logger.critical("DISCORD_BOT_TOKEN not found in environment or .env file! Exiting.")
    sys.exit(1)

# Intents configuration
intents = discord.Intents.default()
intents.guilds = True
intents.messages = True
intents.message_content = True  # Required for reading message content to relay & prompt

class ChatBridgeBot(commands.Bot):
    def __init__(self):
        super().__init__(command_prefix="!", intents=intents, help_command=None)
        self.db = get_database_manager()
        self.bridge_service = BridgeService(self, self.db)
        
        # Initialize F2F Client & Campaign Service
        self.f2f_client = F2FClient()
        self.campaign_service = CampaignService(self.db, self.f2f_client)

    async def setup_hook(self):
        logger.info("Initializing Database connection...")
        await self.db.connect()

        logger.info("Loading Bridge Service Cache...")
        await self.bridge_service.reload_cache()

        logger.info("Adding Cogs: OwnerCommands, F2FAutomation & LiveStreamController...")
        await self.add_cog(OwnerCommands(self, self.bridge_service))
        await self.add_cog(F2FAutomation(self, self.campaign_service))
        try:
            from cogs.live_stream_controller import LiveStreamControllerCog
            await self.add_cog(LiveStreamControllerCog(self))
            logger.info("Loaded LiveStreamControllerCog successfully.")
        except Exception as e:
            logger.error(f"Error loading LiveStreamControllerCog: {e}")

        logger.info("Syncing Slash Command Tree with Discord...")
        try:
            synced = await self.tree.sync()
            logger.info(f"Synced {len(synced)} Slash Commands successfully.")
        except Exception as e:
            logger.error(f"Failed to sync Slash Commands: {e}")

    async def on_ready(self):
        logger.info(f"Logged in as {self.user.name}#{self.user.discriminator} (ID: {self.user.id})")
        logger.info(f"Connected to {len(self.guilds)} Guilds.")

        # Automatically start background campaign worker loops
        self.campaign_service.start_worker()

        await self.change_presence(
            activity=discord.Activity(type=discord.ActivityType.watching, name="Channel Sync & F2F Automation")
        )

    async def on_message(self, message: discord.Message):
        # 1. Safely handle 2-way channel message relay
        try:
            await self.bridge_service.handle_incoming_message(message)
        except Exception as e:
            logger.error(f"Unhandled error in message relay: {e}", exc_info=True)

        # 2. Process prefix commands if any
        try:
            await self.process_commands(message)
        except Exception as e:
            logger.error(f"Error processing commands: {e}", exc_info=True)

    async def close(self):
        logger.info("Shutting down ChatBridge bot...")
        try:
            await self.f2f_client.close()
            await self.db.close()
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")
        await super().close()

async def main():
    bot = ChatBridgeBot()

    # Graceful shutdown handler for UNIX signals
    loop = asyncio.get_running_loop()
    stop_event = asyncio.Event()

    def signal_handler():
        logger.info("Received termination signal. Triggering graceful shutdown...")
        stop_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            pass  # Windows platform compatibility

    async with bot:
        bot_task = asyncio.create_task(bot.start(TOKEN))
        stop_task = asyncio.create_task(stop_event.wait())

        done, pending = await asyncio.wait(
            [bot_task, stop_task],
            return_when=asyncio.FIRST_COMPLETED
        )

        for task in pending:
            task.cancel()

        if bot_task in done:
            exc = bot_task.exception()
            if exc:
                logger.error(f"Bot startup failed with error: {exc}")
                raise exc

        if stop_event.is_set():
            await bot.close()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution terminated by user.")
