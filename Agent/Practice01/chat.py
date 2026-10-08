import configparser
import json
import sys
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

cfg = configparser.ConfigParser()
cfg.read("config.ini", encoding="utf-8")
llm = cfg["llm"]
messages = []

try:
    while True:
        text = input("你的问题是")
        messages.append({"role": "user", "content": text})
        payload = {
            "model": llm["model"],
            "messages": messages,
            "temperature": float(llm.get("temperature", 0.7)),
            "stream": True,
        }
        headers = {"Content-Type": "application/json"}
        if llm["api_key"] and llm["api_key"] != "your-api-key":
            headers["Authorization"] = "Bearer " + llm["api_key"]

        req = urllib.request.Request(
            llm["api_base"].rstrip("/") + "/chat/completions",
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
        )
        reply = ""
        with urllib.request.urlopen(req) as resp:
            for line in resp:
                line = line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    content = json.loads(data)["choices"][0]["delta"].get("content", "")
                except (KeyError, IndexError, json.JSONDecodeError):
                    continue
                if content:
                    reply += content
                    print(content, end="", flush=True)
        messages.append({"role": "assistant", "content": reply})
        print()
except KeyboardInterrupt:
    print("\n已退出")