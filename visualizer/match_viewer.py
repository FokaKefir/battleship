"""Interactive Tkinter visualization for Battleship matches."""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from typing import Dict, List, Optional, Tuple
from urllib.parse import quote

import httpx
import tkinter as tk
from tkinter import ttk


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize Battleship matches via the admin insight API.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="API base URL.")
    parser.add_argument("--match-id", default=None, help="Optional match identifier to pre-select.")
    parser.add_argument(
        "--lobby-key",
        default=None,
        help="Optional lobby key to pre-select when opening the UI.",
    )
    parser.add_argument(
        "--api-key",
        default=None,
        help="Administrative API key (defaults to environment BATTLESHIP_ADMIN_TOKEN or 'admin-secret').",
    )
    parser.add_argument(
        "--interval",
        type=float,
        default=1.0,
        help="Initial polling interval in seconds (modifiable in the UI).",
    )
    parser.add_argument(
        "--game-id",
        default=None,
        help="Optional specific game identifier to replay instead of following the live match.",
    )
    args = parser.parse_args()
    if args.game_id and not args.match_id:
        parser.error("--game-id requires --match-id.")
    return args


class MatchVisualizer:
    """Tkinter-based visualization client for administrative insights."""

    CELL_PADDING = 4

    def __init__(
        self,
        base_url: str,
        match_id: Optional[str],
        lobby_key: Optional[str],
        api_key: Optional[str],
        interval: float,
        game_id: Optional[str],
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.match_id: Optional[str] = match_id
        self.api_key = api_key or os.getenv("BATTLESHIP_ADMIN_TOKEN", "admin-secret")
        self.root = tk.Tk()
        self.root.title("Battleship Match Visualizer")
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.delay_var = tk.DoubleVar(master=self.root, value=max(interval, 0.2))
        self.show_boards_var = tk.BooleanVar(master=self.root, value=True)
        self.selected_game_id: Optional[str] = game_id
        self.game_options: Dict[str, Optional[str]] = {}
        initial_selector_label = "Live view" if game_id is None else "Loading…"
        self.game_selector_var = tk.StringVar(master=self.root, value=initial_selector_label)
        self.game_selector: Optional[ttk.Combobox] = None
        self.match_options: Dict[str, Optional[str]] = {"Select a match": None}
        initial_match_label = f"Match {match_id[:8]}" if match_id else "Select a match"
        if match_id:
            self.match_options[initial_match_label] = match_id
        self.match_selector_var = tk.StringVar(master=self.root, value=initial_match_label)
        self.match_selector: Optional[ttk.Combobox] = None
        self.match_summaries: Dict[str, dict] = {}
        initial_lobby_label = lobby_key if lobby_key else "Select a lobby"
        self.lobby_selector_var = tk.StringVar(master=self.root, value=initial_lobby_label)
        self.lobby_selector: Optional[ttk.Combobox] = None
        self.lobby_options: Dict[str, Optional[str]] = {"Select a lobby": None}
        if lobby_key:
            self.lobby_options[initial_lobby_label] = lobby_key
        self.lobby_details: Dict[str, dict] = {}
        self.selected_lobby_key: Optional[str] = lobby_key
        self.create_lobby_var = tk.StringVar(master=self.root, value="")
        self.lobby_info_var = tk.StringVar(value="Select a lobby to view status.")
        self.delete_lobby_button: Optional[ttk.Button] = None
        self.playing_var = tk.BooleanVar(master=self.root, value=False)
        self.replay_step_var = tk.IntVar(master=self.root, value=0)
        self.step_label_var = tk.StringVar(master=self.root, value="Shot 0/0")
        self.replay_scale: Optional[tk.Scale] = None
        self.play_button: Optional[ttk.Button] = None
        self.step_forward_button: Optional[ttk.Button] = None
        self.step_back_button: Optional[ttk.Button] = None
        self._suppress_scale_callback = False

        self.client = httpx.Client(
            base_url=self.base_url,
            headers={"x-api-key": self.api_key},
            timeout=httpx.Timeout(10.0, connect=5.0),
        )
        self.running = True
        self.fetching = False
        self.last_update = 0.0
        self.current_data: Optional[dict] = None
        self.current_history: List[dict] = []
        self.current_step = 0
        self.max_step = 0
        self.last_step_tick = time.time()

        self.progress_bars: Dict[str, ttk.Progressbar] = {}
        self.progress_labels: Dict[str, ttk.Label] = {}
        self.board_widgets: Dict[str, dict] = {}
        self.game_info_var = tk.StringVar(value="Awaiting data…")
        initial_status = "" if (match_id or lobby_key) else "Select a lobby or match to begin."
        self.status_var = tk.StringVar(value=initial_status)
        self.delay_label_var = tk.StringVar()

        self._build_layout()
        self.on_delay_change(self.delay_var.get())

    # ------------------------------------------------------------------ UI setup
    def _build_layout(self) -> None:
        control_frame = ttk.Frame(self.root)
        control_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        ttk.Label(control_frame, text="Update interval (seconds)").pack(side=tk.LEFT)
        scale = ttk.Scale(
            control_frame,
            from_=0.2,
            to=5.0,
            variable=self.delay_var,
            command=lambda _: self.on_delay_change(self.delay_var.get()),
        )
        scale.pack(side=tk.LEFT, padx=10)

        ttk.Label(control_frame, textvariable=self.delay_label_var).pack(side=tk.LEFT)

        ttk.Checkbutton(
            control_frame,
            text="Reveal boards",
            variable=self.show_boards_var,
            command=self._redraw_boards,
        ).pack(side=tk.RIGHT)

        lobby_frame = ttk.Frame(self.root)
        lobby_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(lobby_frame, text="Lobby").pack(side=tk.LEFT)
        self.lobby_selector = ttk.Combobox(
            lobby_frame,
            textvariable=self.lobby_selector_var,
            state="readonly",
            values=[self.lobby_selector_var.get()],
            width=38,
        )
        self.lobby_selector.pack(side=tk.LEFT, padx=6)
        self.lobby_selector.bind("<<ComboboxSelected>>", self._on_lobby_selected)
        self.delete_lobby_button = ttk.Button(
            lobby_frame,
            text="Delete",
            command=self._delete_lobby,
            state="normal" if self.selected_lobby_key else "disabled",
        )
        self.delete_lobby_button.pack(side=tk.LEFT, padx=4)

        create_frame = ttk.Frame(self.root)
        create_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(create_frame, text="New lobby").pack(side=tk.LEFT)
        ttk.Entry(create_frame, textvariable=self.create_lobby_var, width=28).pack(side=tk.LEFT, padx=6)
        ttk.Button(create_frame, text="Create", command=self._create_lobby).pack(side=tk.LEFT)

        lobby_info_frame = ttk.LabelFrame(self.root, text="Lobby Status")
        lobby_info_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(lobby_info_frame, textvariable=self.lobby_info_var, justify=tk.LEFT).pack(anchor="w", padx=4, pady=2)

        match_frame = ttk.Frame(self.root)
        match_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(match_frame, text="Match").pack(side=tk.LEFT)
        self.match_selector = ttk.Combobox(
            match_frame,
            textvariable=self.match_selector_var,
            state="readonly",
            values=[self.match_selector_var.get()],
            width=42,
        )
        self.match_selector.pack(side=tk.LEFT, padx=6)
        self.match_selector.bind("<<ComboboxSelected>>", self._on_match_selected)

        game_frame = ttk.Frame(self.root)
        game_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(game_frame, text="Game view").pack(side=tk.LEFT)
        self.game_selector = ttk.Combobox(
            game_frame,
            textvariable=self.game_selector_var,
            state="disabled",
            values=[self.game_selector_var.get()],
            width=34,
        )
        self.game_selector.pack(side=tk.LEFT, padx=6)
        self.game_selector.bind("<<ComboboxSelected>>", self._on_game_selected)

        replay_frame = ttk.Frame(self.root)
        replay_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))
        self.play_button = ttk.Button(replay_frame, text="Play", command=self._toggle_play, state="disabled")
        self.play_button.pack(side=tk.LEFT)
        self.step_back_button = ttk.Button(replay_frame, text="◀", width=3, command=self._step_back, state="disabled")
        self.step_back_button.pack(side=tk.LEFT, padx=4)
        self.step_forward_button = ttk.Button(replay_frame, text="▶", width=3, command=self._step_forward, state="disabled")
        self.step_forward_button.pack(side=tk.LEFT)
        ttk.Label(replay_frame, textvariable=self.step_label_var).pack(side=tk.LEFT, padx=6)
        self.replay_scale = tk.Scale(
            replay_frame,
            from_=0,
            to=0,
            orient=tk.HORIZONTAL,
            variable=self.replay_step_var,
            command=lambda _: self._on_replay_scale_change(),
            length=240,
            resolution=1,
            state="disabled",
        )
        self.replay_scale.pack(side=tk.LEFT, padx=8)

        self.progress_frame = ttk.LabelFrame(self.root, text="Match Progress")
        self.progress_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=5)

        game_info_frame = ttk.Frame(self.root)
        game_info_frame.pack(side=tk.TOP, fill=tk.X, padx=10, pady=(0, 5))
        ttk.Label(game_info_frame, textvariable=self.game_info_var, font=("TkDefaultFont", 11, "bold")).pack(anchor="w")

        self.board_container = ttk.Frame(self.root)
        self.board_container.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=5)

        history_frame = ttk.LabelFrame(self.root, text="Move History")
        history_frame.pack(side=tk.BOTTOM, fill=tk.BOTH, expand=True, padx=10, pady=5)

        self.history_text = tk.Text(history_frame, height=12, state="disabled")
        self.history_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        history_scroll = ttk.Scrollbar(history_frame, command=self.history_text.yview)
        history_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.history_text.configure(yscrollcommand=history_scroll.set)

        status_bar = ttk.Label(self.root, textvariable=self.status_var, anchor="w")
        status_bar.pack(side=tk.BOTTOM, fill=tk.X)

    # --------------------------------------------------------------------- Events
    def on_delay_change(self, value: float) -> None:
        safe_value = max(float(value), 0.2)
        self.delay_var.set(safe_value)
        self.delay_label_var.set(f"{safe_value:.1f}s")

    def on_close(self) -> None:
        self.running = False
        try:
            self.client.close()
        finally:
            self.root.destroy()

    def _reset_view_state(self) -> None:
        self.current_data = None
        self.current_history = []
        self.current_step = 0
        self.max_step = 0
        self.playing_var.set(False)
        self._set_replay_step(0)
        if self.replay_scale is not None:
            self.replay_scale.configure(to=0, state="disabled")
        self._sync_replay_controls()
        self.game_options = {"Live view": None}
        if self.game_selector is not None:
            self.game_selector["values"] = ["Live view"]
            self.game_selector.configure(state="disabled")
        self._clear_boards()
        self._update_history([])
        self.game_info_var.set("Awaiting data…")

    def _clear_match_display(self) -> None:
        self.current_data = None
        self.current_history = []
        self.current_step = 0
        self.max_step = 0
        self.playing_var.set(False)
        self._set_replay_step(0)
        self._sync_replay_controls()
        self._clear_boards()
        self._update_history([])
        self.game_info_var.set("No match selected.")
        for bar in self.progress_bars.values():
            bar["value"] = 0.0
        for label in self.progress_labels.values():
            label.configure(text="")

    def _set_active_match(self, match_id: Optional[str], label: Optional[str] = None) -> None:
        if match_id is None:
            self.match_id = None
            self.selected_game_id = None
            self.match_selector_var.set("Select a match")
            self.game_selector_var.set("Live view")
            if self.game_selector is not None:
                self.game_selector.configure(state="disabled")
            self.status_var.set("Select a lobby or match to begin.")
            self._clear_match_display()
            return

        self.match_id = match_id
        self.selected_game_id = None
        self.game_selector_var.set("Live view")
        if self.game_selector is not None:
            self.game_selector.configure(state="disabled")

        if label is None:
            label = next((lbl for lbl, mid in self.match_options.items() if mid == match_id), f"Match {match_id[:8]}")
        if label not in self.match_options:
            updated = dict(self.match_options)
            updated[label] = match_id
            self.match_options = updated
            if self.match_selector is not None:
                self.match_selector["values"] = list(updated.keys())
        self.match_selector_var.set(label)

        self.playing_var.set(False)
        self.last_update = 0.0
        self._reset_view_state()

        summary = self.match_summaries.get(match_id)
        if summary:
            p1 = summary["player1"]["player_name"]
            p2 = summary["player2"]["player_name"]
            score = f"{summary['player1_points']}–{summary['player2_points']}"
            state = "LIVE" if summary.get("match_active", False) else "FINAL"
            self.status_var.set(f"Viewing {p1} vs {p2} ({score}) — {state}. Awaiting update…")
        else:
            self.status_var.set("Match selected — awaiting update…")

    def _update_lobby_display(self, lobby: Optional[dict]) -> None:
        if not lobby:
            self.lobby_info_var.set("Select a lobby to view status.")
            return

        status = lobby.get("status", "waiting").capitalize()
        lines = [f"Lobby: {lobby['lobby_key']} — {status}"]
        for player in sorted(lobby.get("players", []), key=lambda item: item.get("slot", 0)):
            slot = player.get("slot")
            if player.get("joined"):
                name = player.get("player_name") or "Unknown"
                tagline = player.get("tagline") or ""
                tagline_part = f" — {tagline}" if tagline else ""
                lines.append(f"Slot {slot}: {name}{tagline_part}")
            else:
                lines.append(f"Slot {slot}: awaiting player")
        if lobby.get("match_id"):
            lines.append(f"Match ID: {lobby['match_id'][:8]}")
        self.lobby_info_var.set("\n".join(lines))

    def _apply_match_list(self, payload: dict) -> None:
        matches = payload.get("matches", [])
        self.match_summaries = {entry["match_id"]: entry for entry in matches}
        options: Dict[str, Optional[str]] = {"Select a match": None}
        for entry in matches:
            match_id = entry["match_id"]
            p1 = entry["player1"]["player_name"]
            p2 = entry["player2"]["player_name"]
            status = "LIVE" if entry.get("match_active", False) else "FINAL"
            label = f"{p1} vs {p2} [{status}] · {match_id[:8]}"
            options[label] = match_id
        self.match_options = options
        if self.match_selector is not None:
            self.match_selector["values"] = list(options.keys())
        desired_label = None
        if self.match_id and self.match_id in self.match_summaries:
            desired_label = next((lbl for lbl, mid in options.items() if mid == self.match_id), None)
        if desired_label is None:
            desired_label = "Select a match"
            if self.match_id and self.match_id not in self.match_summaries:
                self.match_id = None
        if self.match_selector_var.get() != desired_label:
            self.match_selector_var.set(desired_label)

    def _apply_lobby_list(self, payload: dict) -> None:
        lobbies = payload.get("lobbies", [])
        self.lobby_details = {entry["lobby_key"]: entry for entry in lobbies}
        options: Dict[str, Optional[str]] = {"Select a lobby": None}
        for entry in lobbies:
            lobby_key = entry["lobby_key"]
            joined = sum(1 for player in entry.get("players", []) if player.get("joined"))
            status = entry.get("status", "waiting").upper()
            label = f"{lobby_key} [{status}] {joined}/2"
            options[label] = lobby_key
        self.lobby_options = options
        if self.lobby_selector is not None:
            self.lobby_selector["values"] = list(options.keys())
        desired_label = None
        if self.selected_lobby_key and self.selected_lobby_key in self.lobby_details:
            desired_label = next((lbl for lbl, key in options.items() if key == self.selected_lobby_key), None)
        if desired_label is None:
            desired_label = "Select a lobby"
            if self.selected_lobby_key and self.selected_lobby_key not in self.lobby_details:
                self.selected_lobby_key = None
        if self.lobby_selector_var.get() != desired_label:
            self.lobby_selector_var.set(desired_label)

        lobby = self.lobby_details.get(self.selected_lobby_key) if self.selected_lobby_key else None
        self._update_lobby_display(lobby)
        if self.delete_lobby_button is not None:
            state = "normal" if self.selected_lobby_key else "disabled"
            self.delete_lobby_button.configure(state=state)

        if lobby and lobby.get("match_id"):
            match_id = lobby["match_id"]
            label = next((lbl for lbl, mid in self.match_options.items() if mid == match_id), None)
            if self.match_id != match_id:
                self._set_active_match(match_id, label)
        elif self.selected_lobby_key and not lobby:
            self._set_active_match(None)

    def _create_lobby(self) -> None:
        key = self.create_lobby_var.get().strip()
        if not key:
            self.status_var.set("Enter a lobby key before creating.")
            return

        def worker() -> None:
            try:
                response = self.client.post("/api/v1/lobby/create", json={"lobby_key": key})
                response.raise_for_status()
                self.root.after_idle(lambda: self.status_var.set(f"Lobby '{key}' created."))
            except httpx.HTTPStatusError as exc:
                msg = f"Create lobby failed ({exc.response.status_code}): {exc.response.text[:200]}"
                self.root.after_idle(lambda m=msg: self.status_var.set(m))
            except httpx.RequestError as exc:
                self.root.after_idle(lambda m=f"Create lobby connection error: {exc}": self.status_var.set(m))

        threading.Thread(target=worker, daemon=True).start()
        self.selected_lobby_key = None
        self.lobby_selector_var.set("Select a lobby")
        if self.delete_lobby_button is not None:
            self.delete_lobby_button.configure(state="disabled")
        self._update_lobby_display(None)
        self.create_lobby_var.set("")

    def _delete_lobby(self) -> None:
        if not self.selected_lobby_key:
            self.status_var.set("Select a lobby to delete.")
            return
        key = self.selected_lobby_key

        def worker() -> None:
            try:
                path = f"/api/v1/lobby/{quote(key, safe='')}"
                response = self.client.delete(path)
                if response.status_code not in {200, 204}:
                    try:
                        detail = response.json()
                    except json.JSONDecodeError:
                        detail = response.text
                    msg = f"Delete lobby failed ({response.status_code}): {detail}"
                    self.root.after_idle(lambda m=msg: self.status_var.set(m))
                    return
                self.root.after_idle(lambda: self._handle_lobby_removed(key))
            except httpx.RequestError as exc:
                self.root.after_idle(lambda m=f"Delete lobby connection error: {exc}": self.status_var.set(m))

        threading.Thread(target=worker, daemon=True).start()

    def _on_lobby_selected(self, _event: object | None) -> None:
        label = self.lobby_selector_var.get()
        lobby_key = self.lobby_options.get(label)
        if lobby_key == self.selected_lobby_key:
            return
        self.selected_lobby_key = lobby_key
        if self.delete_lobby_button is not None:
            self.delete_lobby_button.configure(state="normal" if lobby_key else "disabled")
        lobby = self.lobby_details.get(lobby_key) if lobby_key else None
        self._update_lobby_display(lobby)

        if not lobby_key:
            if not self.match_id:
                self.status_var.set("Select a lobby or match to begin.")
            return

        if not lobby:
            self.status_var.set(f"Lobby '{lobby_key}' selected.")
            self._set_active_match(None)
            return

        status = lobby.get("status", "waiting").capitalize()
        self.status_var.set(f"Lobby '{lobby_key}' — {status}.")
        match_id = lobby.get("match_id")
        if match_id:
            label = next((lbl for lbl, mid in self.match_options.items() if mid == match_id), None)
            self._set_active_match(match_id, label)
        else:
            self._set_active_match(None)

    def _handle_lobby_removed(self, lobby_key: str) -> None:
        self.status_var.set(f"Lobby '{lobby_key}' deleted.")
        if self.selected_lobby_key == lobby_key:
            self.selected_lobby_key = None
            if self.lobby_selector is not None:
                self.lobby_selector_var.set("Select a lobby")
            if self.delete_lobby_button is not None:
                self.delete_lobby_button.configure(state="disabled")
            self._update_lobby_display(None)
            self._set_active_match(None)

    def _on_match_selected(self, _event: object | None) -> None:
        label = self.match_selector_var.get()
        match_id = self.match_options.get(label)
        if match_id == self.match_id:
            return
        self.selected_lobby_key = None
        if self.lobby_selector is not None:
            self.lobby_selector_var.set("Select a lobby")
        if self.delete_lobby_button is not None:
            self.delete_lobby_button.configure(state="disabled")
        self._update_lobby_display(None)
        self._set_active_match(match_id, label if match_id else None)

    def _on_game_selected(self, _event: object) -> None:
        label = self.game_selector_var.get()
        selected = self.game_options.get(label)
        self.selected_game_id = selected
        self.last_update = 0.0  # force immediate refresh
        mode = "live" if selected is None else "replay"
        self.playing_var.set(False)
        self.current_step = 0
        self._set_replay_step(self.current_step)
        self._sync_replay_controls()
        self.status_var.set(f"Viewing {mode} data — awaiting update…")

    def _toggle_play(self) -> None:
        if not self.current_data or self.selected_game_id is None:
            return
        playing = not self.playing_var.get()
        self.playing_var.set(playing)
        if playing and self.current_step >= self.max_step:
            self.current_step = 0
            self._set_replay_step(self.current_step)
        self.last_step_tick = time.time()
        self._sync_replay_controls()

    def _step_forward(self) -> None:
        if not self.current_data or self.max_step == 0:
            return
        self.playing_var.set(False)
        self.current_step = min(self.current_step + 1, self.max_step)
        self._set_replay_step(self.current_step)
        self._sync_replay_controls()
        self._render_current_state()

    def _step_back(self) -> None:
        if not self.current_data:
            return
        self.playing_var.set(False)
        self.current_step = max(self.current_step - 1, 0)
        self._set_replay_step(self.current_step)
        self._sync_replay_controls()
        self._render_current_state()

    def _on_replay_scale_change(self) -> None:
        if self._suppress_scale_callback or not self.current_data:
            return
        self.playing_var.set(False)
        self.current_step = int(self.replay_step_var.get())
        self._sync_replay_controls()
        self._render_current_state()

    # ------------------------------------------------------------- Match helpers

    # ----------------------------------------------------------------- Polling UI
    def start(self) -> None:
        self.root.after(0, self.update_loop)
        self.root.mainloop()

    def update_loop(self) -> None:
        if not self.running:
            return

        now = time.time()
        if self.selected_game_id is not None and self.playing_var.get() and self.max_step > 0:
            if self.current_step < self.max_step and now - self.last_step_tick >= self.delay_var.get():
                self.current_step += 1
                self._set_replay_step(self.current_step)
                self.last_step_tick = now
                self._render_current_state()
            elif self.current_step >= self.max_step:
                self.playing_var.set(False)
                self._sync_replay_controls()

        if self.fetching:
            self.root.after(100, self.update_loop)
            return
        if now - self.last_update < self.delay_var.get():
            self.root.after(50, self.update_loop)
            return

        self.fetching = True
        threading.Thread(target=self._fetch_and_update, daemon=True).start()
        self.root.after(100, self.update_loop)

    def _fetch_and_update(self) -> None:
        target_match_id = self.match_id
        matches_payload: Optional[dict] = None
        lobbies_payload: Optional[dict] = None
        try:
            matches_resp = self.client.get("/api/v1/admin/matches")
            matches_resp.raise_for_status()
            matches_payload = matches_resp.json()
        except httpx.HTTPStatusError as exc:
            message = f"Match list error {exc.response.status_code}: {exc.response.text[:200]}"
            self.root.after_idle(lambda msg=message: self.status_var.set(msg))
        except httpx.RequestError as exc:
            message = f"Connection error: {exc}"
            self.root.after_idle(lambda msg=message: self.status_var.set(msg))

        try:
            lobbies_resp = self.client.get("/api/v1/lobby/list")
            lobbies_resp.raise_for_status()
            lobbies_payload = lobbies_resp.json()
        except httpx.HTTPStatusError as exc:
            message = f"Lobby list error {exc.response.status_code}: {exc.response.text[:200]}"
            self.root.after_idle(lambda msg=message: self.status_var.set(msg))
        except httpx.RequestError as exc:
            message = f"Connection error: {exc}"
            self.root.after_idle(lambda msg=message: self.status_var.set(msg))

        if matches_payload is not None:
            self.root.after_idle(lambda payload=matches_payload: self._apply_match_list(payload))
            # The selected match might change after applying the list; use the snapshot for this refresh.
            target_match_id = target_match_id or self.match_id

        if lobbies_payload is not None:
            self.root.after_idle(lambda payload=lobbies_payload: self._apply_lobby_list(payload))

        if not target_match_id:
            self.last_update = time.time()
            self.root.after_idle(self._clear_match_display)
            self.root.after_idle(self._mark_fetch_complete)
            return

        try:
            params = {}
            if self.selected_game_id:
                params["game_id"] = self.selected_game_id
            response = self.client.get(f"/api/v1/admin/match/{target_match_id}/insight", params=params)
            response.raise_for_status()
            data = response.json()
            self.last_update = time.time()
            self.root.after_idle(lambda: self._apply_data(data))
        except httpx.HTTPStatusError as exc:
            message = f"API error {exc.response.status_code}: {exc.response.text[:200]}"
            self.root.after_idle(lambda msg=message: self.status_var.set(msg))
        except httpx.RequestError as exc:
            message = f"Connection error: {exc}"
            self.root.after_idle(lambda msg=message: self.status_var.set(msg))
        finally:
            self.root.after_idle(self._mark_fetch_complete)

    def _mark_fetch_complete(self) -> None:
        self.fetching = False

    # ------------------------------------------------------------------ UI update
    def _update_game_options(self, data: dict, player_lookup: Dict[str, str]) -> None:
        history = sorted(data.get("game_history", []), key=lambda entry: entry.get("game_number", 0))
        option_items: List[Tuple[str, Optional[str]]] = [("Live view", None)]

        for entry in history:
            label = f"Game {entry.get('game_number', '?')}"
            winner_id = entry.get("winner_id")
            shots = entry.get("shots", 0)
            if winner_id:
                winner_name = player_lookup.get(winner_id, winner_id[:8])
                label += f" — Winner {winner_name}"
            else:
                label += " — Pending"
            label += f" ({shots} shots)"
            option_items.append((label, entry["game_id"]))

        current_game = data.get("current_game")
        if current_game:
            current_id = current_game["game_id"]
            if all(item[1] != current_id for item in option_items):
                status = "completed" if not current_game.get("game_active", False) else "in progress"
                label = f"Game {current_game['game_number']} — {status}"
                option_items.append((label, current_id))

        option_map = {label: game_id for label, game_id in option_items}
        option_labels = list(option_map.keys())

        if option_map != self.game_options:
            self.game_options = option_map
            if self.game_selector is not None:
                self.game_selector["values"] = option_labels

        desired_label: Optional[str]
        if self.selected_game_id is None:
            desired_label = "Live view"
        else:
            desired_label = next((label for label, gid in option_items if gid == self.selected_game_id), None)
            if desired_label is None:
                desired_label = "Live view"
                self.selected_game_id = None

        if self.game_selector_var.get() != desired_label and desired_label is not None:
            self.game_selector_var.set(desired_label)

        if self.game_selector is not None:
            self.game_selector.configure(state="readonly")

    def _apply_data(self, data: dict) -> None:
        self.current_data = data

        progress = data.get("progress", {})
        players = progress.get("players", [])
        target = progress.get("target_points", 0)
        self._ensure_progress_widgets(players)
        player_lookup = {entry["player"]["player_id"]: entry["player"]["player_name"] for entry in players}
        self._update_game_options(data, player_lookup)

        for entry in players:
            player = entry["player"]
            player_id = player["player_id"]
            bar = self.progress_bars[player_id]
            label = self.progress_labels[player_id]
            bar["value"] = min(entry.get("progress", 0.0), 1.0)
            label.configure(
                text=f"{player['player_name']}: {entry['points']} / {target} "
                f"(remaining: {entry['points_remaining']})"
            )

        match_active = data.get("match_active", True)
        view_mode = "Live" if self.selected_game_id is None else "Replay"
        self.status_var.set(
            f"Last update: {time.strftime('%H:%M:%S')} — Match {'active' if match_active else 'complete'} — {view_mode} mode"
        )

        game_data = data.get("current_game")
        self.current_history = game_data.get("shot_history", []) if game_data else []
        self.max_step = len(self.current_history)
        if self.selected_game_id is None:
            self.current_step = self.max_step
        else:
            self.current_step = min(self.current_step, self.max_step)
        self._set_replay_step(self.current_step)
        if self.replay_scale is not None:
            self.replay_scale.configure(to=self.max_step)
        self._sync_replay_controls()
        self.last_step_tick = time.time()

        if not game_data:
            if self.selected_game_id:
                self.game_info_var.set("Selected game unavailable or not found.")
            else:
                self.game_info_var.set("No active games. Waiting for the next game to begin.")
            self._clear_boards()
            self._update_history([])
            return

        self._ensure_board_widgets(game_data["boards"])
        self._render_current_state()

    def _sync_replay_controls(self) -> None:
        if self.play_button is None or self.step_forward_button is None or self.step_back_button is None:
            return

        if self.selected_game_id is None or self.max_step == 0:
            self.play_button.configure(text="Play", state="disabled")
            self.step_forward_button.configure(state="disabled")
            self.step_back_button.configure(state="disabled")
            if self.replay_scale is not None:
                self.replay_scale.configure(state="disabled")
            self.step_label_var.set(f"Shot {self.current_step}/{self.max_step}")
            return

        self.play_button.configure(text="Pause" if self.playing_var.get() else "Play", state="normal")
        self.step_forward_button.configure(state="normal")
        self.step_back_button.configure(state="normal")
        if self.replay_scale is not None:
            self.replay_scale.configure(state="normal")
        self.step_label_var.set(f"Shot {self.current_step}/{self.max_step}")

    def _set_replay_step(self, value: int) -> None:
        self._suppress_scale_callback = True
        try:
            self.replay_step_var.set(int(value))
        finally:
            self._suppress_scale_callback = False

    def _render_current_state(self) -> None:
        if not self.current_data:
            return
        game_data = self.current_data.get("current_game")
        if not game_data:
            return
        player_map = {entry["player"]["player_id"]: entry["player"]["player_name"] for entry in game_data["boards"]}
        current_turn = game_data.get("current_turn")
        if current_turn and current_turn in player_map:
            turn_label = player_map[current_turn]
        elif current_turn:
            turn_label = str(current_turn)
        else:
            turn_label = "-"
        status_label = "active" if game_data.get("game_active") else "completed"
        self.game_info_var.set(
            f"Game {game_data['game_number']} ({status_label}) — Current turn: {turn_label} — Shots: {self.current_step}/{self.max_step}"
        )
        self.step_label_var.set(f"Shot {self.current_step}/{self.max_step}")
        self._draw_boards(game_data, self.current_step)
        self._update_history(self.current_history[: self.current_step])
        self._sync_replay_controls()

    # ----------------------------------------------------------- Progress widgets
    def _ensure_progress_widgets(self, players: List[dict]) -> None:
        for widget_dict in (self.progress_bars, self.progress_labels):
            to_remove = [pid for pid in widget_dict if pid not in {p["player"]["player_id"] for p in players}]
            for pid in to_remove:
                widget_dict.pop(pid, None)

        for idx, entry in enumerate(players):
            player = entry["player"]
            player_id = player["player_id"]
            if player_id in self.progress_bars:
                continue
            row_frame = ttk.Frame(self.progress_frame)
            row_frame.grid(row=idx, column=0, sticky="ew", pady=2)
            row_frame.columnconfigure(1, weight=1)

            name_label = ttk.Label(row_frame, text=player["player_name"], width=18)
            name_label.grid(row=0, column=0, sticky="w")

            progress_bar = ttk.Progressbar(row_frame, maximum=1.0)
            progress_bar.grid(row=0, column=1, sticky="ew", padx=5)
            self.progress_bars[player_id] = progress_bar

            info_label = ttk.Label(row_frame, text="")
            info_label.grid(row=0, column=2, sticky="w", padx=5)
            self.progress_labels[player_id] = info_label

    # -------------------------------------------------------------- Board widgets
    def _clear_boards(self) -> None:
        for widget in self.board_container.winfo_children():
            widget.destroy()
        self.board_widgets.clear()

    def _ensure_board_widgets(self, boards: List[dict]) -> None:
        existing_ids = set(self.board_widgets)
        new_ids = {board["player"]["player_id"] for board in boards}

        # Remove stale widgets
        for player_id in existing_ids - new_ids:
            widget_info = self.board_widgets.pop(player_id)
            widget_info["frame"].destroy()

        for board in boards:
            player = board["player"]
            player_id = player["player_id"]
            if player_id in self.board_widgets:
                continue
            frame = ttk.LabelFrame(self.board_container, text=f"{player['player_name']} (Teleport used: "
                                                              f"{'Yes' if board['teleport_used'] else 'No'})")
            frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)

            canvas = tk.Canvas(frame, width=320, height=320, bg="white")
            canvas.pack(fill=tk.BOTH, expand=True)

            self.board_widgets[player_id] = {"frame": frame, "canvas": canvas}

    def _redraw_boards(self) -> None:
        if self.current_data and self.current_data.get("current_game"):
            self._draw_boards(self.current_data["current_game"], self.current_step)

    def _draw_boards(self, game_data: dict, shot_limit: int) -> None:
        boards = game_data["boards"]
        grid_rows, grid_cols = game_data["grid_size"]
        show_ships = self.show_boards_var.get()

        for board in boards:
            player_id = board["player"]["player_id"]
            widget_info = self.board_widgets.get(player_id)
            if not widget_info:
                continue
            frame: ttk.LabelFrame = widget_info["frame"]
            frame.configure(
                text=f"{board['player']['player_name']} (Teleport used: {'Yes' if board['teleport_used'] else 'No'})"
            )
            canvas: tk.Canvas = widget_info["canvas"]
            canvas.delete("all")

            width = canvas.winfo_width() or 320
            height = canvas.winfo_height() or 320
            cell_size = min((width - self.CELL_PADDING * 2) / grid_cols, (height - self.CELL_PADDING * 2) / grid_rows)
            cell_size = max(cell_size, 10)

            offset_x = (width - cell_size * grid_cols) / 2
            offset_y = (height - cell_size * grid_rows) / 2

            # Draw grid
            for row in range(grid_rows + 1):
                y = offset_y + row * cell_size
                canvas.create_line(offset_x, y, offset_x + grid_cols * cell_size, y, fill="#cccccc")
            for col in range(grid_cols + 1):
                x = offset_x + col * cell_size
                canvas.create_line(x, offset_y, x, offset_y + grid_rows * cell_size, fill="#cccccc")

            hits = set()
            misses = set()
            for shot in board["shots_received"]:
                if shot.get("turn", 0) <= shot_limit:
                    coord = shot["coordinate"]
                    key = (coord["row"], coord["col"])
                    if shot["result"] == "miss":
                        misses.add(key)
                    else:
                        hits.add(key)

            ship_records: List[Tuple[set[Tuple[int, int]], set[Tuple[int, int]], bool, List[set[Tuple[int, int]]]]] = []
            sunk_cells: set[Tuple[int, int]] = set()
            for ship in board["ships"]:
                coords = {(coord["row"], coord["col"]) for coord in ship["coordinates"]}
                hits_on_ship = {(cell["row"], cell["col"]) for cell in ship.get("hits", [])}
                sunk = bool(ship.get("sunk"))
                if sunk:
                    sunk_cells.update(coords)
                history_sets: List[set[Tuple[int, int]]] = []
                for entry in ship.get("previous_positions", []) or []:
                    prev_coords = {(cell["row"], cell["col"]) for cell in entry}
                    if prev_coords:
                        history_sets.append(prev_coords)
                ship_records.append((coords, hits_on_ship, sunk, history_sets))

            if show_ships:
                for coords, hits_on_ship, sunk, history_sets in ship_records:
                    for previous in history_sets:
                        for row, col in previous:
                            if (row, col) not in coords:
                                self._draw_cell(canvas, cell_size, offset_x, offset_y, row, col, fill="#BDBDBD")
                    base_color = "#9E9E9E" if sunk else "#4A90E2"
                    for row, col in coords:
                        self._draw_cell(canvas, cell_size, offset_x, offset_y, row, col, fill=base_color)
                    for row, col in hits_on_ship:
                        self._draw_cell(canvas, cell_size, offset_x, offset_y, row, col, fill="#D0021B")

            # Hits
            # Misses
            for row, col in misses:
                self._draw_miss(canvas, cell_size, offset_x, offset_y, row, col)

            if sunk_cells:
                for row, col in sunk_cells:
                    self._draw_sunk_marker(canvas, cell_size, offset_x, offset_y, row, col)

    def _draw_cell(
        self, canvas: tk.Canvas, cell_size: float, offset_x: float, offset_y: float, row: int, col: int, fill: str
    ) -> None:
        x0 = offset_x + col * cell_size + 1
        y0 = offset_y + row * cell_size + 1
        x1 = x0 + cell_size - 2
        y1 = y0 + cell_size - 2
        canvas.create_rectangle(x0, y0, x1, y1, fill=fill, outline="")

    def _draw_miss(self, canvas: tk.Canvas, cell_size: float, offset_x: float, offset_y: float, row: int, col: int):
        radius = cell_size * 0.2
        center_x = offset_x + col * cell_size + cell_size / 2
        center_y = offset_y + row * cell_size + cell_size / 2
        canvas.create_oval(
            center_x - radius,
            center_y - radius,
            center_x + radius,
            center_y + radius,
            outline="#333333",
        )

    def _draw_sunk_marker(
        self, canvas: tk.Canvas, cell_size: float, offset_x: float, offset_y: float, row: int, col: int
    ) -> None:
        margin = max(cell_size * 0.15, 2)
        x0 = offset_x + col * cell_size + margin
        y0 = offset_y + row * cell_size + margin
        x1 = offset_x + (col + 1) * cell_size - margin
        y1 = offset_y + (row + 1) * cell_size - margin
        canvas.create_line(x0, y0, x1, y1, fill="#222222", width=2)
        canvas.create_line(x0, y1, x1, y0, fill="#222222", width=2)

    # ----------------------------------------------------------- History display
    def _update_history(self, history: List[dict]) -> None:
        self.history_text.configure(state="normal")
        self.history_text.delete("1.0", tk.END)
        for entry in history:
            coord = entry["coordinate"]
            result = entry["result"]
            ship_info = f" (ship {entry['ship_id']})" if entry.get("ship_id") is not None else ""
            line = (
                f"Turn {entry['turn']:02d}: {entry['player_name']} -> "
                f"({coord['row']}, {coord['col']}) {result.upper()}{ship_info}\n"
            )
            self.history_text.insert(tk.END, line)
        self.history_text.configure(state="disabled")


def main() -> None:
    args = parse_args()
    visualizer = MatchVisualizer(
        args.base_url,
        args.match_id,
        args.lobby_key,
        args.api_key,
        args.interval,
        args.game_id,
    )
    try:
        visualizer.start()
    except KeyboardInterrupt:
        visualizer.on_close()
        sys.exit(0)


if __name__ == "__main__":
    main()
