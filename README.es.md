<div align="right">
  <a href="README.md">🇷🇺 Русский</a> •
  <a href="README.en.md">🇬🇧 English</a> •
  <a href="README.es.md">🇪🇸 Español</a> •
  <a href="README.hi.md">🇮🇳 हिन्दी</a> •
  <a href="README.zh.md">🇨🇳 简体中文</a>
</div>

<div align="center">

> ⚠️ **Importante:** Este proyecto se encuentra en la etapa de **pruebas alfa**.
> La funcionalidad puede cambiar, son posibles errores y funcionamiento inestable.
> Utilícelo con precaución y reporte cualquier problema.

</div>

---

<div align="center">
  <table cellpadding="0" cellspacing="0" style="border: none;">
    <tr>
      <td style="padding: 0; border: none; vertical-align: middle;">
        <img src="logo.png" alt="GraceHub Logo" width="60">
      </td>
      <td style="padding: 0 0 0 20px; border: none; vertical-align: middle;">
        <h1 style="margin: 0;">GraceHub Platform</h1>
      </td>
    </tr>
  </table>
</div>

GraceHub es una plataforma SaaS que le permite desplegar su soporte directamente en Telegram, así como convertirse en proveedor de servicios de bots de retroalimentación y soporte técnico para pequeñas y medianas empresas.

**🌐 Sitio Web:** [gracehub.ru](https://gracehub.ru)  
**📢 Canal de Telegram:** [@gracehubru](https://t.me/gracehubru)  
**👨‍💻 Desarrollador:** [@Gribson_Micro](https://t.me/Gribson_Micro)
**🗺️ Hoja de ruta:** [ROADMAP.md](./ROADMAP.md)


## Características Principales

- **Bot Maestro** — centro de control para vincular todos los bots de retroalimentación
- **Mini App Gabinete Personal** — interfaz intuitiva para gestionar bots y clientes
- **Estadísticas y Análisis** — realice un seguimiento de las métricas de cada bot
- **Sistema de Facturación** — cálculo automático y gestión de pagos

## 🌍 Idiomas Soportados

- 🇷🇺 Русский
- 🇬🇧 English
- 🇪🇸 Español
- 🇮🇳 हिन्दी
- 🇨🇳 简体中文

## 🛠 Stack Tecnológico

| Componente | Tecnología |
|-----------|-----------|
| Backend | Python (FastAPI, Hypercorn) |
| Frontend | React 19 + TypeScript + Vite |
| Gestión de Bots | API de Telegram Bot |
| Base de Datos | PostgreSQL 15+ |
| Proxy | Nginx |
| Versión de Python | 3.11+ |

## 📁 Estructura del Proyecto

```
gracehub/
├── src/
│   └── master_bot/
│       ├── main.py                 # Punto de entrada del bot maestro
│       ├── api_server.py           # Servidor API REST
│       └── worker/                 # Trabajadores de instancias
├── frontend/miniapp_frontend/      # Aplicación React
├── config/                         # Archivos de configuración
├── scripts/
│   └── launch.sh                   # Script de lanzamiento
├── logs/                           # Registros de aplicación
└── .env                            # Variables de entorno
```

## 📋 Requisitos

- Python 3.10+
- Node.js 20+
- PostgreSQL 15+
- Nginx (opcional)
- Nombre de dominio

## ⚙️ Configuración del Entorno

1. Navegue al directorio del proyecto:

```bash
cd /root/gracehub
```

2. Cree y configure el archivo de entorno:

```bash
cp .env-example .env
nano .env
```

3. Cargue las variables de entorno:

```bash
source .env
```

4. Cree un entorno virtual si es necesario:

```bash
python3 -m venv venv
source venv/bin/activate
```

## 🚀 Ejecución para Desarrollo

### Modo Normal (con registros en terminal)

```bash
./scripts/launch.sh dev
```

### Modo de Fondo

```bash
./scripts/launch.sh dev --detach
```

El inicio incluye tres procesos:
- bot maestro
- servidor API REST
- aplicación frontend

### Ejecución para Uso Personal

Si desea ejecutar el proyecto para usted y su equipo y restringir el acceso externo, especifique 2 parámetros en `.env`:

```bash
export GRACEHUB_SINGLE_TENANT_OWNER_ONLY=1
export GRACEHUB_OWNER_TELEGRAM_ID=YOUR_ID
```

Reemplace `YOUR_ID` con su ID de Telegram.

## 🔧 Implementación en Producción mediante systemd

### Configuración Inicial e Implementación

```bash
./scripts/launch.sh prod
```

### Gestión de Servicios

Después de la implementación, gestione los servicios mediante systemd:

```bash
# Verificar estado
systemctl status gracehub-master gracehub-api gracehub-frontend

# Reiniciar servicios
systemctl restart gracehub-master gracehub-api gracehub-frontend

# Detener servicio
systemctl stop gracehub-frontend
```

## 📊 Registros y Monitoreo

### Modo de Desarrollo

Los registros se encuentran en el directorio `logs/`:

```bash
tail -f logs/masterbot.log
tail -f logs/api_server.log
tail -f logs/frontend-dev.log
```

### Producción

Ver registros de systemd:

```bash
journalctl -u gracehub-master -n 50 --no-pager
journalctl -u gracehub-api -n 50 --no-pager
journalctl -u gracehub-frontend -n 50 --no-pager
```

## 🎯 Instrucciones de Uso

Después de una implementación exitosa, siga estos pasos para configurar su soporte:

### Paso 1: Conectar el Bot Principal de GraceHub

1. Encuentre el bot principal de GraceHub Platform en Telegram (que implementó en los pasos anteriores)
2. Haga clic en **Start** o escriba `/start`
3. El bot le proporcionará un gabinete personal e instrucciones de gestión

### Paso 2: Registrar su Bot de Soporte

1. En el bot principal, seleccione la opción para agregar un nuevo bot
2. Obtenga el token de su bot de Telegram a través de [@BotFather](https://t.me/botfather)
3. Envíe el token al bot de GraceHub Platform
4. Su bot de soporte será activado en el sistema

### Paso 3: Inicializar Administrador

1. Escriba el comando `/start` en su nuevo bot de soporte
2. El bot lo recordará como administrador y otorgará acceso a la gestión

### Paso 4: Crear un Super Chat con Temas

1. Cree un nuevo grupo en Telegram
2. En la configuración del grupo, habilite el modo **"Discusiones"** (Topics)
3. Agregue su bot de soporte a este grupo con derechos de administrador
4. Asegúrese de que el bot tenga derechos para administrar mensajes y temas

### Paso 5: Vincular Bot al Tema General

1. Abra el tema **General** en su super chat
2. Escriba el comando de vinculación:

```
/bind @your_bot_username
```

Reemplace `@your_bot_username` con el nombre de usuario de su bot de soporte.

3. Después de la vinculación exitosa, el bot comenzará a aceptar solicitudes de clientes en este tema
4. Todos los mensajes de clientes se distribuirán automáticamente entre los temas en el super chat

### ✅ ¡Hecho!

Su sistema de soporte en Telegram está completamente configurado. Los clientes de su negocio podrán escribir al bot y usted verá todas las solicitudes en una interfaz de super chat conveniente con separación de temas.

## 📄 Licencia

MIT

