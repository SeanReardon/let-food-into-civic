"""
let-food-into-civic - Main entry point

A funny little project running on homelab-infra.
"""

import logging
import os
import sys

# Configure logging
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)

logger = logging.getLogger(__name__)


def main():
    """Main entry point for the service."""
    logger.info("let-food-into-civic starting up...")
    
    # TODO: Implement your service logic here
    logger.info("Service initialized successfully")
    
    # Keep the service running (placeholder - replace with actual service logic)
    try:
        while True:
            import time
            time.sleep(60)
            logger.debug("Heartbeat...")
    except KeyboardInterrupt:
        logger.info("Shutting down...")


if __name__ == "__main__":
    main()

