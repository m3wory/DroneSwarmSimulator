from typing import List, Tuple, Optional

import pygame

import config
from core.enums import CommandType, EditorMode
from core.command import Command
from entities.coordinator import CoordinatorDrone


class UI:
    def __init__(self):
        self.font_small = pygame.font.Font(None, config.UI_FONT_SMALL)
        self.font_medium = pygame.font.Font(None, config.UI_FONT_MEDIUM)
        self.font_large = pygame.font.Font(None, config.UI_FONT_LARGE)
        self.context_menu_open = False
        self.context_menu_pos = (0, 0)
        self.context_menu_items = [
            ("Move to", CommandType.MOVE_TO),
            ("Pick up", CommandType.PICK_UP),
            ("Drop", CommandType.DROP_OBJECT),
            ("Formation", CommandType.FORMATION),
        ]
        self.editor_menu_open = False
        self.editor_menu_items = [
            ("Obstacle", EditorMode.ADD_OBSTACLE),
            ("Charging Station", EditorMode.ADD_CHARGING_STATION),
            ("Workshop", EditorMode.ADD_WORKSHOP),
            ("Object (Small)", EditorMode.ADD_OBJECT_SMALL),
            ("Object (Medium)", EditorMode.ADD_OBJECT_MEDIUM),
            ("Object (Large)", EditorMode.ADD_OBJECT_LARGE),
            ("Object (Cycle)", EditorMode.ADD_OBJECT),
            ("Delete", EditorMode.DELETE),
        ]
        self.info_panel_open = True
        self.info_panel_collapsed = False
        self.info_panel_rect = pygame.Rect(
            config.INFO_PANEL_X_OFFSET, config.INFO_PANEL_Y_OFFSET, config.INFO_PANEL_WIDTH, 200
        )
        self.info_panel_toggle_rect = pygame.Rect(
            config.INFO_PANEL_X_OFFSET + config.INFO_PANEL_WIDTH + 4,
            60,
            config.INFO_PANEL_TOGGLE_WIDTH,
            config.INFO_PANEL_TOGGLE_HEIGHT,
        )
        self._print_help_to_console()

    def _print_help_to_console(self):
        for text in ["LMB - Select drone", "RMB - Command menu", "Drag - Select group", "E - Editor mode", "Space - Formation", "ESC - Deselect/Close"]:
            print(f"  - {text}")

    def draw_info_panel(self, screen: pygame.Surface, selected_drones: List):
        panel_w = config.INFO_PANEL_WIDTH
        max_visible = config.INFO_PANEL_MAX_VISIBLE_DRONES
        card_h = config.INFO_PANEL_CARD_HEIGHT
        count = len(selected_drones)
        panel_h = min(80 + min(count, max_visible) * card_h, config.SCREEN_HEIGHT - 160)
        panel_x = max(10, (config.SCREEN_WIDTH - panel_w) // 2)
        panel_y = 10
        self.info_panel_rect = pygame.Rect(panel_x, panel_y, panel_w, panel_h)

        self.info_panel_toggle_rect = pygame.Rect(
            panel_x + panel_w + 4,
            panel_y - 28,
            config.INFO_PANEL_TOGGLE_WIDTH,
            config.INFO_PANEL_TOGGLE_HEIGHT,
        )
        toggle_color = config.LIGHT_BLUE if self.info_panel_open and not self.info_panel_collapsed else config.DARK_GRAY
        pygame.draw.rect(screen, toggle_color, self.info_panel_toggle_rect, border_radius=6)
        arrow = ">" if self.info_panel_open and not self.info_panel_collapsed else "<"
        screen.blit(self.font_small.render(arrow, True, config.WHITE), (self.info_panel_toggle_rect.x + 8, self.info_panel_toggle_rect.y + 2))

        if not self.info_panel_open or self.info_panel_collapsed:
            collapsed_rect = pygame.Rect(panel_x + panel_w - 40, panel_y, 36, 24)
            pygame.draw.rect(screen, config.DARK_GRAY, collapsed_rect, border_radius=6)
            screen.blit(self.font_small.render(f"{count}", True, config.WHITE), (collapsed_rect.x + 10, collapsed_rect.y + 2))
            return

        bg = pygame.Surface((panel_w, panel_h), pygame.SRCALPHA)
        bg.fill(config.INFO_PANEL_BG_COLOR)
        screen.blit(bg, (panel_x, panel_y))
        pygame.draw.rect(screen, config.WHITE, self.info_panel_rect, 1, border_radius=8)

        header = self.font_medium.render(f"Selected Drones ({count})", True, config.WHITE)
        screen.blit(header, (panel_x + 12, panel_y + 8))

        y_offset = panel_y + 40
        for i, drone in enumerate(selected_drones[:max_visible]):
            card_rect = pygame.Rect(panel_x + 12, y_offset + i * card_h, panel_w - 24, card_h - 8)
            pygame.draw.rect(screen, (30, 34, 40), card_rect, border_radius=6)
            cx, cy = card_rect.x + 18, card_rect.y + card_rect.h // 2
            color = (
                config.RED
                if drone.hp < config.HP_LOW
                else (config.ORANGE if drone.energy < config.ENERGY_LOW else drone.color)
            )
            pygame.draw.circle(screen, color, (cx, cy), 10)
            id_surf = self.font_small.render(str(drone.id), True, config.BLACK)
            screen.blit(id_surf, (cx - id_surf.get_width() // 2, cy - id_surf.get_height() // 2))
            name = ("COORD" if isinstance(drone, CoordinatorDrone) else "DRONE") + f" #{drone.id}"
            screen.blit(self.font_small.render(name, True, config.WHITE), (cx + 22, card_rect.y + 6))
            bar_x = cx + 22
            bar_y = card_rect.y + 28
            bar_w = 140
            pygame.draw.rect(screen, config.DARK_GRAY, (bar_x, bar_y, bar_w, 8), border_radius=4)
            pygame.draw.rect(screen, config.GREEN, (bar_x, bar_y, int((drone.hp / drone.max_hp) * bar_w), 8), border_radius=4)
            screen.blit(self.font_small.render(f"HP {int(drone.hp)}", True, config.WHITE), (bar_x + bar_w + 8, bar_y - 2))
            e_y = bar_y + 14
            pygame.draw.rect(screen, config.DARK_GRAY, (bar_x, e_y, bar_w, 6), border_radius=3)
            pygame.draw.rect(screen, config.CYAN, (bar_x, e_y, int((drone.energy / drone.max_energy) * bar_w), 6), border_radius=3)
            screen.blit(self.font_small.render(drone.state.name, True, config.YELLOW), (card_rect.right - 80, card_rect.y + 8))

        if count > max_visible:
            screen.blit(self.font_small.render(f"+{count - max_visible} more", True, config.GRAY), (panel_x + 12, y_offset + max_visible * card_h))

    def draw_coordinator_status(self, screen: pygame.Surface, pending_tasks: int):
        if pending_tasks <= 0:
            return
        text = self.font_medium.render(f"Coordinator: {pending_tasks} pending tasks", True, config.PURPLE)
        screen.blit(text, (config.SCREEN_WIDTH - text.get_width() - 20, 10))

    def _draw_menu(self, screen: pygame.Surface, items: List, pos: Tuple[int, int], width: int, title: Optional[str] = None):
        if not items:
            return
        height = len(items) * config.CONTEXT_MENU_ITEM_HEIGHT
        menu_rect = pygame.Rect(pos[0], pos[1], width, height)
        surface = pygame.Surface((width, height))
        surface.set_alpha(config.CONTEXT_MENU_BG_ALPHA)
        surface.fill(config.DARK_GRAY)
        screen.blit(surface, (menu_rect.x, menu_rect.y))
        pygame.draw.rect(screen, config.YELLOW if title else config.WHITE, menu_rect, 2)
        if title:
            screen.blit(self.font_medium.render(title, True, config.YELLOW), (pos[0] + 20, pos[1] - 25))
        mouse_pos = pygame.mouse.get_pos()
        for i, (label, _) in enumerate(items):
            item_rect = pygame.Rect(menu_rect.x, menu_rect.y + i * config.CONTEXT_MENU_ITEM_HEIGHT, width, config.CONTEXT_MENU_ITEM_HEIGHT)
            if item_rect.collidepoint(mouse_pos):
                pygame.draw.rect(screen, config.LIGHT_BLUE, item_rect)
            screen.blit(self.font_small.render(label, True, config.WHITE), (item_rect.x + 10, item_rect.y + 8))

    def draw_context_menu(self, screen: pygame.Surface):
        if self.context_menu_open:
            self._draw_menu(screen, self.context_menu_items, self.context_menu_pos, config.CONTEXT_MENU_WIDTH)

    def draw_editor_menu(self, screen: pygame.Surface):
        if self.editor_menu_open:
            self._draw_menu(
                screen,
                self.editor_menu_items,
                (config.SCREEN_WIDTH - config.EDITOR_MENU_X_OFFSET, config.EDITOR_MENU_Y_OFFSET),
                config.EDITOR_MENU_WIDTH,
                "EDITOR MODE",
            )

    def draw_help(self, screen: pygame.Surface):
        return

