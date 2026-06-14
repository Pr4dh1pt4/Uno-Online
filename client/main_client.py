import sys

import pygame

import config
from shared.packet_types import S2C
from client.network.client_network import ClientNetwork
from client.network.voice_client import VoiceClient
from client.scenes.base import AppState
from client.scenes.login_scene import LoginScene
from client.scenes.lobby_scene import LobbyScene
from client.scenes.room_scene import RoomScene
from client.scenes.game_scene import GameScene
from client.scenes.spectator_scene import SpectatorScene
from client.scenes.result_scene import ResultScene
from client.scenes.leaderboard_scene import LeaderboardScene

class ClientApp:
    def __init__(self, host: str):
        pygame.init()
        self.host = host
        pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=512)
        pygame.display.set_caption("UNO Online")
        self.screen = pygame.display.set_mode((config.WINDOW_WIDTH, config.WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()

        from client.ui import sounds
        sounds.init()
        sounds.play_music("lobby")

        self.net = ClientNetwork()
        self.connected = self.net.connect(host)
        self.voice = VoiceClient(host)
        self.state = AppState(self.net, self.voice)

        self.scenes = {
            "login": LoginScene(self),
            "lobby": LobbyScene(self),
            "room": RoomScene(self),
            "game": GameScene(self),
            "spectator": SpectatorScene(self),
            "result": ResultScene(self),
            "leaderboard": LeaderboardScene(self),
        }
        self.current = self.scenes["login"]
        self.running = True

    def change_scene(self, name: str):
        self.current = self.scenes[name]
        self.current.on_enter()

    def run(self):
        while self.running:
            dt = self.clock.tick(config.FPS) / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    self.running = False
                else:
                    self.current.handle_event(event)

            for pkt in self.net.poll():
                if pkt.get("type") == S2C.FORCE_LOGOUT:
                    self.state.user_id = None
                    self.state.username = None
                    self.state.token = None
                    self.state.room_id = None
                    self.state.game_state = None
                    self.state.hand = []
                    self.state.is_spectator = False
                    self.state.match_mode = "ranked"
                    self.voice.leave()
                    self.change_scene("login")
                    self.current.handle_packet(pkt)
                    continue
                self.current.handle_packet(pkt)

            self.current.update(dt)
            self.current.draw(self.screen)

            if not self.net.connected and self.connected:
                self._draw_disconnected()

            pygame.display.flip()

        self.net.close()
        self.voice.close()
        pygame.quit()

    def _draw_disconnected(self):
        from client.ui.widgets import draw_text, draw_gradient_rect, Palette
        overlay = pygame.Surface((config.WINDOW_WIDTH, 42), pygame.SRCALPHA)
        draw_gradient_rect(overlay, (0, 0, config.WINDOW_WIDTH, 42),
                           (200, 40, 40, 220), (160, 30, 30, 180))
        self.screen.blit(overlay, (0, config.WINDOW_HEIGHT - 42))
        draw_text(self.screen, "⚠  Koneksi ke server terputus.",
                  (config.WINDOW_WIDTH // 2, config.WINDOW_HEIGHT - 21), 16,
                  (255, 255, 255), center=True)

def main():
    host = config.CLIENT_CONNECT_HOST
    if "--server" in sys.argv:
        i = sys.argv.index("--server")
        if i + 1 < len(sys.argv):
            host = sys.argv[i + 1]

    app = ClientApp(host)
    if not app.connected:
        print(f"Gagal terhubung ke server {host}:{config.SERVER_PORT}. "
              f"Pastikan server berjalan.")
    app.run()

if __name__ == "__main__":
    main()
