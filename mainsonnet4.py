import os
import sys
import random
import math
from typing import List, Tuple, Dict

# Ensure a real Windows video driver is used (avoid 'dummy' headless driver)
if os.name == "nt":
    os.environ.setdefault("SDL_VIDEODRIVER", "windows")
    os.environ.setdefault("SDL_VIDEO_CENTERED", "1")

import pygame


def get_resource_path(*parts: str) -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, *parts)


class SpriteLibrary:
    def __init__(self, screen_scale: float = 1.0) -> None:
        self.scale = screen_scale
        self.backgrounds: Dict[str, pygame.Surface] = {}
        self.base: pygame.Surface
        self.birds: Dict[str, List[pygame.Surface]] = {}
        self.pipes: Dict[str, pygame.Surface] = {}
        self.message: pygame.Surface
        self.gameover: pygame.Surface
        self.digits: List[pygame.Surface] = []
        self._load_all()

    def _load_image(self, *path: str, convert_alpha: bool = True) -> pygame.Surface:
        image = pygame.image.load(get_resource_path(*path))
        if pygame.display.get_surface() is not None:
            return image.convert_alpha() if convert_alpha else image.convert()
        return image

    def _scale_surface(self, surface: pygame.Surface) -> pygame.Surface:
        if self.scale == 1.0:
            return surface
        width = int(surface.get_width() * self.scale)
        height = int(surface.get_height() * self.scale)
        return pygame.transform.smoothscale(surface, (width, height))

    def _load_all(self) -> None:
        self.backgrounds["day"] = self._scale_surface(self._load_image("sprites", "background-day.png"))
        self.backgrounds["night"] = self._scale_surface(self._load_image("sprites", "background-night.png"))

        self.base = self._scale_surface(self._load_image("sprites", "base.png"))

        bird_sets = {
            "yellow": [
                "yellowbird-downflap.png",
                "yellowbird-midflap.png",
                "yellowbird-upflap.png",
            ],
            "blue": [
                "bluebird-downflap.png",
                "bluebird-midflap.png",
                "bluebird-upflap.png",
            ],
            "red": [
                "redbird-downflap.png",
                "redbird-midflap.png",
                "redbird-upflap.png",
            ],
        }
        for color, files in bird_sets.items():
            frames = [self._scale_surface(self._load_image("sprites", f)) for f in files]
            self.birds[color] = frames

        self.pipes["green"] = self._scale_surface(self._load_image("sprites", "pipe-green.png"))
        self.pipes["red"] = self._scale_surface(self._load_image("sprites", "pipe-red.png"))

        self.message = self._scale_surface(self._load_image("sprites", "message.png"))
        self.gameover = self._scale_surface(self._load_image("sprites", "gameover.png"))

        for i in range(10):
            self.digits.append(self._scale_surface(self._load_image("sprites", f"{i}.png")))


class SoundLibrary:
    def __init__(self) -> None:
        self.enabled = False
        self.sounds: Dict[str, pygame.mixer.Sound] = {}
        self._init_mixer()
        self._load_sounds()

    def _init_mixer(self) -> None:
        try:
            pygame.mixer.init()
            self.enabled = True
        except Exception:
            self.enabled = False

    def _try_load(self, name: str) -> None:
        if not self.enabled:
            return
        for ext in ("wav", "ogg"):
            candidate = get_resource_path("audio", f"{name}.{ext}")
            if os.path.exists(candidate):
                try:
                    self.sounds[name] = pygame.mixer.Sound(candidate)
                    return
                except Exception:
                    continue

    def _load_sounds(self) -> None:
        for n in ("wing", "point", "die", "hit", "swoosh"):
            self._try_load(n)

    def play(self, name: str) -> None:
        if self.enabled and name in self.sounds:
            try:
                self.sounds[name].play()
            except Exception:
                pass


