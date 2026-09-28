"""Native Windows desktop UI for JARVIS with live module controls."""

import json
import base64
import math
import os
import queue
import threading
import time
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
import mimetypes

from agent.runtime import build_agent
from agent import tts, voice, stt
from agent.tools_catalog import TOOLS

BG = "#081522"
PANEL = "#0d2638"
PANEL2 = "#123e55"
LINE = "#2f7d9e"
CYAN = "#6ff3ff"
TEXT = "#f0fbff"
MUTED = "#91adbd"
GREEN = "#55e39b"
RED = "#ff647c"
YELLOW = "#ffcf6b"
APP_DIR = Path(os.environ.get("APPDATA", Path.home())) / "JARVIS"
SETTINGS_FILE = APP_DIR / "settings.json"
DEFAULT_PROVIDER = "openai-compatible"
DEFAULT_URL = "https://openrouter.ai/api/v1/chat/completions"


def _safe_endpoint(value: str | None) -> str:
    """Reject stale local endpoints that cause WinError 10061 on normal cloud setup."""
    url = (value or "").strip()
    if not url:
        return DEFAULT_URL
    lowered = url.lower()
    blocked = ("localhost", "127.0.0.1", "0.0.0.0")
    if any(lowered.startswith(f"{scheme}{host}") for scheme in ("http://", "https://") for host in blocked):
        return DEFAULT_URL
    return url



def _load_saved_settings() -> dict:
    try:
        data = json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


