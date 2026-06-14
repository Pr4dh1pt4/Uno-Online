class AppState:

    def __init__(self, net, voice=None):
        self.net = net
        self.voice = voice
        self.user_id = None
        self.username = None
        self.token = None
        self.stats = {}
        self.room_id = None
        self.room_code = None
        self.host_id = None
        self.match_mode = "ranked"
        self.players = []
        self.is_spectator = False
        self.game_state = None
        self.hand = []
        self.last_result = None

class Scene:

    def __init__(self, app):
        self.app = app
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

    def go(self, scene_name: str):
        self.app.change_scene(scene_name)
