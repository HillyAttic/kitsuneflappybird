import os
import sys
import random
import math
from typing import List, Tuple, Dict

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
        # Avoid convert/convert_alpha before a display mode is set
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
        self.animation_interval = 0.08
        self.position_x, self.position_y = start_pos
        self.velocity_y = 0.0
        self.rotation = 0.0
        self.dead = False

    @property
    def image(self) -> pygame.Surface:
        return self.frames[int(self.animation_index) % len(self.frames)]

    def rect(self) -> pygame.Rect:
        img = self.image
        return pygame.Rect(int(self.position_x), int(self.position_y), img.get_width(), img.get_height())

    def update(self, dt: float, gravity: float, max_fall_speed: float, rot_down_speed_deg_per_sec: float) -> None:
        if self.dead:
            self.animation_index = 1
        else:
            self.animation_timer += dt
            if self.animation_timer >= self.animation_interval:
                self.animation_timer = 0.0
                self.animation_index = (self.animation_index + 1) % len(self.frames)

        # Physics similar to original clones (frame-based mapped to dt)
        self.velocity_y = min(self.velocity_y + gravity * dt, max_fall_speed)
        self.position_y += self.velocity_y * dt

        # Rotation: snap up on rise, fall towards -90 deg otherwise
        if self.velocity_y < 0:
            self.rotation = 45.0
        else:
            if self.rotation > -90.0:
                self.rotation = max(-90.0, self.rotation - rot_down_speed_deg_per_sec * dt)

    def flap(self, impulse: float) -> None:
        if not self.dead:
            self.velocity_y = -impulse
            self.rotation = 45.0

    def draw(self, surface: pygame.Surface) -> None:
        rotated = pygame.transform.rotate(self.image, self.rotation)
        rect = rotated.get_rect(center=self.rect().center)
        surface.blit(rotated, rect.topleft)

    def update_animation(self, dt: float) -> None:
        self.animation_timer += dt
        if self.animation_timer >= self.animation_interval:
            self.animation_timer = 0.0
            self.animation_index = (self.animation_index + 1) % len(self.frames)


class PipePair:
    def __init__(self, pipe_image: pygame.Surface, x: int, gap_y: int, gap_size: int, bottom_y: int) -> None:
        self.pipe_image = pipe_image
        self.pipe_image_flipped = pygame.transform.flip(pipe_image, False, True)
        self.x = float(x)
        self.gap_y = gap_y
        self.gap_size = gap_size
        self.bottom_y = bottom_y
        self.speed = 150.0
        self.passed = False

    @property
    def width(self) -> int:
        return self.pipe_image.get_width()

    def rects(self) -> Tuple[pygame.Rect, pygame.Rect]:
        top_height = self.gap_y - self.gap_size // 2
        bottom_top = self.gap_y + self.gap_size // 2
        top_rect = pygame.Rect(int(self.x), int(top_height) - self.pipe_image.get_height(), self.width, self.pipe_image.get_height())
        bottom_rect = pygame.Rect(int(self.x), int(bottom_top), self.width, self.pipe_image.get_height())
        return top_rect, bottom_rect

    def update(self, dt: float) -> None:
        self.x -= self.speed * dt

    def draw(self, surface: pygame.Surface) -> None:
        top_rect, bottom_rect = self.rects()
        surface.blit(self.pipe_image_flipped, top_rect.topleft)
        surface.blit(self.pipe_image, bottom_rect.topleft)