class JarvisDesktop(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("JARVIS — AI COMMAND CENTER")
        self.geometry("1420x900")
        self.minsize(1180, 740)
        self.configure(bg=BG)
        self.agent = None
        self.busy = False
        self.events = queue.Queue()
        self.tool_names = []
        self.attachments = []
        self._voice_loop_running = False
        self._voice_armed_until = 0.0
        self._orb_phase = 0.0
        self._visual_state = "IDLE"
        self._visual_level = 0.0
        self._orb_after = None
        self.settings = _load_saved_settings()
        self._apply_saved_settings()
        self._build_style()
        self._build_ui()
        self._start_agent()
        self.after(80, self._drain_events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _apply_saved_settings(self):
        profiles = self.settings.get("agents", {})
        if not isinstance(profiles, dict):
            profiles = {}
        active = int(self.settings.get("active_agent", 0) or 0)
        active = max(0, min(2, active))
        legacy = {
            "name": "JARVIS",
            "provider": self.settings.get("provider") or os.environ.get("JARVIS_PROVIDER") or DEFAULT_PROVIDER,
            "url": _safe_endpoint(self.settings.get("url") or os.environ.get("JARVIS_CHAT_URL") or DEFAULT_URL),
            "model": self.settings.get("model") or os.environ.get("JARVIS_CHAT_MODEL") or "openrouter/free",
            "api_key": self.settings.get("api_key") or self.settings.get("openrouter_api_key") or os.environ.get("JARVIS_CHAT_KEY") or os.environ.get("OPENROUTER_API_KEY") or "",
        }
        defaults = {
            "0": legacy,
            "1": {"name": "DeepSeek", "provider": "openai-compatible", "url": DEFAULT_URL, "model": "deepseek/deepseek-chat:free", "api_key": legacy["api_key"]},
            "2": {"name": "GLM", "provider": "openai-compatible", "url": DEFAULT_URL, "model": "z-ai/glm-5.2:free", "api_key": legacy["api_key"]},
        }
        merged = {}
        for key, default in defaults.items():
            value = profiles.get(key, {})
            merged[key] = {**default, **(value if isinstance(value, dict) else {})}
            merged[key]["url"] = _safe_endpoint(merged[key].get("url"))
        profile = merged[str(active)]
        self.settings["active_agent"] = active
        self.settings["agents"] = merged
        self.settings["provider"] = profile["provider"]
        self.settings["url"] = _safe_endpoint(profile["url"])
        profile["url"] = self.settings["url"]
        self.settings["model"] = profile["model"]
        self.settings["api_key"] = profile["api_key"]
        os.environ["JARVIS_PROVIDER"] = profile["provider"]
        os.environ["JARVIS_CHAT_URL"] = self.settings["url"]
        os.environ["JARVIS_CHAT_KEY"] = profile["api_key"]
        os.environ["OPENROUTER_API_KEY"] = profile["api_key"]
        os.environ["JARVIS_CHAT_MODEL"] = profile["model"]
        os.environ["JARVIS_FAST_MODEL"] = merged["0"]["model"]
        os.environ["JARVIS_REASONING_MODEL"] = merged["1"]["model"]
        os.environ["JARVIS_CODING_MODEL"] = merged["2"]["model"]
        os.environ["JARVIS_ADDITIONAL_MODEL"] = self.settings.get("additional_model") or os.environ.get("JARVIS_ADDITIONAL_MODEL") or merged["0"]["model"]
        # Independent consultant providers. Keep secrets out of the repository;
        # they live only in the user's settings/environment.
        os.environ["JARVIS_DEEPSEEK_URL"] = self.settings.get("deepseek_url", os.environ.get("JARVIS_DEEPSEEK_URL", ""))
        os.environ["JARVIS_DEEPSEEK_KEY"] = self.settings.get("deepseek_key", os.environ.get("JARVIS_DEEPSEEK_KEY", ""))
        os.environ["JARVIS_DEEPSEEK_MODEL"] = self.settings.get("deepseek_model", os.environ.get("JARVIS_DEEPSEEK_MODEL", "deepseek/deepseek-chat:free"))
        os.environ["JARVIS_GLM_URL"] = self.settings.get("glm_url", os.environ.get("JARVIS_GLM_URL", ""))
        os.environ["JARVIS_GLM_KEY"] = self.settings.get("glm_key", os.environ.get("JARVIS_GLM_KEY", ""))
        os.environ["JARVIS_GLM_MODEL"] = self.settings.get("glm_model", os.environ.get("JARVIS_GLM_MODEL", "z-ai/glm-5.2:free"))
        disabled = self.settings.get("disabled_tools", [])
        if not isinstance(disabled, list):
            disabled = []
        self.settings["disabled_tools"] = disabled
        os.environ["JARVIS_DISABLED_TOOLS"] = json.dumps(disabled, ensure_ascii=False)
        self.settings.setdefault("voice_enabled", True)
        self.settings.setdefault("tts_enabled", True)
        self.settings.setdefault("tts_gender", "male")
        self.settings.setdefault("tts_engine", "auto")
        self.settings.setdefault("tts_voice", "Dmitri Medium")
        self.settings.setdefault("elevenlabs_api_key", os.environ.get("JARVIS_ELEVENLABS_API_KEY", ""))
        self.settings.setdefault("elevenlabs_voice_id", "srULqtwUV9XZPg1ZCO5w")
        self.settings.setdefault("elevenlabs_model", "eleven_flash_v2_5")
        os.environ["JARVIS_ELEVENLABS_API_KEY"] = self.settings.get("elevenlabs_api_key", "")
        os.environ["JARVIS_ELEVENLABS_VOICE_ID"] = self.settings.get("elevenlabs_voice_id", "srULqtwUV9XZPg1ZCO5w")
        os.environ["JARVIS_ELEVENLABS_MODEL"] = self.settings.get("elevenlabs_model", "eleven_flash_v2_5")
        os.environ["JARVIS_TTS"] = str(self.settings.get("tts_engine", "auto")).strip().lower() or "auto"

    def _save_settings(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        SETTINGS_FILE.write_text(json.dumps(self.settings, ensure_ascii=False, indent=2), encoding="utf-8")

    def _build_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TButton", background=PANEL2, foreground=TEXT, bordercolor=LINE,
                        padding=(12, 9), font=("Segoe UI", 10, "bold"), relief="flat")
        style.map("TButton", background=[("active", "#1b526c")], foreground=[("active", "white")])
        style.configure("Accent.TButton", background="#0e667a", foreground="#f4ffff",
                        bordercolor=CYAN, padding=(14, 9), font=("Segoe UI", 10, "bold"))
        style.map("Accent.TButton", background=[("active", "#148aa1")])
        style.configure("TCheckbutton", background=PANEL2, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", PANEL2)], foreground=[("active", TEXT)])


    def _build_ui(self):
        # CAM-HM inspired holographic cockpit: purple/cyan glassmorphism + reactive ARC reactor.
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self.configure(bg="#03010b")

        root = tk.Frame(self, bg="#03010b")
        root.grid(row=0, column=0, sticky="nsew", padx=10, pady=10)
        root.grid_rowconfigure(1, weight=1)
        root.grid_columnconfigure(1, weight=1)

        # Top glass command strip
        top = tk.Frame(root, bg="#09061a", highlightbackground="#44206a", highlightthickness=1, height=62)
        top.grid(row=0, column=0, columnspan=3, sticky="ew", pady=(0, 8))
        top.grid_propagate(False)
        top.grid_columnconfigure(1, weight=1)
        brand = tk.Frame(top, bg="#09061a")
        brand.grid(row=0, column=0, sticky="nsw", padx=16)
        tk.Label(brand, text="J.A.R.V.I.S", bg="#09061a", fg="#f1eaff",
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", pady=(7, 0))
        tk.Label(brand, text="HOLOGRAPHIC ARC // NEURAL COMMAND", bg="#09061a", fg="#8b63b5",
                 font=("Consolas", 7, "bold")).pack(anchor="w")
        self.top_state = tk.Label(top, text="● SYSTEM ONLINE", bg="#09061a", fg="#00eaff",
                                  font=("Consolas", 9, "bold"))
        self.top_state.grid(row=0, column=1, sticky="w", padx=24)
        self.status = self.top_state

        controls = tk.Frame(top, bg="#09061a")
        controls.grid(row=0, column=2, sticky="e", padx=10)
        self.voice_control = tk.Button(controls, text="◉ VOICE", command=self.toggle_voice,
                                       bg="#170d2b", fg="#d9baff", activebackground="#281047",
                                       activeforeground="#ffffff", relief="flat", bd=0,
                                       padx=11, pady=7, font=("Consolas", 8, "bold"))
        self.voice_control.pack(side="left", padx=3)
        self.tts_control = tk.Button(controls, text="◌ TTS", command=self.toggle_tts,
                                     bg="#170d2b", fg="#d9baff", activebackground="#281047",
                                     activeforeground="#ffffff", relief="flat", bd=0,
                                     padx=11, pady=7, font=("Consolas", 8, "bold"))
        self.tts_control.pack(side="left", padx=3)
        tk.Button(controls, text="⚙ SETTINGS", command=self.show_settings,
                  bg="#170d2b", fg="#d9baff", activebackground="#281047",
                  activeforeground="#ffffff", relief="flat", bd=0,
                  padx=11, pady=7, font=("Consolas", 8, "bold")).pack(side="left", padx=3)

        # Left holographic subsystem rail
        left = tk.Frame(root, bg="#070412", highlightbackground="#32174d", highlightthickness=1, width=205)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 7))
        left.grid_propagate(False)
        tk.Label(left, text="ARC SUBSYSTEMS", bg="#070412", fg="#b68bda",
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=14, pady=(16, 8))
        self.nav_state = {}
        nav_items = (
            ("CORE", "NEURAL CORE", "READY"),
            ("VOICE", "AUDIO MATRIX", "WARM"),
            ("MEMORY", "MEMORY VAULT", "READY"),
            ("TOOLS", "PC AGENT", "READY"),
            ("VISION", "VISION / OCR", "READY"),
            ("NETWORK", "UPLINK", "ONLINE"),
        )
        for key, title, state in nav_items:
            card = tk.Frame(left, bg="#0c0719", highlightbackground="#24133a", highlightthickness=1)
            card.pack(fill="x", padx=9, pady=3)
            dot = tk.Label(card, text="◆", bg="#0c0719", fg="#8b4dff", font=("Segoe UI", 8))
            dot.pack(side="left", padx=(9, 7), pady=8)
            body = tk.Frame(card, bg="#0c0719")
            body.pack(side="left", fill="x", expand=True, pady=6)
            tk.Label(body, text=title, bg="#0c0719", fg="#ded0ed",
                     font=("Segoe UI", 8, "bold")).pack(anchor="w")
            val = tk.Label(body, text=state, bg="#0c0719", fg="#6d4c87",
                           font=("Consolas", 6, "bold"))
            val.pack(anchor="w")
            self.nav_state[key] = (dot, val)
        tk.Frame(left, bg="#3b1b59", height=1).pack(fill="x", padx=13, pady=12)
        tk.Button(left, text="◈  MODULE MATRIX", command=self.show_tools,
                  bg="#120923", fg="#c78cff", activebackground="#25113f",
                  activeforeground="#ffffff", relief="flat", bd=0,
                  anchor="w", padx=12, pady=10,
                  font=("Consolas", 8, "bold")).pack(fill="x", padx=9)
        tk.Label(left, text="GLASS HUD\nAUDIO REACTIVE\nTHREE-DIMENSIONAL ARC\nOFFLINE-FIRST INTELLIGENCE",
                 bg="#070412", fg="#5b4270", justify="left",
                 font=("Consolas", 7), anchor="w").pack(fill="x", padx=14, pady=16)

        # Center reactor stage
        center = tk.Frame(root, bg="#03020a", highlightbackground="#3b1b59", highlightthickness=1)
        center.grid(row=1, column=1, sticky="nsew")
        center.grid_rowconfigure(0, weight=1)
        center.grid_columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(center, bg="#03020a", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        tk.Label(center, text="ARC REACTOR // HOLOGRAPHIC CORE", bg="#03020a", fg="#eee4ff",
                 font=("Segoe UI", 14, "bold")).place(relx=.5, rely=.025, anchor="n")
        tk.Label(center, text="PROCEDURAL 3D  •  AUDIO REACTIVE  •  LIVE NEURAL LINK",
                 bg="#03020a", fg="#76558f", font=("Consolas", 7, "bold")).place(
                     relx=.5, rely=.072, anchor="n")
        self.hud_text = tk.Label(center, text="JARVIS READY", bg="#03020a", fg="#00eaff",
                                 font=("Segoe UI", 11, "bold"))
        self.hud_text.place(relx=.5, rely=.84, anchor="center")
        self.hud_state = tk.Label(center, text="STATE // IDLE", bg="#03020a", fg="#00eaff",
                                  font=("Consolas", 8, "bold"))
        self.hud_state.place(relx=.5, rely=.88, anchor="center")
        self.hud_hint = tk.Label(center, text="СКАЖИТЕ «ДЖАРВИС»  •  REACTOR READY",
                                 bg="#03020a", fg="#6b4d80", font=("Consolas", 7))
        self.hud_hint.place(relx=.5, rely=.92, anchor="center")

        # Right glass telemetry
        right = tk.Frame(root, bg="#070412", highlightbackground="#32174d", highlightthickness=1, width=235)
        right.grid(row=1, column=2, sticky="nsew", padx=(7, 0))
        right.grid_propagate(False)
        tk.Label(right, text="LIVE TELEMETRY", bg="#070412", fg="#e7dcf5",
                 font=("Consolas", 10, "bold")).pack(anchor="w", padx=14, pady=(16, 2))
        tk.Label(right, text="NEURAL / SYSTEM / AUDIO", bg="#070412", fg="#624875",
                 font=("Consolas", 6, "bold")).pack(anchor="w", padx=14, pady=(0, 10))
        self.metrics = {}
        for name in ("Core", "AI Provider", "Memory", "Tools", "Voice", "TTS"):
            rowm = tk.Frame(right, bg="#0c0719", highlightbackground="#24133a", highlightthickness=1)
            rowm.pack(fill="x", padx=9, pady=3)
            tk.Label(rowm, text=name.upper(), bg="#0c0719", fg="#765d87",
                     font=("Consolas", 7, "bold")).pack(side="left", padx=8, pady=8)
            value = tk.Label(rowm, text="—", bg="#0c0719", fg="#00eaff",
                             font=("Consolas", 7, "bold"))
            value.pack(side="right", padx=8)
            self.metrics[name] = value
        tk.Frame(right, bg="#3b1b59", height=1).pack(fill="x", padx=12, pady=11)
        tk.Label(right, text="QUICK ACTIONS", bg="#070412", fg="#e7dcf5",
                 font=("Consolas", 8, "bold")).pack(anchor="w", padx=13, pady=(0, 5))
        for label, cmd in (
            ("SYSTEM SCAN", "Покажи полный статус системы"),
            ("TIME", "Который сейчас час?"),
            ("CAPABILITIES", "Что ты умеешь?"),
            ("PC DIAGNOSTIC", "Проверь состояние компьютера"),
        ):
            tk.Button(right, text="›  " + label, command=lambda c=cmd: self._command_from_hud(c),
                      bg="#0c0719", fg="#b9a7c6", activebackground="#211035",
                      activeforeground="#00eaff", relief="flat", bd=0, anchor="w",
                      padx=10, pady=8, font=("Consolas", 7, "bold")).pack(fill="x", padx=9, pady=2)

        # Bottom command glass
        dock = tk.Frame(root, bg="#09061a", highlightbackground="#44206a", highlightthickness=1)
        dock.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        dock.grid_columnconfigure(0, weight=1)
        self.input = tk.Entry(dock, bg="#0c0719", fg="#f1eaff", insertbackground="#00eaff",
                              relief="flat", bd=0, font=("Segoe UI", 10))
        self.input.grid(row=0, column=0, sticky="ew", padx=9, pady=8, ipady=9)
        self.input.bind("<Return>", lambda _e: self.send())
        self.voice_button = tk.Button(dock, text="◉  LISTEN", command=self.start_voice,
                                       bg="#17102a", fg="#d7b8ff", activebackground="#2a1548",
                                       activeforeground="#ffffff", relief="flat", bd=0,
                                       padx=13, pady=8, font=("Consolas", 8, "bold"))
        self.voice_button.grid(row=0, column=1, padx=3)
        self.attach_button = tk.Button(dock, text="＋ FILE", command=self.pick_attachments,
                                       bg="#0d0918", fg="#a78bb8", activebackground="#211035",
                                       activeforeground="#00eaff", relief="flat", bd=0,
                                       padx=13, pady=8, font=("Consolas", 8, "bold"))
        self.attach_button.grid(row=0, column=2, padx=3)
        self.send_button = tk.Button(dock, text="EXECUTE  ›", command=self.send,
                                      bg="#5b20a8", fg="#ffffff", activebackground="#7c31d8",
                                      activeforeground="#ffffff", relief="flat", bd=0,
                                      padx=17, pady=8, font=("Consolas", 8, "bold"))
        self.send_button.grid(row=0, column=3, padx=(3, 9))

        self.attachment_label = tk.Label(root, text="ATTACHMENTS // NONE", bg="#03010b",
                                         fg="#5b4270", anchor="w", font=("Consolas", 6))
        self.attachment_label.grid(row=3, column=0, columnspan=3, sticky="ew", padx=6, pady=(3, 2))
        self.chat = tk.Text(root, bg="#05020e", fg=TEXT, insertbackground="#00eaff",
                            relief="flat", wrap="word", padx=12, pady=7,
                            font=("Segoe UI", 8), height=4, state="disabled",
                            highlightbackground="#24133a", highlightthickness=1)
        self.chat.grid(row=4, column=0, columnspan=3, sticky="ew")
        self.chat.tag_configure("who", foreground="#b87cff", font=("Consolas", 7, "bold"))
        self.chat.tag_configure("stream_body", foreground=TEXT)
        self._set_visual_state("IDLE", 0.0)
        self.after(40, self._draw_orb)

    def _build_sidebar(self):
        pass

    def _build_center(self):
        pass

    def _build_right(self):
        pass

    def _command_from_hud(self, command):
        self.input.delete(0, "end")
        self.input.insert(0, command)
        self.send()


    def _set_visual_state(self, state, level=0.0):
        """Update the visual HUD and reactor state without assuming optional widgets exist."""
        state = str(state or "IDLE").upper()
        if state not in {"IDLE", "LISTENING", "THINKING", "SPEAKING", "ERROR"}:
            state = "IDLE"
        self._visual_state = state
        self._visual_level = max(0.0, min(1.0, float(level or 0.0)))
        accent = RED if state == "ERROR" else (YELLOW if state == "THINKING" else CYAN)
        labels = {
            "IDLE": ("JARVIS READY", "STATE // IDLE"),
            "LISTENING": ("LISTENING", "STATE // LISTENING"),
            "THINKING": ("PROCESSING", "STATE // THINKING"),
            "SPEAKING": ("JARVIS SPEAKING", "STATE // SPEAKING"),
            "ERROR": ("SYSTEM ERROR", "STATE // ERROR"),
        }
        title, state_text = labels[state]
        for name, value in (("hud_text", title), ("hud_state", state_text)):
            widget = getattr(self, name, None)
            if widget is not None and widget.winfo_exists():
                widget.configure(text=value, fg=accent)
        widget = getattr(self, "top_state", None)
        if widget is not None and widget.winfo_exists():
            widget.configure(text=f"● ONLINE / {state}", fg=accent)
        widget = getattr(self, "status", None)
        if widget is not None and widget.winfo_exists():
            widget.configure(text=f"● {state}", fg=accent)
        widget = getattr(self, "hud_hint", None)
        if widget is not None and widget.winfo_exists():
            hints = {
                "IDLE": "СКАЖИТЕ «ДЖАРВИС»  •  ГОТОВ К КОМАНДЕ",
                "LISTENING": "СЛУШАЮ  •  ГОВОРИТЕ КОМАНДУ",
                "THINKING": "ОБРАБОТКА  •  ВЫБИРАЮ ИНСТРУМЕНТ",
                "SPEAKING": "ОТВЕЧАЮ  •  ГОЛОСОВОЙ ВЫВОД",
                "ERROR": "ОШИБКА  •  ПРОВЕРЬТЕ СОСТОЯНИЕ СИСТЕМЫ",
            }
            widget.configure(text=hints[state], fg="#527887" if state != "ERROR" else RED)
        nav = getattr(self, "nav_state", {})
        if isinstance(nav, dict):
            for key, pair in nav.items():
                try:
                    dot, value = pair
                    active = {
                        "VOICE": state == "LISTENING",
                        "CORE": state == "THINKING",
                    }.get(key, False)
                    dot.configure(fg=accent if active else CYAN)
                    if active:
                        value.configure(fg=accent, text=state)
                except Exception:
                    pass

    def _draw_orb(self):
        """Holographic 3D ARC reactor inspired by cam-hm/jarvis: neon glass, depth, particles and audio reactivity."""
        self.canvas.delete("all")
        w=max(520,self.canvas.winfo_width()); h=max(430,self.canvas.winfo_height())
        cx,cy=w*.5,h*.47; p=self._orb_phase; state=self._visual_state; level=self._visual_level
        accent = RED if state=="ERROR" else (YELLOW if state=="THINKING" else "#00eaff")
        purple="#a85cff"; violet="#6f35d4"; deep="#09051a"
        self.canvas.create_rectangle(0,0,w,h,fill=deep,outline="")
        # Holographic atmosphere / radial fields
        for rr, col in ((270,"#160c2d"),(235,"#1c0e38"),(205,"#241146"),(175,"#2d1554")):
            self.canvas.create_oval(cx-rr,cy-rr*.68,cx+rr,cy+rr*.68,outline=col,width=1)
        # Perspective floor / scan grid
        horizon=cy+h*.23
        for i in range(11):
            yy=horizon+(i*i)*3.1
            self.canvas.create_line(0,yy,w,yy,fill="#160d26",width=1)
        for i in range(-13,14):
            self.canvas.create_line(cx+i*28,horizon,cx+i*120,h,fill="#120a20",width=1)
        # Floating particles with depth
        for i in range(150):
            a=i*math.tau/150+p*(.025+(i%9)*.003)
            z=.5+.5*math.sin(a*1.7+i*1.91)
            rx=110+170*z; ry=48+100*z
            x=cx+math.cos(a)*rx; y=cy+math.sin(a)*ry*.62
            r=.35+1.8*z*(.45+level*1.7)
            col=accent if i%29==0 or (state=="LISTENING" and i%11==0) else ("#6339a0" if z>.55 else "#292044")
            self.canvas.create_oval(x-r,y-r,x+r,y+r,fill=col,outline="")
        # Multiple tilted 3D rings
        rings=((232,84,.12,.045,1,"#5b35a1"),(208,72,-.38,-.075,1,"#8b4fe2"),
               (181,62,.58,.11,2,"#00a8d0"),(154,53,-.76,-.15,1,"#6c3ac5"),
               (126,44,.28,.21,2,accent))
        for rx,ry,tilt,rot,width,col in rings:
            ang0=p*rot+tilt; pts=[]
            for j in range(161):
                a=ang0+math.tau*j/160; z=.5+.5*math.sin(a)
                x=cx+math.cos(a)*rx; y=cy+math.sin(a)*ry*(.76+.24*z)
                pts.append((x,y))
            for j in range(len(pts)-1):
                self.canvas.create_line(*pts[j],*pts[j+1],fill=col,width=width)
        # Segmented holographic outer arcs
        for ring_r, segs, col in ((247,24,purple),(218,18,"#00cfe8")):
            for i in range(segs):
                gap=.055 if i%2==0 else .12
                a1=p*(.06 if ring_r==247 else -.09)+i*math.tau/segs+gap
                a2=a1+math.tau/segs-gap*2.2
                pts=[]
                for j in range(10):
                    a=a1+(a2-a1)*j/9
                    pts.append((cx+math.cos(a)*ring_r,cy+math.sin(a)*ring_r*.55))
                for j in range(len(pts)-1): self.canvas.create_line(*pts[j],*pts[j+1],fill=col,width=2)
        # Hexagonal technical lattice around core
        for radius in (74,92,111):
            pts=[]
            for i in range(7):
                a=p*.16+i*math.tau/6
                pts.append((cx+math.cos(a)*radius,cy+math.sin(a)*radius*.78))
            self.canvas.create_polygon(pts,outline="#3c2263",fill="",width=1)
        # Audio-reactive waveform spokes
        spokes=56
        for i in range(spokes):
            a=i*math.tau/spokes+p*.9
            wave=.5+.5*math.sin(p*5.2+i*.71)
            r1=55+level*18; r2=118+wave*18+level*58*wave
            x1,y1=cx+math.cos(a)*r1,cy+math.sin(a)*r1*.76
            x2,y2=cx+math.cos(a)*r2,cy+math.sin(a)*r2*.76
            col=accent if i%7==0 else ("#56318a" if i%2 else "#164d62")
            self.canvas.create_line(x1,y1,x2,y2,fill=col,width=2 if i%7==0 else 1)
        # Rotating radar sweep
        sweep=(p*1.65)%math.tau
        for k in range(14,0,-1):
            a=sweep-k*.025
            x=cx+math.cos(a)*235; y=cy+math.sin(a)*84
            self.canvas.create_line(cx,cy,x,y,fill="#241448",width=1)
        sx=cx+math.cos(sweep)*235; sy=cy+math.sin(sweep)*84
        self.canvas.create_line(cx,cy,sx,sy,fill=accent,width=2)
        self.canvas.create_oval(sx-4,sy-4,sx+4,sy+4,fill=accent,outline="")
        # Volumetric reactor core
        pulse=1+.05*math.sin(p*4)+level*.32
        for rr,col,width in ((83,"#28134d",2),(69,"#3d1c6d",2),(57,"#56308e",2),(46,accent,2)):
            self.canvas.create_oval(cx-rr*pulse,cy-rr*pulse,cx+rr*pulse,cy+rr*pulse,outline=col,width=width)
        self.canvas.create_oval(cx-37,cy-37,cx+37,cy+37,fill="#080612",outline="#8d55db",width=2)
        core_r=17+6*pulse+11*level
        self.canvas.create_oval(cx-core_r,cy-core_r,cx+core_r,cy+core_r,fill=accent,outline="")
        self.canvas.create_oval(cx-core_r*.45,cy-core_r*.45,cx+core_r*.45,cy+core_r*.45,fill="#f4fbff",outline="")
        self.canvas.create_text(cx,cy,text="J",fill="#10051d",font=("Segoe UI",20,"bold"))
        # Orbital module nodes
        labels=("CORE","VOICE","AI","TOOLS","MEMORY","VISION","SYSTEM","NET")
        for i,label in enumerate(labels):
            a=p*(.10 if i%2==0 else -.07)+i*math.tau/8
            rx,ry=(232,84) if i%2==0 else (181,62)
            x,y=cx+math.cos(a)*rx,cy+math.sin(a)*ry
            self.canvas.create_oval(x-5,y-5,x+5,y+5,fill=accent if i<2 else "#43236e",outline="#8b54cf")
            self.canvas.create_text(x,y+(15 if y<cy else -15),text=label,fill="#9c79b5",font=("Consolas",6,"bold"))
        self.canvas.create_text(16,16,text="CAM-HM // ARC HOLOGRAPHIC HUD",anchor="nw",fill="#76558f",font=("Consolas",7,"bold"))
        self.canvas.create_text(w-16,16,text="AUDIO // "+state,anchor="ne",fill=accent,font=("Consolas",7,"bold"))
        self.canvas.create_text(cx,h-18,text="J A R V I S  •  NEURAL REACTOR LINK",fill="#674b7e",font=("Consolas",7,"bold"))
        self._orb_phase+= {"IDLE":.025,"LISTENING":.085,"THINKING":.12,"SPEAKING":.10,"ERROR":.16}.get(state,.03)
        self._orb_after=self.after(33,self._draw_orb)

    def _start_agent(self):
        def work():
            try:
                agent = build_agent()
                self.events.put(("ready", agent))
                threading.Thread(target=self._warmup_stt, daemon=True).start()
            except Exception as exc:
                self.events.put(("agent_error", str(exc)))
        threading.Thread(target=work, daemon=True).start()

    def _warmup_stt(self):
        try:
            stt.warmup()
            self.events.put(("stt_ready", None))
        except Exception as exc:
            self.events.put(("stt_error", str(exc)))

    def _start_voice_loop(self):
        if not self.settings.get("voice_enabled", True) or self._voice_loop_running or not voice.available():
            return
        self._voice_loop_running = True
        self.voice_button.config(text="🎙 СЛУШАЮ")
        self.voice_control.config(text="🔊  Голос: ВКЛ")
        def on_speech_start():
            if tts.is_playing():
                tts.stop()
                self.events.put(("voice_status", "Перебивание: TTS остановлен, слушаю вас."))
        def work():
            wake_words = ("jarvis", "джарвис")
            while self._voice_loop_running and self.settings.get("voice_enabled", True):
                try:
                    heard = voice.listen_for_phrase(
                        silence_seconds=0.55,
                        max_seconds=None,
                        start_timeout=None,
                        on_speech_start=on_speech_start,
                    )
                    if not heard or not self._voice_loop_running:
                        continue
                    normalized = " ".join(heard.lower().split())
                    command = None
                    activated = False
                    for word in wake_words:
                        if normalized.startswith(word):
                            activated = True
                            command = normalized[len(word):].strip(" ,.!")
                            self._voice_armed_until = float("inf")
                            break
                    if activated and not command:
                        self.events.put(("voice_status", "Jarvis активирован. Слушаю вас."))
                        command = voice.listen_for_phrase(
                            silence_seconds=0.55,
                            max_seconds=None,
                            start_timeout=None,
                            on_speech_start=on_speech_start,
                        )
                    elif not activated and time.monotonic() < self._voice_armed_until:
                        command = normalized
                    else:
                        continue
                    if command in {"стоп", "режим ожидания", "перейди в режим ожидания", "спасибо джарвис", "спасибо джарвис"}:
                        self._voice_armed_until = 0.0
                        self.events.put(("voice_status", "Голосовой режим: ожидание. Скажите «Джарвис», чтобы продолжить."))
                        continue
                    if command and self._voice_loop_running:
                        self._voice_armed_until = float("inf")
                        self.events.put(("voice_text", command))
                except Exception as exc:
                    self.events.put(("voice_error", str(exc)))
                    break
            self._voice_loop_running = False
        threading.Thread(target=work, daemon=True).start()

    def _stop_voice(self):
        self._voice_loop_running = False
        self.voice_button.config(text="🎙 ГОЛОС")
        self._append("VOICE", "Голосовой цикл остановлен. Его можно включить снова кнопкой «Голос». ")

    def toggle_voice(self):
        self.settings["voice_enabled"] = not self.settings.get("voice_enabled", True)
        self._save_settings()
        if self.settings["voice_enabled"]:
            self._start_voice_loop()
            self.voice_control.config(text="🔊  Голос: ВКЛ")
        else:
            self._stop_voice()
            self.voice_control.config(text="🔇  Голос: ВЫКЛ")
        self._update_voice_status()

    def toggle_tts(self):
        self.settings["tts_enabled"] = not self.settings.get("tts_enabled", True)
        self._save_settings()
        if not self.settings["tts_enabled"]:
            tts.stop()
        self.tts_control.config(text=("🗣  TTS: ВКЛ" if self.settings["tts_enabled"] else "🗣  TTS: ВЫКЛ"))
        self._update_voice_status()

    def _update_voice_status(self):
        stt_ok = voice.available() and self.settings.get("voice_enabled", True)
        tts_engine = tts.current_engine()
        tts_ok = self.settings.get("tts_enabled", True) and tts_engine != "off"
        self.metrics["Voice"].config(text="ON" if stt_ok else "OFF", fg=GREEN if stt_ok else RED)
        self.metrics["TTS"].config(text=tts_engine.upper() if tts_ok else "OFF", fg=GREEN if tts_ok else RED)

    def _drain_events(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "ready":
                    self.agent = event[1]
                    self.tool_names = list(self.agent.tools.names())
                    provider = getattr(self.agent.provider, "name", "unknown").upper()
                    self.status.config(text="● ONLINE", fg=GREEN)
                    self.hud_text.config(text="Ядро активно\nAI: " + provider)
                    self.metrics["Core"].config(text="ONLINE", fg=GREEN)
                    self.metrics["AI Provider"].config(text=provider)
                    self.metrics["Memory"].config(text="ACTIVE", fg=GREEN)
                    self.metrics["Tools"].config(text=str(len(self.tool_names)), fg=GREEN)
                    self.tools_button.config(text=f"⌁  Модули ({len(self.tool_names)}/{len(TOOLS)})")
                    self.enabled_label.config(text=f"Активно модулей: {len(self.tool_names)} из {len(TOOLS)}\nОтключено: {len(TOOLS)-len(self.tool_names)}")
                    self._update_voice_status()
                    self.side_core.config(text="● CORE  —  ACTIVE", fg=GREEN)
                    self._append("JARVIS", f"Система готова. Активных модулей: {len(self.tool_names)} из {len(TOOLS)}.")
                    if self.settings.get("voice_enabled", True):
                        self._start_voice_loop()
                elif kind == "stt_ready":
                    self.metrics["Voice"].config(text="READY", fg=GREEN)
                    self.side_voice.config(text="◉ ГОЛОС — ГОТОВ", fg=GREEN)
                elif kind == "stt_error":
                    self.metrics["Voice"].config(text="ERROR", fg=RED)
                    self.side_voice.config(text="◉ ГОЛОС — ОШИБКА", fg=RED)
                    self._append("VOICE", "STT: " + event[1])
                elif kind == "reply_delta":
                    self._streaming_reply = getattr(self, "_streaming_reply", "") + str(event[1])
                    self._set_visual_state("THINKING", 0.7)
                    self._replace_streaming_reply(self._streaming_reply)
                elif kind == "reply":
                    reply = event[1]
                    self._set_visual_state("SPEAKING", 0.65)
                    if getattr(self, "_streaming_reply", ""):
                        self._replace_streaming_reply(reply, final=True)
                    else:
                        self._append("JARVIS", reply)
                    self._streaming_reply = ""
                    self.busy = False
                    self.send_button.config(state="normal")
                    self.attach_button.config(state="normal")
                    self.status.config(text="● ONLINE", fg=GREEN)
                    self._set_visual_state("IDLE", 0.0)
                    if self.settings.get("tts_enabled", True):
                        threading.Thread(target=self._speak_reply, args=(reply,), daemon=True).start()
                elif kind == "voice_text":
                    self._set_visual_state("LISTENING", 0.75)
                    if self.busy:
                        continue
                    self.input.delete(0, "end")
                    self.input.insert(0, event[1])
                    self.send(event[1])
                elif kind == "voice_status":
                    self._append("VOICE", event[1])
                elif kind == "voice_error":
                    self._set_visual_state("ERROR")
                    self._append("VOICE", "Ошибка: " + event[1])
                elif kind == "tts_error":
                    self._append("VOICE", "ElevenLabs недоступен — автоматически использую локальный мужской голос Piper.")
                    self.metrics["TTS"].config(fg=RED)
                elif kind == "agent_error":
                    self._set_visual_state("ERROR")
                    self.status.config(text="● ERROR", fg=RED)
                    self._append("SYSTEM", "Не удалось запустить ядро: " + event[1])
                    self.busy = False
                    self.send_button.config(state="normal")
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _speak_reply(self, text):
        try:
            self._set_visual_state("SPEAKING", 0.8)
            tts.speak_and_play(text)
            self._set_visual_state("IDLE", 0.0)
        except Exception as exc:
            self.events.put(("tts_error", str(exc)))

    def _replace_streaming_reply(self, text, final=False):
        self.chat.configure(state="normal")
        if not getattr(self, "_streaming_reply_started", False):
            self.chat.insert("end", "JARVIS\\n", "who")
            self._streaming_reply_started = True
        self.chat.delete("end-1c linestart", "end")
        self.chat.insert("end", text, "stream_body")
        if final:
            self.chat.insert("end", "\\n\\n")
            self._streaming_reply_started = False
        self.chat.tag_configure("stream_body", foreground=TEXT)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _append(self, who, text):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{who}\n", "who")
        self.chat.insert("end", text + "\n\n", "body")
        self.chat.tag_configure("who", foreground=CYAN, font=("Segoe UI", 9, "bold"))
        self.chat.tag_configure("body", foreground=TEXT)
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _handle_voice_setting_command(self, text):
        """Handle voice-gender commands locally, without sending them to the AI backend."""
        normalized = " ".join(text.lower().replace("ё", "е").split())
        male_phrases = ("голос на мужской", "мужской голос", "сделай голос мужским", "поставь мужской голос", "включи мужской голос")
        female_phrases = ("голос на женский", "женский голос", "сделай голос женским", "поставь женский голос", "включи женский голос")
        if any(phrase in normalized for phrase in male_phrases):
            gender = "male"
            message = "Готово. Установил мужской голос JARVIS."
        elif any(phrase in normalized for phrase in female_phrases):
            self.events.put(("reply", "В этой сборке доступен русский мужской голос Dmitri."))
            return True
        else:
            return False
        self.settings["tts_gender"] = gender
        os.environ["JARVIS_TTS_GENDER"] = gender
        tts.set_gender(gender)
        self._save_settings()
        self.events.put(("reply", message))
        return True

    def pick_attachments(self):
        paths=filedialog.askopenfilenames(parent=self,title="Прикрепить файлы, фото, видео или аудио",
            filetypes=[("Все файлы","*.*")])
        if not paths: return
        self.attachments=[]
        for raw in paths:
            p=Path(raw)
            try: size=p.stat().st_size
            except OSError: continue
            if size<=50*1024*1024:
                self.attachments.append({"path":str(p),"name":p.name,"mime":mimetypes.guess_type(p.name)[0] or "application/octet-stream","size":size})
        self._refresh_attachment_label()

    def _refresh_attachment_label(self):
        if not self.attachments:
            self.attachment_label.config(text="Вложений нет",fg=MUTED); return
        names=", ".join(x["name"] for x in self.attachments)
        self.attachment_label.config(text=f"📎 {len(self.attachments)} файл(ов): {names[:140]}",fg=CYAN)

    def _build_attachment_context(self):
        if not self.attachments: return ""
        parts=["ВЛОЖЕНИЯ ПОЛЬЗОВАТЕЛЯ:"]
        for x in self.attachments:
            p=Path(x["path"])
            line=f"- {x['name']} | {x['mime']} | {x['size']} байт | путь: {p}"
            if x["size"] <= 15*1024*1024:
                try:
                    suffix=p.suffix.lower()
                    if suffix in {".txt",".md",".csv",".json",".xml",".log",".yaml",".yml",".toml",".ini",".py",".ps1",".js",".ts",".html",".css"}:
                        line+="\n  Содержимое:\n"+p.read_text(encoding="utf-8",errors="replace")[:120000]
                    elif suffix in {".pdf",".docx",".xlsx",".xlsm",".zip",".tar",".gz",".7z",".rar"}:
                        from agent.tools.universal import inspect_file
                        line+="\n  Анализ файла:\n"+inspect_file(str(p))[:120000]
                except Exception as exc:
                    line+=f"\n  Не удалось прочитать содержимое автоматически: {exc}"
            parts.append(line)
        return "\n".join(parts)

    def _build_attachment_payload(self):
        for x in self.attachments:
            mime=x.get("mime","").lower()
            if not (mime.startswith("image/") or mime.startswith("audio/")):
                continue
            p=Path(x["path"])
            try:
                if p.stat().st_size > 15*1024*1024:
                    continue
                return {"name":p.name,"mime":mime,"data":base64.b64encode(p.read_bytes()).decode("ascii")}
            except OSError:
                continue
        return None

    def _clear_attachments(self):
        self.attachments=[]; self._refresh_attachment_label()

    def send(self, text=None):
        if text is None: text=self.input.get()
        text=text.strip()
        if not text or self.agent is None or self.busy: return
        context=self._build_attachment_context()
        shown = text + (
            "\n📎 " + ", ".join(x["name"] for x in self.attachments)
            if self.attachments else ""
        )
        self.input.delete(0, "end")
        self._append("ВЫ", shown)
        if self._handle_voice_setting_command(text):
            self._clear_attachments(); return
        prompt=text+("\n\n"+context if context else "")
        attachment_payload=self._build_attachment_payload()
        self.busy=True; self.send_button.config(state="disabled"); self.attach_button.config(state="disabled")
        self.status.config(text="● PROCESSING",fg=CYAN)
        def work():
            provider = getattr(self.agent, "provider", None)
            try:
                if provider is not None and hasattr(provider, "on_delta"):
                    provider.on_delta = lambda delta: self.events.put(("reply_delta", delta))
                result=self.agent.handle(prompt, attachment=attachment_payload)
                if provider is not None and hasattr(provider, "on_delta"):
                    provider.on_delta = None
                self.events.put(("reply",result.text))
            except Exception as exc:
                if provider is not None and hasattr(provider, "on_delta"):
                    provider.on_delta = None
                self.events.put(("reply","Ошибка: "+str(exc)))
        self._clear_attachments()
        threading.Thread(target=work,daemon=True).start()

    def start_voice(self):
        if not self.settings.get("voice_enabled", True):
            self._append("VOICE", "Голос выключен. Нажмите кнопку «Голос: ВЫКЛ», чтобы включить.")
            return
        if self._voice_loop_running:
            self._append("VOICE", "Голосовой режим уже слушает.")
            return
        self._start_voice_loop()
        if not self._voice_loop_running:
            self._append("VOICE", "Голосовой ввод недоступен. Проверьте зависимости STT.")

    def _draw_tool_avatar(self, canvas, kind, seed):
        palette = {
            "core": (CYAN, "#0b5d73"), "folder": ("#6bdcff", "#155a76"), "danger": (RED, "#7a2334"),
            "app": ("#b68cff", "#4b2c7a"), "web": (GREEN, "#1c6c4a"), "audio": (YELLOW, "#805d1b"),
            "screen": ("#73a7ff", "#294d87"), "process": ("#f39cff", "#703d78"), "clipboard": ("#9ee6d1", "#326e60"),
            "time": ("#8ed0ff", "#315e83"), "voice": ("#ff9dce", "#74345b"), "weather": ("#80c9ff", "#24577d"),
            "intel": ("#d4a7ff", "#633a83"), "image": ("#91e7ff", "#286b80"), "mail": ("#ffad8a", "#7d3f2d"),
            "memory": ("#72f0ad", "#26754b"), "graph": ("#9fa9ff", "#394580"), "calc": ("#f5df72", "#75661c"),
        }
        c1, c2 = palette.get(kind, (CYAN, "#155a76"))
        canvas.delete("all")
        cx, cy = 32, 32
        canvas.create_oval(6, 9, 58, 58, fill="#02050a", outline="")
        angle = (seed % 11) * 0.42
        for r, flat, off in ((22, 8, 0), (17, 6, 1.2), (12, 4, 2.2)):
            a = angle + off
            x = cx + math.cos(a) * 12
            y = cy + math.sin(a) * flat
            canvas.create_oval(x-r, y-flat, x+r, y+flat, outline=c2, width=1)
        points = []
        for i in range(6):
            a = angle + i * math.pi / 3
            points.append((cx + math.cos(a) * 20, cy + math.sin(a) * 20))
        for x, y in points:
            canvas.create_oval(x-2, y-2, x+2, y+2, fill=c1, outline="")
        canvas.create_oval(cx-9, cy-9, cx+9, cy+9, fill=c1, outline="")
        canvas.create_oval(cx-5, cy-6, cx+1, cy, fill="#eaffff", outline="")
        canvas.create_text(cx, 62, text=str(seed), fill=c1, font=("Segoe UI", 6, "bold"))

    def _open_module_details(self, name, title, desc, enabled):
        items = []
        if name == "osint":
            items = [(n, d) for n, t, d, k in TOOLS if k == "intel"]
        elif name == "ps":
            try:
                import csv, subprocess
                out = subprocess.run(["tasklist", "/fo", "csv", "/nh"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8).stdout
                items = [(r[0], "PID " + r[1]) for r in csv.reader(out.splitlines()) if len(r) >= 2]
            except Exception:
                items = []
        elif name == "launch":
            try:
                import subprocess
                out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-StartApps | Sort-Object Name | ForEach-Object { \"$($_.Name)|$($_.AppID)\" }"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=8).stdout
                items = [(a.strip(), b.strip()) for line in out.splitlines() if "|" in line for a, b in [line.split("|", 1)] if a.strip()]
            except Exception:
                items = []
        if not items: items = [(name, desc)]
        win = tk.Toplevel(self); win.title("JARVIS — " + title); win.configure(bg=BG); win.geometry("820x650")
        tk.Label(win, text=title, bg=BG, fg=CYAN, font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=20, pady=(18, 4))
        tk.Label(win, text=("● АКТИВЕН" if enabled else "● ВЫКЛЮЧЕН"), bg=BG, fg=GREEN if enabled else RED, font=("Segoe UI", 10, "bold")).pack(anchor="w", padx=20)
        tk.Label(win, text="Полный перечень: " + str(len(items)), bg=BG, fg=MUTED).pack(anchor="w", padx=20, pady=8)
        text = tk.Text(win, bg=PANEL, fg=TEXT, relief="flat", wrap="word", font=("Segoe UI", 10))
        text.pack(fill="both", expand=True, padx=20, pady=10)
        for item, detail in items: text.insert("end", item + "  —  " + detail + "\n")
        text.configure(state="disabled")
        ttk.Button(win, text="ЗАКРЫТЬ", command=win.destroy).pack(anchor="e", padx=20, pady=(0, 14))
    def show_tools(self):
        win = tk.Toplevel(self)
        win.title("JARVIS — Управление модулями")
        win.configure(bg=BG)
        win.geometry("1120x760")
        win.minsize(920, 600)
        win.transient(self)
        header = tk.Frame(win, bg=BG)
        header.pack(fill="x", padx=20, pady=(18, 8))
        tk.Label(header, text="АКТИВНЫЕ МОДУЛИ", bg=BG, fg=CYAN,
                 font=("Segoe UI", 18, "bold")).pack(side="left")
        self.tool_status_label = tk.Label(header, text="", bg=BG, fg=GREEN,
                                          font=("Segoe UI", 10, "bold"))
        self.tool_status_label.pack(side="right")
        tk.Label(win, text="Нажми на модуль, чтобы открыть его. Переключатель «АКТИВЕН» включает или отключает функцию. JARVIS сам выбирает нужный инструмент по вашей задаче — команды вводить не нужно.",
                 bg=BG, fg=MUTED, font=("Segoe UI", 9), wraplength=1040, justify="left").pack(anchor="w", padx=22, pady=(0, 10))

        outer = tk.Frame(win, bg=PANEL, highlightbackground=LINE, highlightthickness=1)
        outer.pack(fill="both", expand=True, padx=20, pady=(0, 12))
        canvas = tk.Canvas(outer, bg=PANEL, highlightthickness=0)
        scrollbar = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        canvas.configure(yscrollcommand=scrollbar.set)
        inner = tk.Frame(canvas, bg=PANEL)
        window_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        def resize_inner(_event=None):
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window_id, width=canvas.winfo_width())
        inner.bind("<Configure>", resize_inner)
        canvas.bind("<Configure>", resize_inner)

        disabled = set(self.settings.get("disabled_tools", []))
        switches = {}
        catalog = {name: (title, desc, kind) for name, title, desc, kind in TOOLS}
        for index, (name, title, desc, kind) in enumerate(TOOLS, start=1):
            enabled_var = tk.BooleanVar(value=name not in disabled)
            switches[name] = enabled_var
            row = (index - 1) // 2
            col = (index - 1) % 2
            inner.grid_columnconfigure(col, weight=1)
            card = tk.Frame(inner, bg=PANEL2, highlightbackground=LINE, highlightthickness=1, cursor="hand2")
            card.grid(row=row, column=col, sticky="ew", padx=8, pady=7)
            icon = tk.Canvas(card, width=70, height=70, bg=PANEL2, highlightthickness=0, cursor="hand2")
            icon.pack(side="left", padx=10, pady=10)
            self._draw_tool_avatar(icon, kind, index)
            body = tk.Frame(card, bg=PANEL2)
            body.pack(side="left", fill="both", expand=True, padx=(0, 10), pady=10)
            tk.Label(body, text=title, bg=PANEL2, fg=TEXT, font=("Segoe UI", 10, "bold"),
                     anchor="w").pack(fill="x")
            tk.Label(body, text=desc, bg=PANEL2, fg=MUTED, font=("Segoe UI", 8),
                     wraplength=310, justify="left", anchor="w").pack(fill="x")
            state_label = tk.Label(body, text=("● АКТИВЕН" if enabled_var.get() else "● ВЫКЛЮЧЕН"), bg=PANEL2, fg=GREEN if enabled_var.get() else RED, font=("Segoe UI", 8, "bold"), cursor="hand2")
            state_label.pack(anchor="w", pady=(5, 0))
            state_label.bind("<Button-1>", lambda e, v=enabled_var, l=state_label: (v.set(not v.get()), l.config(text=("● АКТИВЕН" if v.get() else "● ВЫКЛЮЧЕН"), fg=GREEN if v.get() else RED)))
            def open_card(_event=None, n=name, t=title, d=desc, v=enabled_var):
                self._open_module_details(n, t, d, v.get())
            def bind_card(widget):
                widget.bind("<Button-1>", open_card)
                for child in widget.winfo_children():
                    bind_card(child)
            bind_card(card)
            state_label.bind("<Button-1>", lambda e, v=enabled_var, l=state_label: (v.set(not v.get()), l.config(text=("● АКТИВЕН" if v.get() else "● ВЫКЛЮЧЕН"), fg=GREEN if v.get() else RED)))

        def save_modules():
            new_disabled = [name for name, var in switches.items() if not var.get()]
            self.settings["disabled_tools"] = new_disabled
            os.environ["JARVIS_DISABLED_TOOLS"] = json.dumps(new_disabled, ensure_ascii=False)
            self._save_settings()
            win.destroy()
            self._reload_agent()

        bottom = tk.Frame(win, bg=BG)
        bottom.pack(fill="x", padx=20, pady=(0, 16))
        ttk.Button(bottom, text="Включить ВСЕ", command=lambda: [v.set(True) for v in switches.values()]).pack(side="left")
        ttk.Button(bottom, text="Выключить ВСЕ", command=lambda: [v.set(False) for v in switches.values()]).pack(side="left", padx=8)
        ttk.Button(bottom, text="СОХРАНИТЬ И ПЕРЕЗАПУСТИТЬ ЯДРО", style="Accent.TButton",
                   command=save_modules).pack(side="right")
        self.tool_status_label.config(text=f"Активно сейчас: {len(self.tool_names)} / {len(TOOLS)}")

    def show_settings(self):
        win = tk.Toplevel(self)
        win.title("JARVIS — Центр управления")
        win.configure(bg=PANEL)
        win.geometry("900x780")
        win.minsize(820, 700)
        win.transient(self)
        win.grab_set()
        tk.Label(win, text="ЦЕНТР УПРАВЛЕНИЯ JARVIS", bg=PANEL, fg=CYAN,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=24, pady=(22, 4))
        tk.Label(win, text="Один OpenRouter API-ключ для всех моделей. Меняйте модель — ключ остаётся один.",
                 bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=24, pady=(0, 16))

        body = tk.Frame(win, bg=PANEL)
        body.pack(fill="both", expand=True, padx=20)
        canvas = tk.Canvas(body, bg=PANEL, highlightthickness=0)
        scroll = ttk.Scrollbar(body, orient="vertical", command=canvas.yview)
        inner = tk.Frame(canvas, bg=PANEL)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        profiles = self.settings.get("agents", {})
        if not isinstance(profiles, dict):
            profiles = {}
        active = int(self.settings.get("active_agent", 0) or 0)
        names = ("FAST / Обычные", "REASONING / Рассуждения", "CODING / Код")
        defaults = (
            ("openai-compatible", DEFAULT_URL, "openrouter/free"),
            ("openai-compatible", DEFAULT_URL, "deepseek/deepseek-chat:free"),
            ("openai-compatible", DEFAULT_URL, "z-ai/glm-5.2:free"),
        )
        shared_key_row = tk.Frame(inner, bg="#091b29", highlightbackground=CYAN, highlightthickness=1)
        shared_key_row.pack(fill="x", pady=(0, 10))
        tk.Label(shared_key_row, text="OPENROUTER API-КЛЮЧ", bg="#091b29", fg=CYAN, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        shared_key = tk.Entry(shared_key_row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", show="•", exportselection=False)
        shared_key.insert(0, str(self.settings.get("openrouter_api_key") or profiles.get("0", {}).get("api_key", "") or os.environ.get("OPENROUTER_API_KEY", "")))
        shared_key.pack(fill="x", padx=14, pady=(0, 12), ipady=7)

        additional_row = tk.Frame(inner, bg="#091b29", highlightbackground=LINE, highlightthickness=1)
        additional_row.pack(fill="x", pady=(2, 10))
        tk.Label(additional_row, text="4. ADDITIONAL — резерв / второе мнение", bg="#091b29", fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 4))
        additional_model = tk.Entry(additional_row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat")
        additional_model.insert(0, str(self.settings.get("additional_model", "openrouter/free")))
        additional_model.pack(fill="x", padx=14, pady=(0, 12), ipady=6)

        consultant_frame = tk.Frame(inner, bg="#091b29", highlightbackground=LINE, highlightthickness=1)
        consultant_frame.pack(fill="x", pady=(2, 10))
        tk.Label(consultant_frame, text="НЕЗАВИСИМЫЕ КОНСУЛЬТАНТЫ", bg="#091b29", fg=CYAN,
                 font=("Segoe UI", 11, "bold")).pack(anchor="w", padx=14, pady=(10, 3))
        tk.Label(consultant_frame,
                 text="Если указать собственные ключи, DeepSeek и GLM работают напрямую, а не через OpenRouter.",
                 bg="#091b29", fg=MUTED, font=("Segoe UI", 8), wraplength=760, justify="left").pack(anchor="w", padx=14, pady=(0, 7))
        consultant_fields = {}
        consultant_defaults = (
            ("DeepSeek URL", "deepseek_url", self.settings.get("deepseek_url", ""), False),
            ("DeepSeek API-ключ", "deepseek_key", self.settings.get("deepseek_key", ""), True),
            ("DeepSeek модель", "deepseek_model", self.settings.get("deepseek_model", "deepseek/deepseek-chat:free"), False),
            ("GLM URL", "glm_url", self.settings.get("glm_url", ""), False),
            ("GLM API-ключ", "glm_key", self.settings.get("glm_key", ""), True),
            ("GLM модель", "glm_model", self.settings.get("glm_model", "z-ai/glm-5.2:free"), False),
        )
        for label, key, default, secret in consultant_defaults:
            row = tk.Frame(consultant_frame, bg="#091b29")
            row.pack(fill="x", padx=14, pady=3)
            tk.Label(row, text=label, width=20, anchor="w", bg="#091b29", fg=MUTED).pack(side="left")
            e = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", show="•" if secret else "", exportselection=False)
            e.insert(0, str(default))
            e.pack(side="left", fill="x", expand=True, ipady=6)
            consultant_fields[key] = e

        entries = []
        for i, title in enumerate(names):
            dprov, durl, dmodel = defaults[i]
            p = profiles.get(str(i), {})
            if not isinstance(p, dict):
                p = {}
            card = tk.Frame(inner, bg="#091b29", highlightbackground=CYAN if i == active else LINE, highlightthickness=1)
            card.pack(fill="x", pady=7)
            head = tk.Frame(card, bg="#091b29")
            head.pack(fill="x", padx=14, pady=(12, 4))
            tk.Label(head, text=f"{i+1}. {title}", bg="#091b29",
                     fg=CYAN if i == active else TEXT, font=("Segoe UI", 12, "bold")).pack(side="left")
            tk.Button(head, text="СДЕЛАТЬ АКТИВНЫМ", command=lambda idx=i: self._select_agent(idx, win),
                      bg="#0e667a", fg=TEXT, relief="flat", padx=10, pady=5).pack(side="right")
            fields = {}
            for label, key, default, secret in (
                ("Провайдер", "provider", p.get("provider", dprov), False),
                ("API URL", "url", p.get("url", durl), False),
                ("Модель", "model", p.get("model", dmodel), False),
            ):
                row = tk.Frame(card, bg="#091b29")
                row.pack(fill="x", padx=14, pady=4)
                tk.Label(row, text=label, width=13, anchor="w", bg="#091b29", fg=MUTED).pack(side="left")
                e = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat",
                             show="•" if secret else "", exportselection=False)
                e.insert(0, str(default))
                e.pack(side="left", fill="x", expand=True, ipady=6)
                fields[key] = e
            entries.append(fields)

        voice_frame = tk.Frame(inner, bg="#091b29", highlightbackground=CYAN, highlightthickness=1)
        voice_frame.pack(fill="x", pady=10)
        tk.Label(voice_frame, text="ГОЛОС JARVIS / ELEVENLABS + PIPER", bg="#091b29", fg=CYAN,
                 font=("Segoe UI", 12, "bold")).pack(anchor="w", padx=14, pady=(12, 6))
        voice_fields = {}
        for label, key, default, secret in (
            ("Движок TTS", "tts_engine", self.settings.get("tts_engine", "auto"), False),
            ("Локальный голос", "tts_voice", self.settings.get("tts_voice", "Dmitri Medium"), False),
            ("ElevenLabs API-ключ", "elevenlabs_api_key", self.settings.get("elevenlabs_api_key", ""), True),
            ("ElevenLabs Voice ID", "elevenlabs_voice_id", self.settings.get("elevenlabs_voice_id", "srULqtwUV9XZPg1ZCO5w"), False),
            ("ElevenLabs модель", "elevenlabs_model", self.settings.get("elevenlabs_model", "eleven_flash_v2_5"), False),
        ):
            row = tk.Frame(voice_frame, bg="#091b29")
            row.pack(fill="x", padx=14, pady=4)
            tk.Label(row, text=label, width=20, anchor="w", bg="#091b29", fg=MUTED).pack(side="left")
            e = tk.Entry(row, bg=PANEL2, fg=TEXT, insertbackground=CYAN, relief="flat", show="•" if secret else "")
            e.insert(0, str(default))
            e.pack(side="left", fill="x", expand=True, ipady=6)
            voice_fields[key] = e

        voice_var = tk.BooleanVar(value=self.settings.get("voice_enabled", True))
        tts_var = tk.BooleanVar(value=self.settings.get("tts_enabled", True))
        ttk.Checkbutton(inner, text="Голосовое прослушивание при старте", variable=voice_var).pack(anchor="w", padx=14, pady=6)
        ttk.Checkbutton(inner, text="Озвучивать ответы через TTS", variable=tts_var).pack(anchor="w", padx=14, pady=6)

        def save():
            new_profiles = {}
            for i, fields in enumerate(entries):
                new_profiles[str(i)] = {k: e.get().strip() for k, e in fields.items()}
                new_profiles[str(i)]["api_key"] = shared_key.get().strip()
                new_profiles[str(i)]["name"] = names[i]
            self.settings["agents"] = new_profiles
            self.settings["openrouter_api_key"] = shared_key.get().strip()
            self.settings["additional_model"] = additional_model.get().strip() or "openrouter/free"
            for k, e in consultant_fields.items():
                self.settings[k] = e.get().strip()
            self.settings["active_agent"] = active
            self.settings["voice_enabled"] = bool(voice_var.get())
            self.settings["tts_enabled"] = bool(tts_var.get())
            for k, e in voice_fields.items():
                self.settings[k] = e.get().strip()
            if self.settings.get("tts_engine", "auto").strip().lower() not in {"auto", "elevenlabs", "piper", "off"}:
                self.settings["tts_engine"] = "auto"
            self._apply_saved_settings()
            self._save_settings()
            win.destroy()
            self._reload_agent()

        ttk.Button(win, text="СОХРАНИТЬ И ПЕРЕЗАПУСТИТЬ", style="Accent.TButton", command=save).pack(anchor="e", padx=24, pady=18)

    def _select_agent(self, idx, parent=None):
        self.settings["active_agent"] = idx
        self._apply_saved_settings()
        self._save_settings()
        self._reload_agent()
        if parent and parent.winfo_exists():
            parent.destroy()

    def _reload_agent(self):
        self.agent = None
        self.status.config(text="● RESTARTING", fg=YELLOW)
        self._start_agent()

    def _close(self):
        self._voice_loop_running = False
        tts.stop()
        if self._orb_after:
            self.after_cancel(self._orb_after)
        self.destroy()


if __name__ == "__main__":
    JarvisDesktop().mainloop()