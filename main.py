import asyncio
import json
import os
import time
import aiohttp
import websockets

CONFIG_FILE = "config.json"
GATEWAY_URL = "wss://gateway.discord.gg/?v=9&encoding=json"
USER_AGENT = "Mozilla/5.0"

COLOR_RESET = "\033[0m"
COLOR_RED = "\033[31m"
COLOR_GREEN = "\033[32m"
COLOR_YELLOW = "\033[33m"
COLOR_CYAN = "\033[36m"
COLOR_MAGENTA = "\033[35m"
COLOR_BOLD = "\033[1m"

heartbeat_interval = None
sequence = None
token = None
presence_config = {}

def clear_screen():
    os.system("cls" if os.name == "nt" else "clear")

def print_header():
    clear_screen()
    print(f"{COLOR_CYAN}{COLOR_BOLD}")
    print(r"""    _    __     __    ____        ____    ____   
    U  /"\  u\ \   /"/uU /"___|      |  _"\ U|  _"\ u
     \/ _ \/  \ \ / // \| | u  U  u /| | | |\| |_) |/
     / ___ \  /\ V /_,-.| |/__ /___\U| |_| |\|  __/  
    /_/   \_\U  \_/-(_/  \____|__"__||____/ u|_|     
     \\    >>  //       _// \\        |||_   ||>>_   
    (__)  (__)(__)     (__)(__)      (__)_) (__)__)  """)
    print(f"{COLOR_RESET}\n")

def print_status(message, level="info"):
    colors = {
        "success": COLOR_GREEN, "error": COLOR_RED, "warning": COLOR_YELLOW,
        "info": COLOR_CYAN, "system": COLOR_MAGENTA
    }
    prefix = {
        "success": "[✓] ", "error": "[✗] ", "warning": "[!] ",
        "info": "[i] ", "system": "[»] "
    }
    print(f"{colors[level]}{prefix[level]}{message}{COLOR_RESET}")

def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            print_status("Config load error, resetting config", "warning")
    return {}

def save_config(data):
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)

async def validate_token(token):
    headers = {"Authorization": token, "User-Agent": USER_AGENT}
    async with aiohttp.ClientSession() as session:
        try:
            async with session.get("https://discord.com/api/v9/users/@me", headers=headers) as resp:
                return resp.status == 200
        except:
            return False

async def validate_channel(token, guild_id, channel_id):
    headers = {"Authorization": token, "User-Agent": USER_AGENT}
    async with aiohttp.ClientSession() as session:
        try:
            url = f"https://discord.com/api/v9/guilds/{guild_id}/channels"
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    return None, None
                for c in await resp.json():
                    if c["id"] == channel_id and c["type"] == 2:
                        return c["name"], guild_id
        except:
            return None, None

async def heartbeat(ws):
    while True:
        await asyncio.sleep(heartbeat_interval / 1000)
        await ws.send(json.dumps({"op": 1, "d": sequence}))

async def send_presence(ws):
    if presence_config["type_id"] is None:
        print_status("No activity set (skipped presence)", "warning")
        return

    activity = {
        "name": presence_config["name"],
        "type": presence_config["type_id"]
    }
    if presence_config["type_id"] == 1:
        activity["url"] = presence_config.get("url", "https://twitch.tv/llama")

    payload = {
        "op": 3,
        "d": {
            "since": int(time.time() * 1000),
            "activities": [activity],
            "status": presence_config["status"],
            "afk": False
        }
    }
    await ws.send(json.dumps(payload))
    print_status(f"Presence set: {presence_config['status']} + {presence_config['type']} {presence_config['name']}", "system")


async def join_voice(ws, guild_id, channel_id):
    await ws.send(json.dumps({
        "op": 4,
        "d": {
            "guild_id": guild_id,
            "channel_id": channel_id,
            "self_mute": True, # Changed to appear muted    
            "self_deaf": True  # Changed to appear deafened
        }
    }))
    print_status(f"Joining voice (deafened): {guild_id}:{channel_id}", "system")

async def gateway_connection(guild_id, channel_id):
    global heartbeat_interval, sequence
    print_status("Connecting to Discord Gateway...", "info")
    async with websockets.connect(GATEWAY_URL, max_size=2**23) as ws:
        hello = json.loads(await ws.recv())
        heartbeat_interval = hello["d"]["heartbeat_interval"]
        asyncio.create_task(heartbeat(ws))

        await ws.send(json.dumps({
            "op": 2,
            "d": {
                "token": token,
                "properties": {
                    "os": "Windows",
                    "browser": "Firefox",
                    "device": "desktop"
                },
                "presence": {
                    "status": presence_config["status"],
                    "afk": False
                }
            }
        }))

        async for msg in ws:
            data = json.loads(msg)
            if data.get("s"): sequence = data["s"]

            if data.get("t") == "READY":
                user = data["d"]["user"]
                print_status(f"Connected as {user['username']}#{user['discriminator']}", "success")
                await join_voice(ws, guild_id, channel_id)
                await send_presence(ws)

