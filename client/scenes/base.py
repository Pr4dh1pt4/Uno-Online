"""Kerangka scene & state aplikasi client yang dibagikan antar scene."""


class AppState:
    """State global client yang dibagikan antar scene."""

    def __init__(self, net, voice=None):
        self.net = net
        self.voice = voice
        self.user_id = None
        self.username = None
        self.token = None
        self.stats = {}
        # room
        self.room_id = None
        self.room_code = None
        self.host_id = None
        self.match_mode = "ranked"
        self.players = []
        self.is_spectator = False
        # game
        self.game_state = None
        self.hand = []          # list dict kartu milik sendiri
        self.last_result = None


class Scene:
    """Kelas dasar scene. Subclass mengimplementasikan handle/update/draw."""

    def __init__(self, app):
        self.app = app          # referensi ke ClientApp
        self.state: AppState = app.state

    def on_enter(self):
        pass

    def handle_event(self, event):
        pass

    def handle_packet(self, pkt):
        pass

    def update(self, dt):
        pass

    def draw(self, surf):
        pass

    # helper navigasi
    def go(self, scene_name: str):
        self.app.change_scene(scene_name)