class Game:
    def __init__(self) -> None:
        pygame.init()

        self.sprites = SpriteLibrary()
        self.sounds = SoundLibrary()

        self.background_key = random.choice(["day", "night"])  # toggled on restart
        self.background = self.sprites.backgrounds[self.background_key]
        self.screen_width = self.background.get_width()
        self.screen_height = self.background.get_height()
        self.screen = pygame.display.set_mode((self.screen_width, self.screen_height))
        pygame.display.set_caption("Flappy Bird")

        self.clock = pygame.time.Clock()
        self.fps = 60

        self.base = self.sprites.base
        self.base_y = self.screen_height - self.base.get_height()
        self.base_x = 0.0
        self.base_speed = 150.0

        self.pipe_image = self.sprites.pipes["green"]
        self.pipes: List[PipePair] = []
        self.pipe_spawn_timer = 0.0
        self.pipe_spawn_interval = 1.25
        self.pipe_gap = 100

        self.bird_frames = self.sprites.birds["yellow"]
        self.bird = Bird(self.bird_frames, (self.screen_width // 6, self.screen_height // 2))
        self.gravity = 1800.0
        self.max_fall_speed = 600.0
        self.rot_down_speed = 250.0  # deg/sec toward -90 on fall
        self.flap_impulse = 350.0

        self.state = "WELCOME"
        self.score = 0
        self.high_score = 0

    def reset(self) -> None:
        self.background_key = "night" if self.background_key == "day" else "day"
        self.background = self.sprites.backgrounds[self.background_key]
        self.base_x = 0.0
        self.pipe_image = self.sprites.pipes["green"]
        self.pipes.clear()
        self.pipe_spawn_timer = 0.0
        self.bird_frames = self.sprites.birds["yellow"]
        self.bird = Bird(self.bird_frames, (self.screen_width // 6, self.screen_height // 2))
        self.score = 0
        self.state = "WELCOME"

    def spawn_pipe(self) -> None:
        # Slight sinusoidal bias to gap to mimic original feel
        min_center = int(self.screen_height * 0.25) + self.pipe_gap // 2
        max_center = int(self.base_y - 10 - self.pipe_gap // 2)
        base_center = random.randint(min_center, max_center)
        t = pygame.time.get_ticks() / 1000.0
        bias = int(20 * math.sin(t * 1.3))
        gap_center = max(min_center, min(max_center, base_center + bias))
        self.pipes.append(PipePair(self.pipe_image, self.screen_width + 10, gap_center, self.pipe_gap, self.base_y))

    def update_base(self, dt: float) -> None:
        self.base_x -= self.base_speed * dt
        if self.base_x <= - (self.base.get_width() - self.screen_width):
            self.base_x = 0.0

    def check_collisions(self) -> bool:
        bird_rect = self.bird.rect()
        if bird_rect.bottom >= self.base_y:
            return True

        rotated = pygame.transform.rotate(self.bird.image, self.bird.rotation)
        bird_mask = pygame.mask.from_surface(rotated)
        bird_rot_rect = rotated.get_rect(center=self.bird.rect().center)

        for pipe in self.pipes:
            top_rect, bottom_rect = pipe.rects()
            top_mask = pygame.mask.from_surface(pipe.pipe_image_flipped)
            bottom_mask = pygame.mask.from_surface(pipe.pipe_image)

            offset_top = (top_rect.left - bird_rot_rect.left, top_rect.top - bird_rot_rect.top)
            if bird_mask.overlap(top_mask, offset_top):
                return True

            offset_bottom = (bottom_rect.left - bird_rot_rect.left, bottom_rect.top - bird_rot_rect.top)
            if bird_mask.overlap(bottom_mask, offset_bottom):
                return True
        return False

    def update_score(self) -> None:
        for pipe in self.pipes:
            if not pipe.passed and pipe.x + pipe.width < self.bird.rect().left:
                pipe.passed = True
                self.score += 1
                self.high_score = max(self.high_score, self.score)
                self.sounds.play("point")

    def handle_input(self, event: pygame.event.Event) -> None:
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_SPACE, pygame.K_UP):
            if self.state == "WELCOME":
                self.state = "PLAYING"
                self.sounds.play("swoosh")
            elif self.state == "PLAYING":
                self.bird.flap(self.flap_impulse)
                self.sounds.play("wing")
            elif self.state == "GAME_OVER":
                self.reset()
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.state == "WELCOME":
                self.state = "PLAYING"
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
        y = int(self.screen_height * 0.25)
        for d in text_digits:
            img = self.sprites.digits[d]
            surface.blit(img, (x, y))
            x += img.get_width()

    def run(self) -> None:
        running = True
        death_sound_played = False
        while running:
            dt_ms = self.clock.tick(self.fps)
            dt = dt_ms / 1000.0

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                else:
                    self.handle_input(event)

            if self.state in ("WELCOME", "PLAYING"):
                self.update_base(dt)
                # In welcome screen, apply idle oscillation and slow animation
                if self.state == "WELCOME":
                    self.bird.update_animation(dt)
                    self.bird.position_y = (self.screen_height // 2) + 6 * math.sin(pygame.time.get_ticks() / 250.0)
                    self.bird.rotation = 0.0
                else:
                    self.bird.update(dt, self.gravity, self.max_fall_speed, self.rot_down_speed)

            if self.state == "PLAYING":
                self.pipe_spawn_timer += dt
                if self.pipe_spawn_timer >= self.pipe_spawn_interval:
                    self.pipe_spawn_timer = 0.0
                    self.spawn_pipe()

                for pipe in list(self.pipes):
                    pipe.update(dt)
                self.pipes = [p for p in self.pipes if p.x + p.width > -10]

                if self.check_collisions():
                    self.state = "GAME_OVER"
                    self.bird.dead = True
                    death_sound_played = False
                    self.sounds.play("hit")

                self.update_score()

            elif self.state == "GAME_OVER":
                self.update_base(dt)
                self.bird.update(dt, self.gravity, self.max_fall_speed, self.rot_down_speed)
                if not death_sound_played and self.bird.rect().bottom >= self.base_y - 1:
                    death_sound_played = True
                    self.sounds.play("die")

            self.screen.blit(self.background, (0, 0))
            for pipe in self.pipes:
                pipe.draw(self.screen)
            self.screen.blit(self.base, (int(self.base_x), self.base_y))
            self.screen.blit(self.base, (int(self.base_x) + self.base.get_width(), self.base_y))
            self.bird.draw(self.screen)

            if self.state == "WELCOME":
                msg_rect = self.sprites.message.get_rect(center=(self.screen_width // 2, int(self.screen_height * 0.40)))
                self.screen.blit(self.sprites.message, msg_rect.topleft)
                # Draw score 0 like original welcome screen shows no score
            if self.state in ("PLAYING",):
                self.draw_score(self.screen)
            if self.state == "GAME_OVER":
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


