from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Optional, Dict, Any


class InstanceStatus(str, Enum):
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    STOPPED = "stopped"


@dataclass
class BotInstance:
    instance_id: str
    user_id: int  # внутренний id владельца в твоей системе (как было)
    token_hash: str
    bot_username: str
    bot_name: str
    webhook_url: str
    webhook_path: str
    webhook_secret: str
    status: InstanceStatus
    created_at: datetime
    updated_at: Optional[datetime] = None
    error_message: Optional[str] = None

    # новый владелец-интегратор: реальный Telegram user id администратора,
    # который привязывал worker-бота / является "owner" инстанса в Telegram
    owner_user_id: Optional[int] = None

    # опционально: приватный чат, куда слали ссылку на мини-аппу
    admin_private_chat_id: Optional[int] = None

    # Backward-compatible aliases (old field names used in some code)

    @property
    def instanceid(self) -> str:  # alias
        return self.instance_id

    @instanceid.setter
    def instanceid(self, v: str) -> None:
        self.instance_id = v

    @property
    def userid(self) -> int:  # alias
        return self.user_id

    @userid.setter
    def userid(self, v: int) -> None:
        self.user_id = v

    @property
    def tokenhash(self) -> str:  # alias
        return self.token_hash

    @tokenhash.setter
    def tokenhash(self, v: str) -> None:
        self.token_hash = v

    @property
    def botusername(self) -> str:  # alias
        return self.bot_username

    @botusername.setter
    def botusername(self, v: str) -> None:
        self.bot_username = v

    @property
    def botname(self) -> str:  # alias
        return self.bot_name

    @botname.setter
    def botname(self, v: str) -> None:
        self.bot_name = v

    @property
    def webhookurl(self) -> str:  # alias
        return self.webhook_url

    @webhookurl.setter
    def webhookurl(self, v: str) -> None:
        self.webhook_url = v

    @property
    def webhookpath(self) -> str:  # alias
        return self.webhook_path

    @webhookpath.setter
    def webhookpath(self, v: str) -> None:
        self.webhook_path = v

    @property
    def webhooksecret(self) -> str:  # alias
        return self.webhook_secret

    @webhooksecret.setter
    def webhooksecret(self, v: str) -> None:
        self.webhook_secret = v

    @property
    def createdat(self) -> datetime:  # alias
        return self.created_at

    @createdat.setter
    def createdat(self, v: datetime) -> None:
        self.created_at = v

    @property
    def updatedat(self) -> Optional[datetime]:  # alias
        return self.updated_at

    @updatedat.setter
    def updatedat(self, v: Optional[datetime]) -> None:
        self.updated_at = v

    @property
    def errormessage(self) -> Optional[str]:  # alias
        return self.error_message

    @errormessage.setter
    def errormessage(self, v: Optional[str]) -> None:
        self.error_message = v


@dataclass
class UserState:
    user_id: int
    state: str
    data: Optional[str] = None
    created_at: Optional[datetime] = None

    # aliases
    @property
    def userid(self) -> int:
        return self.user_id

    @userid.setter
    def userid(self, v: int) -> None:
        self.user_id = v

    @property
    def createdat(self) -> Optional[datetime]:
        return self.created_at

    @createdat.setter
    def createdat(self, v: Optional[datetime]) -> None:
        self.created_at = v


@dataclass
class UpdateQueueItem:
    instance_id: str
    updated_ata: Dict[str, Any]
    priority: int = 0
    created_at: datetime = datetime.now()

    # alias for updated_ata to keep current callers intact if needed
    @property
    def update_data(self) -> Dict[str, Any]:
        return self.updated_ata

    @update_data.setter
    def update_data(self, v: Dict[str, Any]) -> None:
        self.updated_ata = v
