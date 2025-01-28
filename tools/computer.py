import asyncio
import base64
import os
import shlex
import shutil
import logging
from enum import StrEnum
from pathlib import Path
from typing import Literal, TypedDict
from uuid import uuid4
import pyautogui

import subprocess

# Set up logging - only show INFO level messages
logging.basicConfig(
    level=logging.INFO,
    format='%(message)s'  # Only show the message, no timestamps or levels
)
logger = logging.getLogger(__name__)

# Handle Retina scaling through coordinate calculations instead of pyautogui.setRetinaScaling

from anthropic.types.beta import BetaToolComputerUse20241022Param

from .base import BaseAnthropicTool, ToolError, ToolResult
from .run import run

OUTPUT_DIR = "/tmp/outputs"

TYPING_DELAY_MS = 12
TYPING_GROUP_SIZE = 50

Action = Literal[
    "key",
    "type",
    "mouse_move",
    "left_click",
    "left_click_drag",
    "right_click",
    "middle_click",
    "double_click",
    "screenshot",
    "cursor_position",
]


class Resolution(TypedDict):
    width: int
    height: int


# sizes above XGA/WXGA are not recommended (see README.md)
# scale down to one of these targets if ComputerTool._scaling_enabled is set
MAX_SCALING_TARGETS: dict[str, Resolution] = {
    "Custom": Resolution(width=1470, height=956)  # Custom resolution for this system
}


class ScalingSource(StrEnum):
    COMPUTER = "computer"
    API = "api"


class ComputerToolOptions(TypedDict):
    display_height_px: int
    display_width_px: int
    display_number: int | None


def chunks(s: str, chunk_size: int) -> list[str]:
    return [s[i : i + chunk_size] for i in range(0, len(s), chunk_size)]