class Bird:
    def __init__(self, frames: List[pygame.Surface], start_pos: Tuple[int, int]) -> None:
        self.frames = frames
        self.animation_index = 0
        self.animation_timer = 0.0
        self.animation_interval = 0.1
        self.position_x, self.position_y = start_pos
        self.initial_y = start_pos[1]  # Store initial position for wobble
        self.velocity_y = 0.0
        self.rotation = 0.0
        self.dead = False
        self.max_fall_speed = 400.0
        self.wobble_amplitude = 8.0
        self.wobble_timer = 0.0
        
        # Get bird center for proper rotation
        self.center_x = self.frames[0].get_width() // 2
        self.center_y = self.frames[0].get_height() // 2

    @property
    def image(self) -> pygame.Surface:
        return self.frames[int(self.animation_index) % len(self.frames)]

    def rect(self) -> pygame.Rect:
        img = self.image
        rect = pygame.Rect(int(self.position_x), int(self.position_y), img.get_width(), img.get_height())
        rect.inflate_ip(-8, -8)
        return rect

    def get_center(self) -> Tuple[float, float]:
        """Get the center point of the bird for rotation"""
        return (self.position_x + self.center_x, self.position_y + self.center_y)

    def update(self, dt: float, gravity: float, rotation_speed: float, is_playing: bool = True) -> None:
        # Update animation
        if self.dead:
            self.animation_index = 1
        else:
            self.animation_timer += dt
            if self.animation_timer >= self.animation_interval:
                self.animation_timer = 0.0
                self.animation_index = (self.animation_index + 1) % len(self.frames)

        if is_playing:
            # Apply gravity with terminal velocity
            self.velocity_y += gravity * dt
            self.velocity_y = min(self.velocity_y, self.max_fall_speed)
            self.position_y += self.velocity_y * dt
            
            # Smooth rotation based on velocity
            if self.velocity_y > 0:  # Falling
                target_rotation = min(90, self.velocity_y * 0.15)
            else:  # Rising
                target_rotation = max(-30, self.velocity_y * 0.2)
                
            rotation_diff = target_rotation - self.rotation
            self.rotation += rotation_diff * min(1.0, rotation_speed * dt)
        else:
            # Idle wobble animation - smooth sine wave
            self.wobble_timer += dt * 2.0  # Speed of wobble
            wobble_offset = self.wobble_amplitude * math.sin(self.wobble_timer)
            self.position_y = self.initial_y + wobble_offset
            self.rotation = 0

    def flap(self, impulse: float) -> None:
        if not self.dead:
            self.velocity_y = -impulse

    def draw(self, surface: pygame.Surface) -> None:
        # Get the current image
        current_image = self.image
        
        # Rotate the image around its center
        if abs(self.rotation) > 0.1:  # Only rotate if necessary
            rotated_image = pygame.transform.rotate(current_image, -self.rotation)  # Negative for correct direction
            # Calculate the new position to keep the rotation centered
            old_center = self.get_center()
            new_rect = rotated_image.get_rect(center=old_center)
            surface.blit(rotated_image, new_rect.topleft)
        else:
            # No rotation needed
            surface.blit(current_image, (int(self.position_x), int(self.position_y)))


class PipePair:
    def __init__(self, pipe_image: pygame.Surface, x: int, gap_y: int, gap_size: int, bottom_y: int, speed: float) -> None:
        self.pipe_image = pipe_image
        self.pipe_image_flipped = pygame.transform.flip(pipe_image, False, True)
        self.x = float(x)
        self.gap_y = gap_y
        self.gap_size = gap_size
        self.bottom_y = bottom_y
        self.speed = speed
        self.passed = False

    @property
    def width(self) -> int:
        return self.pipe_image.get_width()

    def rects(self) -> Tuple[pygame.Rect, pygame.Rect]:
        top_height = self.gap_y - self.gap_size // 2
        bottom_top = self.gap_y + self.gap_size // 2
        top_rect = pygame.Rect(int(self.x), int(top_height) - self.pipe_image.get_height(), 
                                self.width, self.pipe_image.get_height())
        bottom_rect = pygame.Rect(int(self.x), int(bottom_top), self.width, self.pipe_image.get_height())
        top_rect.inflate_ip(-4, 0)
        bottom_rect.inflate_ip(-4, 0)
        return top_rect, bottom_rect

    def update(self, dt: float) -> None:
        self.x -= self.speed * dt

    def draw(self, surface: pygame.Surface) -> None:
        top_rect, bottom_rect = self.rects()
        draw_top = pygame.Rect(int(self.x) - 2, top_rect.top, self.width, top_rect.height)
        draw_bottom = pygame.Rect(int(self.x) - 2, bottom_rect.top, self.width, bottom_rect.height)
        surface.blit(self.pipe_image_flipped, draw_top.topleft)
        surface.blit(self.pipe_image, draw_bottom.topleft)


