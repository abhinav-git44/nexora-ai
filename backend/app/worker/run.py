import logging
from app.worker.queue import loop

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    loop()
