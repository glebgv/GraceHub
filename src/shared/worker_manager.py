import asyncio
import docker
import logging
import os
from typing import Optional
from shared.database import MasterDatabase

logger = logging.getLogger(__name__)

class DockerWorkerManager:
    def __init__(self, docker_host: Optional[str] = None):
        self.docker_host = docker_host or os.getenv("DOCKER_HOST", "unix:///var/run/docker.sock")
        self.use_docker = self._is_docker_available()
        logger.info(f"WorkerManager mode: {'DOCKER' if self.use_docker else 'FALLBACK'}")
    
    def _is_docker_available(self) -> bool:
        try:
            if self.docker_host.startswith("unix://"):
                client = docker.DockerClient(base_url=self.docker_host)
            else:
                client = docker.from_env()
            client.ping()
            return True
        except Exception:
            logger.warning("Docker unavailable - using fallback mode")
            return False
    
    # 🔥 Только 2 аргумента! БЕЗ token!
    async def spawn_worker(self, instance_id: str, db: MasterDatabase):
        """Спавним worker контейнер БЕЗ token - worker берёт из БД по hostname"""
        if self.use_docker:
            await self._spawn_docker(instance_id, db)
        else:
            logger.warning(f"Docker unavailable for {instance_id} - skipping spawn")
            # Можно добавить fallback логику позже
            raise Exception(f"Docker unavailable - cannot spawn worker for {instance_id}")
    
    async def _spawn_docker(self, instance_id: str, db: MasterDatabase):
        """🔥 Минимальные ENV - worker сам найдёт instance_id по имени контейнера"""
        try:
            client = docker.DockerClient(base_url=self.docker_host)
            container_name = f"gracehub-worker-{instance_id}"
            image_name = "gracehub-user-worker"
            
            # Проверяем наличие образа
            try:
                client.images.get(image_name)
                logger.info(f"✅ Local image found: {image_name}")
            except docker.errors.ImageNotFound:
                logger.error(f"❌ Image {image_name} not found locally!")
                raise Exception(f"Build user-worker first: docker compose build user-worker")
            
            # Удаляем старый контейнер (если есть)
            try:
                container = client.containers.get(container_name)
                logger.info(f"🗑️ Stopping old container: {container_name}")
                container.stop()
                container.remove()
            except docker.errors.NotFound:
                pass
            
            # 🔥 ИСПРАВЛЕННЫЕ ENV - ВСЕ С ЗАГЛАВНЫМИ БУКВАМИ!
            environment = {
                "DATABASE_URL": db.dsn,  
                "WORKER_INSTANCE_ID": instance_id,
                "ENCRYPTION_KEY": os.getenv("ENCRYPTION_KEY", "DK2GpT43STFu463KTh4aUNLud5HPZ38YEBpD-ndhm3E="),
                
                # Настройки приложения
                "APP_BASE_DIR": "/app",
                "LOGLEVEL": os.getenv("LOGLEVEL", "INFO"),
                "WEBHOOK_DOMAIN": os.getenv("WEBHOOK_DOMAIN", ""),
                "WEBHOOK_PORT": os.getenv("WEBHOOK_PORT", "8443"),
                "ENCRYPTION_KEY_FILE": "/app/master_key.key",
                
                # Fallback DB переменные (на случай если DATABASE_URL не работает)
                "DB_HOST": os.getenv("DB_HOST", "db"),
                "DB_USER": os.getenv("DB_USER", ""),
                "DB_PASSWORD": os.getenv("DB_PASSWORD", ""),
                "DB_NAME": os.getenv("DB_NAME", ""),
            }
            
            # 🔥 Копируем все GRACEHUB_* переменные из master (но НЕ токены!)
            for key, value in os.environ.items():
                if key.startswith("GRACEHUB_") and key not in ["GRACEHUB_MASTERBOT_TOKEN"]:
                    environment[key] = value  # ✅ Оставляем как есть (заглавные)
            # Перед client.containers.run добавьте:
            logger.info(f"🔍 [DEBUG] Environment for {container_name}:")
            logger.info(f"   DATABASE_URL: {environment.get('DATABASE_URL', 'NOT SET')[:50]}...")
            logger.info(f"   WORKER_INSTANCE_ID: {environment.get('WORKER_INSTANCE_ID', 'NOT SET')}")
            logger.info(f"   ENCRYPTION_KEY: {'SET' if environment.get('ENCRYPTION_KEY') else 'NOT SET'}")
           
            container = client.containers.run(
                image=image_name,
                name=container_name,
                hostname=container_name,  # ✅ Устанавливаем hostname
                environment=environment,
                detach=True,
                network="gracehub_default",
                mem_limit="512m",
                restart_policy={"Name": "unless-stopped"},
                labels={
                    "gracehub.instance": instance_id,
                    "gracehub.type": "user-worker"
                }
            )
            
            logger.info(f"🚀 Docker worker spawned: {container_name} (hostname={container_name}) ID={container.id}")
            await db.update_instance_status(instance_id, "RUNNING")
            
        except Exception as e:
            logger.error(f"💥 Docker spawn failed instance_id={instance_id}: {e}")
            raise


    
    async def stop_worker(self, instance_id: str):
        """Останавливаем и удаляем worker контейнер"""
        try:
            client = docker.DockerClient(base_url=self.docker_host)
            container_name = f"gracehub-worker-{instance_id}"
            container = client.containers.get(container_name)
            logger.info(f"🛑 Stopping container: {container_name}")
            container.stop()
            container.remove()
            logger.info(f"✅ Docker worker stopped: {container_name}")
        except docker.errors.NotFound:
            logger.info(f"ℹ️ Container not found: {container_name}")
        except Exception as e:
            logger.warning(f"⚠️ Docker stop failed {instance_id}: {e}")

# Глобальный экземпляр
worker_manager = DockerWorkerManager()