async def connection_manager(guild_id, channel_id):
    while True:
        try:
            await gateway_connection(guild_id, channel_id)
        except Exception as e:
            print_status(f"Disconnected: {e}", "error")
            print_status("Retrying in 10s...", "warning")
            await asyncio.sleep(10)
            # Wait for internet
            while True:
                try:
                    async with aiohttp.ClientSession() as s:
                        async with s.get("https://1.1.1.1", timeout=5):
                            break
                except:
                    print_status("Waiting for internet...", "warning")
                    await asyncio.sleep(5)

def get_presence_config():
    import readline  # Optional: smooth line clearing on Linux/macOS

    def ask_non_empty(prompt):
        while True:
            response = input(prompt).strip()
            if response:
                return response
            # Move cursor up and clear last line
            print("\033[F\033[K", end='')

    print(f"{COLOR_YELLOW}{COLOR_BOLD}--- Presence Setup ---{COLOR_RESET}\n")

    # STATUS
    valid_status = ["online", "idle", "dnd", "invisible"]
    while True:
        status = input(f"Status (online, idle, dnd, invisible) [default: online]: ").strip().lower()
        if status == "":
            status = "online"
        if status in valid_status:
            break
        print("\033[F\033[K", end='')  # Clear line

    # ACTIVITY TYPE
    print("\nSelect Activity Type (press ENTER to skip):")
    type_map = {
        "3": "Watching",
        "2": "Listening",
        "1": "Streaming",
        "0": "Playing"
    }
    type_id_map = {v.lower(): int(k) for k, v in type_map.items()}

    for k in sorted(type_map.keys(), reverse=True):
        print(f"  {k} - {type_map[k]}")

    type_choice = ""
    while True:
        type_choice = input("\nEnter choice [default: skip]: ").strip()
        if type_choice == "":
            return {
                "name": "",
                "type": None,
                "type_id": None,
                "status": status,
                "url": ""
            }
        if type_choice in type_map:
            break
        print("\033[F\033[K", end='')  # Clear line

    type_text = type_map[type_choice]

    # ACTIVITY NAME (required, no default)
    print()
    name = ask_non_empty("Activity Name (required): ")

    # STREAMING URL (only if streaming)
    stream_url = ""
    if type_choice == "1":
        default_url = "https://twitch.tv/llama"
        stream_url = input(f"\nStream URL [default: {default_url}]: ").strip()
        if not stream_url:
            stream_url = default_url

    print()
    return {
        "name": name,
        "type": type_text,
        "type_id": type_id_map[type_text.lower()],
        "status": status,
        "url": stream_url
    }

def token_menu(config):
    global token
    print_header()
    token = input("Enter Discord token: ").strip()
    if token:
        config["token"] = token
        save_config(config)
    else:
        print_status("No token provided", "error")

def voice_menu(last_guild, last_channel, config):
    global token, presence_config
    if not token:
        token_menu(config)
        if not token:
            return

    print_header()
    guild_id = input(f"Server ID [{last_guild}]: ").strip() or last_guild
    channel_id = input(f"Voice Channel ID [{last_channel}]: ").strip() or last_channel

    print_status("Validating token and channel...", "info")
    if not asyncio.run(validate_token(token)):
        print_status("Invalid token", "error")
        return
    channel_info = asyncio.run(validate_channel(token, guild_id, channel_id))
    if not channel_info:
        print_status("Invalid guild or channel", "error")
        return

    config["last_guild_id"] = guild_id
    config["last_channel_id"] = channel_id
    save_config(config)
    presence_config = get_presence_config()

    try:
        asyncio.run(connection_manager(guild_id, channel_id))
    except KeyboardInterrupt:
        print_status("Terminated", "warning")
        time.sleep(1)

def main():
    global token
    config = load_config()
    token = config.get("token", "")
    while True:
        print_header()
        print("Main Menu:")
        print(" 1 - Join Voice Channel")
        print(" 2 - Update Token")
        print(" 3 - Exit")
        choice = input("Choose: ").strip()
        if choice == "1":
            voice_menu(config.get("last_guild_id", ""), config.get("last_channel_id", ""), config)
        elif choice == "2":
            token_menu(config)
        elif choice == "3":
            print_status("Goodbye!", "success")
            time.sleep(1)
            break
        else:
            print_status("Invalid selection", "error")
            input("Enter to continue...")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{COLOR_RED}[-] Program terminated{COLOR_RESET}")
        time.sleep(1)