class ComputerTool(BaseAnthropicTool):
    """
    A tool that allows the agent to interact with the screen, keyboard, and mouse of the current computer.
    The tool parameters are defined by Anthropic and are not editable.
    """

    name: Literal["computer"] = "computer"
    api_type: Literal["computer_20241022"] = "computer_20241022"
    width: int
    height: int
    display_num: int | None
    scaling_factor: float = 2.0  # Retina display scaling factor

    _screenshot_delay = 2.0
    _scaling_enabled = True

    @property
    def options(self) -> ComputerToolOptions:
        # Use the logical (scaled) resolution for the API
        return {
            "display_width_px": self.width,
            "display_height_px": self.height,
            "display_number": self.display_num,
        }

    def to_params(self) -> BetaToolComputerUse20241022Param:
        return {"name": self.name, "type": self.api_type, **self.options}

    def __init__(self):
        super().__init__()
        # PyAutoGUI already returns the logical resolution
        screen_size = pyautogui.size()
        logger.info("\n=== Screen Configuration ===")
        logger.info(f"Logical Resolution: {screen_size.width}x{screen_size.height}")
        logger.info(f"Physical Resolution: {screen_size.width * self.scaling_factor}x{screen_size.height * self.scaling_factor}")
        
        # Store the logical resolution directly
        self.width = screen_size.width
        self.height = screen_size.height
        logger.info(f"Scaling Factor: {self.scaling_factor}")
        self.display_num = None

    async def __call__(
        self,
        *,
        action: Action,
        text: str | None = None,
        coordinate: tuple[int, int] | None = None,
        **kwargs,
    ):
        if action in ("mouse_move", "left_click_drag"):
            if coordinate is None:
                raise ToolError(f"coordinate is required for {action}")
            if text is not None:
                raise ToolError(f"text is not accepted for {action}")
            if not isinstance(coordinate, list) or len(coordinate) != 2:
                raise ToolError(f"{coordinate} must be a tuple of length 2")
            if not all(isinstance(i, int) and i >= 0 for i in coordinate):
                raise ToolError(f"{coordinate} must be a tuple of non-negative ints")

            logger.info(f"\n=== Mouse Action: {action} ===")
            logger.info(f"Input coordinates: ({coordinate[0]}, {coordinate[1]})")
            x, y = self.scale_coordinates(
                ScalingSource.API, coordinate[0], coordinate[1]
            )
            logger.info(f"Target screen position: ({x}, {y})")

            if action == "mouse_move":
                current_pos = pyautogui.position()
                logger.info(f"Current mouse: ({current_pos.x}, {current_pos.y})")
                pyautogui.moveTo(x, y)
                new_pos = pyautogui.position()
                logger.info(f"New mouse: ({new_pos.x}, {new_pos.y})")
                return ToolResult(output=f"Moved mouse to {x}, {y}")
            elif action == "left_click_drag":
                pyautogui.dragTo(x, y, button='left')
                return ToolResult(output=f"Dragged mouse to {x}, {y}")

        if action in ("key", "type"):
            if text is None:
                raise ToolError(f"text is required for {action}")
            if coordinate is not None:
                raise ToolError(f"coordinate is not accepted for {action}")
            if not isinstance(text, str):
                raise ToolError(output=f"{text} must be a string")

            if action == "key":
                pyautogui.press(text)
                return ToolResult(output=f"Pressed key {text}")
            elif action == "type":
                pyautogui.write(text, interval=TYPING_DELAY_MS/1000)
                screenshot_base64 = (await self.screenshot()).base64_image
                return ToolResult(
                    output=f"Typed text: {text}",
                    base64_image=screenshot_base64,
                )

        if action in (
            "left_click",
            "right_click",
            "double_click",
            "middle_click",
            "screenshot",
            "cursor_position",
        ):
            if text is not None:
                raise ToolError(f"text is not accepted for {action}")
            if coordinate is not None:
                raise ToolError(f"coordinate is not accepted for {action}")

            if action == "screenshot":
                return await self.screenshot()
            elif action == "cursor_position":
                x, y = pyautogui.position()
                x, y = self.scale_coordinates(ScalingSource.COMPUTER, x, y)
                return ToolResult(output=f"X={x},Y={y}")
            else:
                button = {
                    "left_click": "left",
                    "right_click": "right",
                    "middle_click": "middle",
                }
                if action == "double_click":
                    pyautogui.doubleClick()
                else:
                    pyautogui.click(button=button[action])
                return ToolResult(output=f"Performed {action}")

        raise ToolError(f"Invalid action: {action}")

    async def screenshot(self):
        """Take a screenshot using pyautogui and return the base64 encoded image."""
        output_dir = Path(OUTPUT_DIR)
        output_dir.mkdir(parents=True, exist_ok=True)
        path = output_dir / f"screenshot_{uuid4().hex}.png"

        # Take screenshot using pyautogui
        screenshot = pyautogui.screenshot()
        screenshot.save(str(path))

        if self._scaling_enabled:
            x, y = self.scale_coordinates(
                ScalingSource.COMPUTER, self.width, self.height
            )
            resized = screenshot.resize((x, y))
            resized.save(str(path))

        if path.exists():
            return ToolResult(
                base64_image=base64.b64encode(path.read_bytes()).decode()
            )
        raise ToolError("Failed to take screenshot")

    async def shell(self, command: str, take_screenshot=True) -> ToolResult:
        """Run a shell command and return the output, error, and optionally a screenshot."""
        process = await asyncio.create_subprocess_shell(
            command,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        stdout, stderr = await process.communicate()
        base64_image = None

        if take_screenshot:
            await asyncio.sleep(self._screenshot_delay)
            base64_image = (await self.screenshot()).base64_image

        return ToolResult(
            output=stdout.decode() if stdout else None,
            error=stderr.decode() if stderr else None,
            base64_image=base64_image
        )

    def scale_coordinates(self, source: ScalingSource, x: int, y: int):
        """Scale coordinates to a target maximum resolution."""
        if not self._scaling_enabled:
            return x, y
            
        if source == ScalingSource.API:
            # Input coordinates are in API space (1470x956)
            # First convert to logical coordinates (also 1470x956)
            logical_x = x  # No scaling needed since API matches logical
            logical_y = y
            # Then convert logical to physical (multiply by 2 for Retina)
            physical_x = int(logical_x * self.scaling_factor)
            physical_y = int(logical_y * self.scaling_factor)
            logger.info(f"API coords ({x}, {y}) -> Physical ({physical_x}, {physical_y})")
            return (physical_x, physical_y)
        else:
            # Input coordinates are in physical space (2940x1912)
            # Convert to logical coordinates (divide by 2 for Retina)
            logical_x = int(x / self.scaling_factor)
            logical_y = int(y / self.scaling_factor)
            # Logical coordinates are already in API space (1470x956)
            logger.info(f"Physical ({x}, {y}) -> Logical/API ({logical_x}, {logical_y})")
            return (logical_x, logical_y)
