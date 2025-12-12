import logging
from typing import Optional
from urllib.parse import urljoin

from aiogram import Bot

logger = logging.getLogger(__name__)


class WebhookManager:
    """
    Manages webhook URLs and routing.

    Формирует URL вебхука вида:
      {protocol}://{domain}/webhook/{instanceid}
    и умеет из пути вытащить instanceid.
    """

    def __init__(self, domain: str, use_https: bool = True) -> None:
        self.domain = domain.rstrip("/")
        self.protocol = "https://" if use_https else "http://"
        self.baseurl = f"{self.protocol}{self.domain}"

    def generate_webhook_url(self, instanceid: str) -> str:
        """
        Generate webhook URL for bot instance.
        """
        # urljoin нормально склеивает baseurl и относительный путь
        return urljoin(self.baseurl + "/", f"webhook/{instanceid}")

    def extract_instance_id(self, webhookpath: str) -> Optional[str]:
        """
        Extract instance ID from webhook path.

        Ожидаемые варианты:
          - "/webhook/<id>"
          - "webhook/<id>"
        """
        if webhookpath.startswith("/"):
            webhookpath = webhookpath[1:]
        if webhookpath.startswith("webhook/"):
            return webhookpath[len("webhook/"):]
        return None

    async def setup_webhook(self, bottoken: str, webhookurl: str, secrettoken: str) -> bool:
        """
        Setup webhook for bot.

        Вызывает setWebhook у Telegram API с заданным URL и секретом.
        """
        bot = Bot(token=bottoken)
        try:
            await bot.set_webhook(
                url=webhookurl,
                secret_token=secrettoken,
                allowed_updates=["message", "callback_query", "chat_member"],
                drop_pending_updates=True,
            )
            logger.info(f"Webhook setup successful {webhookurl}")
            return True
        except Exception as e:
            logger.error(f"Failed to setup webhook {webhookurl}: {e}")
            return False
        finally:
            await bot.session.close()

    async def remove_webhook(self, bottoken: str) -> bool:
        """
        Remove webhook for bot.
        """
        bot = Bot(token=bottoken)
        try:
            await bot.delete_webhook(drop_pending_updates=True)
            logger.info("Webhook removed successfully")
            return True
        except Exception as e:
            logger.error(f"Failed to remove webhook: {e}")
            return False
        finally:
            await bot.session.close()