class DifficultySettings:
    def __init__(self):
        # Single, clean preset matching classic feel
        self.settings = {
            "gravity": 700.0,
            "flap_impulse": 280.0,
            "pipe_gap": 140,
            "pipe_speed": 150.0,
            "pipe_interval": 1.8,
        }
    
    def get_current_settings(self):
        return self.settings


class Game:
    def __init__(self) -> None:
        pygame.init()

        self.sprites = SpriteLibrary()
        self.sounds = SoundLibrary()
        self.difficulty_settings = DifficultySettings()

        self.background_key = random.choice(["day", "night"])
        self.background = self.sprites.backgrounds[self.background_key]
        self.screen_width = self.background.get_width()
        self.screen_height = self.background.get_height()
        pygame.display.init()
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.event.pump()
        if pygame.display.get_surface() is None:
            raise RuntimeError("Failed to initialize video display")
        pygame.display.set_caption("Flappy Bird")

        self.clock = pygame.time.Clock()
        self.fps = 60

        # Score font (kept minimal UI)
        try:
            self.font_small = pygame.font.Font(None, 24)
        except:
            self.font_small = pygame.font.SysFont('Arial', 24)

        self.base = self.sprites.base
        self.base_y = self.screen_height - self.base.get_height()
        self.base_x = 0.0

        self.pipe_image = self.sprites.pipes[random.choice(["green", "red"])]
        self.pipes: List[PipePair] = []
        self.pipe_spawn_timer = 0.0

        self.bird_frames = self.sprites.birds[random.choice(["yellow", "blue", "red"])]
        self.bird = Bird(self.bird_frames, (self.screen_width // 4, self.screen_height // 2))
        self.rotation_speed = 6.0

        self.state = "WELCOME"
        self.score = 0
        self.high_score = self._load_high_score()
        self._apply_difficulty_settings()

    def _apply_difficulty_settings(self):
        """Apply current difficulty settings to game parameters"""
        settings = self.difficulty_settings.get_current_settings()
        self.gravity = settings["gravity"]
        self.flap_impulse = settings["flap_impulse"]
        self.pipe_gap = settings["pipe_gap"]
        self.base_speed = settings["pipe_speed"]
        self.pipe_spawn_interval = settings["pipe_interval"]

    def _load_high_score(self) -> int:
        try:
            with open("highscore.txt", "r") as f:
                return int(f.read().strip())
        except:
            return 0

    def _save_high_score(self) -> None:
        try:
            with open("highscore.txt", "w") as f:
                f.write(str(self.high_score))
        except:
            pass

    def reset(self) -> None:
        self.background_key = "night" if self.background_key == "day" else "day"
        self.background = self.sprites.backgrounds[self.background_key]
        self.base_x = 0.0
        self.pipe_image = self.sprites.pipes[random.choice(["green", "red"])]
        self.pipes.clear()
        self.pipe_spawn_timer = 0.0
        self.bird_frames = self.sprites.birds[random.choice(["yellow", "blue", "red"])]
        self.bird = Bird(self.bird_frames, (self.screen_width // 4, self.screen_height // 2))
        self.score = 0
        self.state = "WELCOME"

    def spawn_pipe(self) -> None:
        min_center = int(self.screen_height * 0.25) + self.pipe_gap // 2
        max_center = int(self.base_y - 20 - self.pipe_gap // 2)
        gap_center = random.randint(min_center, max_center)
        self.pipes.append(PipePair(self.pipe_image, self.screen_width + 10, 
                                   gap_center, self.pipe_gap, self.base_y, self.base_speed))

    def update_base(self, dt: float) -> None:
        self.base_x -= self.base_speed * dt
        if self.base_x <= -(self.base.get_width() - self.screen_width):
            self.base_x = 0.0

    def check_collisions(self) -> bool:
        bird_rect = self.bird.rect()
        
        if bird_rect.bottom >= self.base_y - 5:
            return True
        
        if bird_rect.top <= 0:
            return True

        for pipe in self.pipes:
            top_rect, bottom_rect = pipe.rects()
            if bird_rect.colliderect(top_rect) or bird_rect.colliderect(bottom_rect):
                return True
        
        return False

    def update_score(self) -> None:
        for pipe in self.pipes:
            if not pipe.passed and pipe.x + pipe.width < self.bird.position_x:
                pipe.passed = True
                self.score += 1
                if self.score > self.high_score:
                    self.high_score = self.score
                    self._save_high_score()
                self.sounds.play("point")

    def handle_difficulty_input(self, event: pygame.event.Event) -> None:
        pass

    def handle_input(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_UP):
            if self.state == "WELCOME":
                self.state = "PLAYING"
                self.bird.flap(self.flap_impulse)
                self.sounds.play("swoosh")
            elif self.state == "PLAYING":
                self.bird.flap(self.flap_impulse)
                self.sounds.play("wing")
            elif self.state == "GAME_OVER":
                self.reset()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.state == "WELCOME":
                self.state = "PLAYING"
                self.bird.flap(self.flap_impulse)
                self.sounds.play("swoosh")
            elif self.state == "PLAYING":
                self.bird.flap(self.flap_impulse)
                self.sounds.play("wing")
            elif self.state == "GAME_OVER":
                self.reset()

    def draw_score(self, surface: pygame.Surface) -> None:
        digits = [int(d) for d in str(self.score)]
        total_width = sum(self.sprites.digits[d].get_width() for d in digits)
        x = (self.screen_width - total_width) // 2
        y = int(self.screen_height * 0.12)
        for d in digits:
            img = self.sprites.digits[d]
            surface.blit(img, (x, y))
            x += img.get_width()

    def draw_high_score(self, surface: pygame.Surface) -> None:
        if self.state != "GAME_OVER":
            return
        text_digits = [int(d) for d in str(self.high_score)]
        total_width = sum(self.sprites.digits[d].get_width() for d in text_digits)
        x = (self.screen_width - total_width) // 2
        y = int(self.screen_height * 0.40)
        for d in text_digits:
            img = self.sprites.digits[d]
            surface.blit(img, (x, y))
            x += img.get_width()

    def draw_difficulty_menu(self, surface: pygame.Surface) -> None:
        pass

    def run(self) -> None:
        running = True
        death_sound_played = False
        
        while running:
            dt_ms = self.clock.tick(self.fps)
            dt = dt_ms / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    running = False
                else:
                    self.handle_input(event)

            # Update base animation always
            self.update_base(dt)

            if self.state == "WELCOME":
                self.bird.update(dt, self.gravity, self.rotation_speed, is_playing=False)
                
            elif self.state == "PLAYING":
                self.bird.update(dt, self.gravity, self.rotation_speed, is_playing=True)
                
                # Spawn pipes
                self.pipe_spawn_timer += dt
                if self.pipe_spawn_timer >= self.pipe_spawn_interval:
                    self.pipe_spawn_timer = 0.0
                    self.spawn_pipe()

                # Update pipes
                for pipe in list(self.pipes):
                    pipe.update(dt)
                self.pipes = [p for p in self.pipes if p.x + p.width > -50]

                # Check collisions
                if self.check_collisions():
                    self.state = "GAME_OVER"
                    self.bird.dead = True
                    death_sound_played = False
                    self.sounds.play("hit")

                self.update_score()

            elif self.state == "GAME_OVER":
                self.bird.update(dt, self.gravity * 1.5, self.rotation_speed, is_playing=True)
                if not death_sound_played and self.bird.rect().bottom >= self.base_y - 1:
                    death_sound_played = True
                    self.sounds.play("die")

            # Render game
            self.screen.blit(self.background, (0, 0))
            
            for pipe in self.pipes:
                pipe.draw(self.screen)
            
            self.screen.blit(self.base, (int(self.base_x), self.base_y))
            self.screen.blit(self.base, (int(self.base_x) + self.base.get_width(), self.base_y))
            
            self.bird.draw(self.screen)

            if self.state == "WELCOME":
                msg_rect = self.sprites.message.get_rect(center=(self.screen_width // 2, int(self.screen_height * 0.40)))
                self.screen.blit(self.sprites.message, msg_rect.topleft)
            elif self.state == "PLAYING":
                self.draw_score(self.screen)
            elif self.state == "GAME_OVER":
                go_rect = self.sprites.gameover.get_rect(center=(self.screen_width // 2, int(self.screen_height * 0.20)))
                self.screen.blit(self.sprites.gameover, go_rect.topleft)
                self.draw_score(self.screen)
                self.draw_high_score(self.screen)

            pygame.display.flip()

        pygame.quit()


def main() -> None:
    try:
        Game().run()
    except Exception as exc:
        print(f"Error: {exc}")
        pygame.quit()
        sys.exit(1)


if __name__ == "__main__":
    main()